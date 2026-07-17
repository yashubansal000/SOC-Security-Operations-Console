# Module 1 — Synthetic Multi-Source Generator

Loads UNSW-NB15 flow data, enriches it with a deterministic synthetic layer
(timestamps, enterprise topology, host placement, config-change events,
syslog lines), and writes everything to a single SQLite database used as
the ground-truth source for Modules 2–7.

- **Deterministic**: fixed seed → same DB every run, byte-for-byte
- **Idempotent**: re-running drops and recreates all tables cleanly
- **Fast**: ~60 seconds end-to-end on the full 258k-row dataset
- **Self-validating**: 10 post-write checks, script exits non-zero on any failure

---

## 1. Project Layout

```
project-root/
├── data/
│   ├── raw/                              # SOURCE DATASETS go here
│   │   ├── UNSW_NB15_training-set.parquet
│   │   └── UNSW_NB15_testing-set.parquet
│   └── processed/
│       └── rca.db                         # OUTPUT (created by the script)
├── synth/
│   ├── __init__.py
│   └── generate_multisource.py           # THE script
├── logs/
│   └── generate_multisource.log           # created on first run
├── requirements.txt
└── README.md                              # this file
```

The script computes all paths relative to the project root (via `__file__`),
so it runs correctly from any working directory as long as this layout is intact.

---

## 2. Prerequisites

- **Python 3.11+** (uses PEP 604 union syntax, `from __future__ import annotations`)
- ~200MB free disk space (the generated DB is ~88MB, plus temporary DataFrame
  memory during processing)

---

## 3. Setup

```bash
# 1. Create a virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate            # Linux/macOS
# .venv\Scripts\activate             # Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Place the source data files in data/raw/
#    (paths shown are relative to the project root)
cp /path/to/UNSW_NB15_training-set.parquet data/raw/
cp /path/to/UNSW_NB15_testing-set.parquet  data/raw/
```

Expected `data/raw/` contents:

```
UNSW_NB15_training-set.parquet   (~10 MB)
UNSW_NB15_testing-set.parquet    (~5 MB)
```

---

## 4. Run

```bash
python3 synth/generate_multisource.py
```

Expected wall-clock time: **~60 seconds** on a modern laptop.

Expected output:

- `data/processed/rca.db` — SQLite database (~88 MB)
- `logs/generate_multisource.log` — full run log (dual: console + file)

Exit code:
- `0` — all sections completed and all 10 validation checks passed
- `1` — any hard failure (missing input file, schema mismatch, validation failure)

---

## 5. What the Script Produces

Four SQLite tables in `data/processed/rca.db`:

| Table | Rows (full dataset) | Purpose |
|---|---|---|
| `flows` | ~257,673 | Original UNSW-NB15 flow features + synthetic `ts`, `host_id`, `flow_id`, `split` |
| `synthetic_topology` | 20 | Fixed enterprise topology (firewall / DNS / web / app / DB / auth / mail / infra / external) with adjacency |
| `synthetic_config_changes` | ~50–60 | Infrastructure change events injected before ~35% of attack clusters |
| `synthetic_logs` | ~257,673 | One syslog-style line per flow, with `INFO`/`WARN`/`ERROR` severity |

Full schema is documented in the script's Section 10 (`_FLOWS_TABLE_COLUMNS`,
`_TOPOLOGY_TABLE_COLUMNS`, etc.).

### Design decisions worth knowing before Module 2/3 builds on this

1. **Only ~35% of attack clusters get a config-change record.** Intentional —
   the remaining 65% become "missing evidence" cases for Module 3, satisfying
   the problem statement's "explicitly refuse to evaluate incomplete data"
   requirement. If every cluster had a change, the three-way `confirmed /
   correlated / missing` evidence split would be untestable.
2. **Attack rows cluster in time (04:00–18:24), normal traffic spreads across
   the full 24h window.** Gives Module 3's correlation engine a real
   time-based signal to work with, and makes the timeline UI in Module 6 look
   coherent instead of noisy.
3. **Config-change host may be the cluster's host OR a topology-adjacent
   neighbor** (70% / 30% split, seeded). This is what lets Module 3
   distinguish "change on the compromised host itself" from "change in the
   blast radius."
4. **Timestamps are ISO-8601 strings, not native datetimes.** SQLite has no
   datetime type; strings are lexicographically sortable and what SQLite would
   store anyway. Module 2/3 should parse with `datetime.fromisoformat()`.
5. **`log_id == flow_id`, one-to-one.** No join gymnastics needed to correlate
   a log with its underlying flow.

---

## 6. Configuration (Tweakables)

All tuneable constants live in one block at the top of `generate_multisource.py`
(Section 1). Most are safe to change:

| Constant | Default | What it controls |
|---|---|---|
| `SEED` | `42` | RNG seed for all randomness. Change → different DB, still reproducible. |
| `MAX_ROWS` | `None` | Set to e.g. `20000` for fast dev iteration on a subset. |
| `DEMO_DATE` | `2026-07-14 00:00:00` | Anchor date for synthetic timestamps. |
| `WINDOW_HOURS` | `24` | Total demo window. |
| `CONFIG_CHANGE_INJECTION_RATE` | `0.35` | % of attack clusters that receive a config-change. |
| `CONFIG_CHANGE_ADJACENT_HOST_PROBABILITY` | `0.30` | Chance a change lands on a topology neighbor instead of the cluster host. |
| `CLUSTER_TIME_WINDOW_MINUTES` | `10` | Max gap between attack flows to count as one cluster. |

Changing the topology itself → edit `TOPOLOGY_DEFINITION` in Section 6.

---

## 7. Troubleshooting

### `FileNotFoundError: Dataset file not found: data/raw/UNSW_NB15_training-set.parquet`
Source files aren't in `data/raw/`. Copy them in per Setup step 3.

### `SchemaValidationError: Required columns missing`
A source file was swapped for one with a different schema. Check that both
parquet files have at least the columns `proto`, `service`, `state`, and one
of `attack_cat` / `label`. The full expected schema is in Section 1
(`REQUIRED_COLUMNS`, `LABEL_COLUMNS`, `FEATURE_COLUMNS`).

### `ModuleNotFoundError: No module named 'pyarrow'`
Parquet needs pyarrow. `pip install -r requirements.txt` should install it —
if you skipped that, run it now.

### `[FAIL] every flow host exists in topology`
Someone edited `TOPOLOGY_DEFINITION` to remove a node that host mapping relied
on. Add it back, or update the host-mapping logic in Section 7.

### `[FAIL] config-changes precede their attack clusters`
Timestamp math in Section 5 or Section 8 drifted. Re-check `_linear_offsets`
and `CONFIG_CHANGE_LEAD_MINUTES_*` constants.

### Script hangs on the "Generating logs" tqdm bar for >2 minutes
Row-level Python loop; ~5,000 rows/sec is normal. 258k rows ≈ 60 seconds. If
it's much slower, check that pandas isn't in some degraded mode (e.g. running
inside a debugger with tracing enabled).

---

## 8. Handing Off to Module 2 / Module 3

Downstream modules should connect to `data/processed/rca.db` and query the
four tables directly. Important contracts:

- **`flow_id`** is the join key between `flows` and `synthetic_logs`.
- **`host_id`** is the join key between `flows` / `synthetic_config_changes` /
  `synthetic_logs` and `synthetic_topology.node_id`.
- **`synthetic_topology.adjacent_nodes`** is stored as a JSON array string;
  parse with `json.loads()`.
- **All `ts` columns are ISO-8601 strings**, sortable as text or parseable
  via `datetime.fromisoformat()`.

Indexes are pre-built on `host_id` and `ts` for all relevant tables — SQL
queries filtering on either will be fast.

---

## 9. Regenerating

The script is fully idempotent. To regenerate from scratch:

```bash
python3 synth/generate_multisource.py
```

The old `rca.db` is dropped and recreated in a single transaction — you never
end up with a half-populated DB even if you Ctrl+C mid-write.

To clear logs too:

```bash
rm data/processed/rca.db logs/generate_multisource.log
python3 synth/generate_multisource.py
```
