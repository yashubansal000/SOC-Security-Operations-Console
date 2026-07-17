# 🛡️ Network Anomaly Root-Cause Assistant

> An end-to-end SOC (Security Operations Center) assistant that detects network
> anomalies with explainable ML, correlates them into incidents, and produces
> **grounded, ranked root-cause hypotheses** with remediation steps — served
> through a single FastAPI service and an interactive Incident Command Center
> dashboard.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?logo=fastapi&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-single--file-003B57?logo=sqlite&logoColor=white)
![XGBoost](https://img.shields.io/badge/XGBoost-2.0+-EB5E28)
![SHAP](https://img.shields.io/badge/SHAP-Explainable%20AI-6f42c1)
![LangGraph](https://img.shields.io/badge/LangGraph-Agent-1C3C3C)
![Groq](https://img.shields.io/badge/Groq-LLM%20narratives-F55036)
![D3.js](https://img.shields.io/badge/D3.js-Dashboard-F9A03C?logo=d3.js&logoColor=white)

---

## 🔍 Overview

The **Network Anomaly Root-Cause Assistant** is a SOC triage engine that takes raw
network flows all the way to grounded, ranked root-cause hypotheses. It combines:

1. **Explainable ML** — an XGBoost classifier (multiclass + binary) scores flows
   from the UNSW-NB15 dataset; SHAP explains *why* each flow was flagged.
2. **Evidence correlation** — anomalous flows are clustered into incidents and
   evidence is bucketed as `confirmed`, `correlated`, or `missing`, using
   config-change and network-topology data rather than time-based guesswork.
3. **Grounded agentic reasoning** — a LangGraph agent generates hypotheses, but
   all scoping, topology-path validation, and ranking math run in deterministic
   Python. The LLM (Groq) only writes narrative/remediation text, and falls
   back to static templates if no API key is set.
4. **SOC dashboard** — a D3.js/vanilla-JS Incident Command Center with topology
   maps, evidence matrices, a reasoning console, and a live "what-if" scorer.

Everything runs over a single pre-built SQLite database (`rca.db`), so the app
works out of the box, offline, with reproducible output on every run.

---

## ✨ Key Features

| Feature | Description |
|---|---|
| **Explainable anomaly detection** | XGBoost + SHAP `TreeExplainer` top-feature attribution per flow. |
| **Incident correlation** | Groups anomalous flows into incidents by time window + shared host. |
| **Evidence bucketing** | `confirmed` / `correlated` / `missing`, using config changes + topology adjacency + repeat-connection signals. |
| **Grounded agentic reasoning** | LangGraph state machine: generate → ground-check → revise → rank → recommend. |
| **Topology-aware root cause** | Root causes validated against a real dependency graph (impact paths, blast radius). |
| **Incident timeline** | Chronological, source-tagged merge of flows, logs, and config changes. |
| **Live single-flow scoring** | `POST /score` runs the ML models + SHAP on an ad-hoc flow. |
| **Full audit trail** | Every mutating action writes an `audit_log` row. |

---

## 🧰 Technology Stack

- **Backend:** Python 3.10+, FastAPI + Uvicorn, Pydantic v2, SQLite
- **ML / XAI:** XGBoost, scikit-learn, SHAP, joblib, NumPy/pandas/PyArrow
- **Agentic AI:** LangGraph, Groq SDK (LLM narratives), deterministic template fallback
- **Graph:** NetworkX (topology, shortest paths, impact/blast-radius)
- **Frontend:** Vanilla JS (ES modules), D3.js, anime.js, HTML5/CSS
- **Data:** UNSW-NB15 network intrusion dataset

---

## 🏗 System Architecture

Seven modules sit over a single SQLite database (`rca.db`):

```
                         ┌──────────────────────────────────────────┐
                         │        rca.db  (single SQLite file)      │
                         │  flows · synthetic_topology · logs ·     │
                         │  config_changes · anomaly_scores ·       │
                         │  topology · incidents · incident_flows · │
                         │  evidence · hypotheses · audit_log       │
                         └──────────────────────────────────────────┘
                                    ▲    ▲    ▲   ▲
       ┌──────────────┐   writes flows   │    │   │
       │  M1  Synth   │ ─────────────────┘    │   │
       │  Generator   │  (UNSW-NB15 parquet)  │   │
       └──────────────┘                       │   │
                                              │   │
       ┌──────────────┐  writes anomaly_scores│   │
       │ M2  Detect   │ ──────────────────────┘   │
       │ XGBoost+SHAP │                           │
       └──────────────┘                           │
                                                  │
       ┌──────────────┐  writes incidents /       │
       │ M3  Correlate│ evidence / incident_flows │
       └──────────────┘ ──────────────────────────┘
              │  incident bundle (adapters/)
              ▼
       ┌──────────────┐  writes hypotheses + audit_log
       │ M4  LangGraph│ ────────────────────────────►
       │ Agent + LLM  │
       └──────────────┘
              │
              ▼
       ┌──────────────┐        HTTP/JSON        ┌──────────────┐
       │  M7  FastAPI │◄───────────────────────►│ M6 Dashboard │
       │  + audit_log │      (12 endpoints)     │ D3 / vanilla │
       └──────▲───────┘                         └──────────────┘
              │  GET /incidents/{id}/timeline — reads flows / logs /
              │  config_changes directly, assembled on demand
       ┌──────────────┐
       │ M5  Timeline │
       │ (on-demand)  │
       └──────────────┘
```

**Flow, in short:** M1 generates the ground-truth data → M2 detects and
explains anomalies → M3 clusters them into incidents and buckets evidence →
M4's LangGraph agent reasons over that evidence to produce grounded, ranked
root causes → M7 exposes everything as JSON → M6 renders it, pulling M5's
timeline on demand. Orchestrated end-to-end by `run_pipeline.py` (M2 → M3 → M4).

---

## 🧩 Modules at a Glance

| Module | Name | What it does |
|---|---|---|
| **M1** | Synthetic Multi-Source Generator | Loads UNSW-NB15 flow data, adds deterministic timestamps, a 20-node enterprise topology, config-change events, and syslog lines, writing everything to `rca.db`. |
| **M2** | Anomaly Detection Engine | XGBoost (multiclass + binary) scores every flow; SHAP `TreeExplainer` attributes each anomaly to its top contributing features; outputs structured incident objects with severity. |
| **M3** | Correlation & Evidence Engine | Clusters anomalous flows into incidents (time window + shared host) and buckets evidence as `confirmed` / `correlated` / `missing` using config changes, topology adjacency, and repeat-connection signals; computes blast radius via NetworkX. |
| **M4** | Root-Cause Agent Layer (LangGraph) | A cyclic state-machine agent: generates hypotheses → deterministically ground-checks them against real evidence and topology paths → revises failed ones (bounded loop) → ranks by a deterministic score → recommends remediation. LLM (Groq) writes narrative only. |
| **M5** | Incident Timeline Builder | Assembles a chronological, source-tagged timeline (flows, logs, config changes) for an incident, on demand — not persisted to the DB. |
| **M6** | UI Dashboard (Incident Command Center) | A D3.js/vanilla-JS SPA: analytics, incident desk, evidence matrix, reasoning console, what-if scorer, knowledge graph, network topology, timeline, and SIEM audit console. |
| **M7** | API Layer | FastAPI service exposing incidents, evidence, timeline, topology, hypothesis regeneration, review, audit log, live scoring, and analytics; also serves the dashboard. |

---

## 📖 Module Details

### M1 — Synthetic Multi-Source Generator

`synth/generate_multisource.py` loads UNSW-NB15 flow data and enriches it
with a deterministic synthetic layer, writing four tables to `rca.db`:

| Table | Rows (full dataset) | Purpose |
|---|---|---|
| `flows` | ~257,673 | UNSW-NB15 features + synthetic `ts`, `host_id`, `flow_id`, `split` |
| `synthetic_topology` | 20 | Fixed enterprise topology (firewall/DNS/web/app/DB/auth/mail/infra/external) |
| `synthetic_config_changes` | ~50–60 | Infra change events injected before ~35% of attack clusters |
| `synthetic_logs` | ~257,673 | One syslog-style line per flow (INFO/WARN/ERROR) |

**Properties:** deterministic (fixed seed → byte-identical DB), idempotent
(drops/recreates cleanly), fast (~60s on 258k rows), self-validating (10
post-write checks).

**Key design decisions:**
- Only ~35% of attack clusters get a config-change record — the remaining
  65% become genuine "missing evidence" cases for Module 3.
- Attack rows cluster in time (04:00–18:24); normal traffic spreads across
  the full 24h window, giving Module 3 a real time signal.
- A config change's host is the cluster's host **or** a topology-adjacent
  neighbor (70%/30% split) — lets Module 3 distinguish a direct compromise
  from blast-radius exposure.
- Timestamps are ISO-8601 strings; `log_id == flow_id` one-to-one.

Tuneable constants: `SEED` (42), `MAX_ROWS`, `DEMO_DATE`, `WINDOW_HOURS` (24),
`CONFIG_CHANGE_INJECTION_RATE` (0.35), `CONFIG_CHANGE_ADJACENT_HOST_PROBABILITY`
(0.30), `CLUSTER_TIME_WINDOW_MINUTES` (10).

---

### M2 — Anomaly Detection Engine (XGBoost & SHAP)

`ml/train.py` + `ml/detect_events.py`, run in six phases:

1. **Dataset recovery** — reads the `flows` table directly from SQLite,
   validated via `PRAGMA`, reconstructed as a pandas DataFrame.
2. **Preprocessing** — `proto`/`service`/`state` label-encoded; uses Module
   1's `split` column for train/test (falls back to a 70:30 random split).
3. **ML detection** — XGBoost, 100 trees, max depth 6, learning rate 0.1,
   seed 42, log-loss optimization; produces a binary prediction + anomaly
   probability per flow.
4. **Evaluation** — Accuracy/Precision/Recall/F1/Confusion Matrix; confidence
   scores written to `anomaly_scores`.
5. **Explainability** — SHAP `TreeExplainer` on anomalous flows only; top
   contributing features (e.g. `dload`, `sload`, `sinpkt`) stored in
   `anomaly_scores.shap_top_features` and translated into human-readable
   evidence strings. `POST /score` exposes the same SHAP explanation live.
6. **Incident object generation** — predictions become structured incidents
   (ID, timestamp, attack type, confidence, severity, network context, SHAP
   features). Severity: **Critical** (conf > 0.90), **High** (conf > 0.70),
   else **Medium**.

**Outputs:** `anomaly_scores` table and `incidents` table.

---

### M3 — Correlation & Evidence Engine

`correlation/evidence_engine.py` — deterministic structural/behavioral
evidence over time-based guesswork:

1. **Spatiotemporal clustering** — thresholds `anomaly_scores` by confidence,
   groups flows within a time window (default 10 min) and shared `host_id`
   into one incident.
2. **Evidence bucketing:**
   - **Confirmed** — a config change mapped directly to the incident's host
     within the incident window (hard proof).
   - **Correlated** — a config change on a topology-*adjacent* host
     (structural), or elevated repeat-connection counters
     `ct_src_dport_ltm` / `ct_dst_sport_ltm` (behavioral).
   - **Missing** — no structural or behavioral link found; explicitly
     tagged rather than fabricated.
3. **Blast radius calculation** — loads `synthetic_topology` into NetworkX,
   traverses from the compromised host via `build_impact_path()` to map
   reachable dependent nodes.
4. **Evidence bundle assembly** — packages findings into an immutable JSON
   bundle that becomes the strict prompt context for Module 4.

---

### M4 — Root-Cause Agent Layer (LangGraph)

`agent/graph.py`, `agent/schemas.py`, `agent/llm_engine.py`,
`agent/topology.py` — a cyclic `StateGraph` with shared state
(`IncidentState`) and five nodes:

1. **`generate_hypotheses`** — expands scope beyond the triggering node using
   `get_impact_path(max_hops=1)` for immediate topology neighbors; Groq
   writes a narrative hypothesis per node using local evidence.
2. **`ground_check`** — 100% deterministic Python gate. Rejects hypotheses
   citing evidence IDs not in the Module 3 bundle, or lacking a valid
   topology path (`MAX_HOPS = 3`) to the victim node.
3. **`revise_hypothesis`** — bounded correction loop (`MAX_LOOP_ITERATIONS = 2`):
   the LLM strips hallucinated claims, then loops back to `ground_check`.
4. **`rank_hypotheses`** — deterministic scoring: confirmed evidence `+0.45`,
   correlated `+0.30`, missing `−0.05`/`−0.10`, `+0.15` proximity bonus for
   the primary node, `+0.25` from top SHAP feature importance. Clamped to a
   1–99% confidence range and sorted.
5. **`recommend_next_steps`** — the top-ranked grounded hypothesis is sent
   back to the LLM for concrete remediation (e.g. CLI commands).

**LLM provider:** Groq (default `openai/gpt-oss-120b`, overridable via
`GROQ_MODEL`). Without `GROQ_API_KEY`, falls back to deterministic templates
— fully offline, cannot hard-fail.

---

### M5 — Incident Timeline Builder

`correlation/timeline.py` — served on demand via
`GET /incidents/{id}/timeline`, **not persisted** to `rca.db`.

1. **Scope definition** — restricted to the incident's hosts; also checks a
   configurable prior window (default 1 hour) for config changes, since
   causes typically precede symptoms.
2. **Multi-source fetch** — three parallel queries: flow events, syslog
   events, config-change events.
3. **Source tagging** — each event becomes a dict with `timestamp`,
   `source_type` (`flow`/`log`/`config_change`), `node_id`, `details`,
   `raw_id`.
4. **Deterministic sorting** — primary sort by ISO-8601 timestamp, secondary
   tie-break by `source_type` so identical timestamps never reorder.

**Robustness:** graceful partial timelines when a source type is missing;
typed `IncidentNotFoundError` → HTTP 404; malformed rows are logged and
skipped rather than failing the whole build.

---

### M6 — UI Dashboard (Incident Command Center)

`frontend/` — a vanilla HTML5/CSS3/D3.js SPA over the FastAPI endpoints.
Nine views:

| View | What it shows |
|---|---|
| Analytics Dashboard | KPI cards + D3 charts over `/stats` and `/analytics` |
| Incident Desk | Sortable/filterable/searchable incident table |
| Incident Details | Ingestion summary, SHAP profile, Evidence Matrix |
| Hypotheses Engine | Ranked hypotheses, confidence bars, grounding trace log |
| What-if Simulator | Interactive single-flow scoring against live models |
| Knowledge Graph | D3 graph: incident → evidence → suggested actions |
| Network Topology | Interactive topology / blast-radius map |
| Incident Timeline | Chronological flow/log/config-change stream (M5) |
| Security SIEM Logs | Auto-refreshing audit console, approve/reject, CSV export |

Notable UI pieces: a force-directed topology map (amber = anomaly node, red
= downstream blast radius), a bucketed Evidence Matrix, and a **Live Score
Flow** modal calling `POST /score` with real-time SHAP bars.

---

### M7 — API Layer

FastAPI service (`api/main.py`). Every **mutating** call writes an
`audit_log` row.

| Method | Path | Purpose |
|---|---|---|
| GET | `/incidents` | List incidents (filter by `attack_cat`, `severity`) |
| GET | `/incidents/{id}` | Full detail: evidence, timeline, hypotheses, impact path |
| POST | `/incidents/{id}/hypotheses/regenerate` | Re-run M4 agent *(audited)* |
| GET | `/incidents/{id}/timeline` | Ordered event timeline (M5) |
| GET | `/incidents/{id}/topology` | Impact-path subgraph |
| POST | `/incidents/{id}/review` | Approve/reject an incident *(audited)* |
| GET | `/audit-log/{id}` | Audit trail for one incident |
| GET | `/audit-log` | Global audit feed |
| POST | `/score` | Live single-flow scoring + SHAP *(audited)* |
| GET | `/stats` | Dashboard summary counts |
| GET | `/analytics` | Read-only aggregations for charts |
| GET | `/` | Serves the dashboard |

---

## 🚀 Module 4 — Root-Cause Agent Layer (Standalone Demo)

The repo also includes a complete, runnable **standalone** version of Module
4. It simulates the inputs Module 4 would normally receive from Module 1
(topology/synthetic data) and Module 3 (correlation/evidence engine), so the
reasoning layer can be built, tested, and demoed independently.

Given an incident's evidence bundle (a mix of confirmed evidence,
correlated-but-unproven signals, and explicitly-missing evidence), the
LangGraph pipeline runs:

1. **`generate_hypotheses`** — proposes 3–5 candidate root causes via the Groq LLM.
2. **`ground_check`** — deterministic Python that rejects any hypothesis that
   cites a non-existent evidence ID, cites only "missing" evidence, or claims
   a root-cause node with no real topology path to the incident.
3. **`rank_hypotheses`** — deterministic confidence scoring from evidence tier
   counts + SHAP feature weights.
4. **`recommend_next_steps`** — remediation grounded strictly on the
   top-ranked hypothesis.

The demo incident (`INC-1042`) is seeded with a real root cause (a firewall
rule change), a plausible downstream symptom, and two deliberately bad
hypotheses (one hallucinated evidence ID, one disconnected topology node) —
proving the `ground_check` correctly rejects bad LLM guesses and ranks the
true root cause on top.

---

## 📂 Folder Structure

### Integrated project (full pipeline)

```
integrated/
├── synth/
│   └── generate_multisource.py     # M1 — synthetic multi-source generator
├── db/
│   ├── setup_integration.py        # applies downstream schema + topology edges
│   ├── schema_downstream.sql       # ACTIVE schema (M2/M3/M4/M7 tables)
│   └── schema_original_m3.sql      # legacy schema (unused)
├── ml/
│   ├── train.py                    # M2 — train XGBoost models
│   ├── detect_events.py            # M2 — batch scoring + SHAP
│   ├── incident_db.py              # legacy standalone schema (unused)
│   ├── preprocessor.joblib         # saved ColumnTransformer
│   ├── label_encoder.joblib        # saved LabelEncoder
│   ├── model_multiclass.joblib     # saved XGBoost multiclass model
│   ├── model_binary.joblib         # saved XGBoost binary model
│   └── encoded_feature_names.joblib
├── correlation/
│   ├── evidence_engine.py          # M3 — clustering + evidence bucketing
│   └── timeline.py                 # M5 — incident timeline builder
├── agent/
│   ├── schemas.py                  # M4 — Pydantic state & output models
│   ├── graph.py                    # M4 — LangGraph reasoning workflow
│   ├── llm_engine.py               # M4 — live/fallback LLM bridge
│   ├── llm_layer.py                # M4 — Groq API calls
│   └── topology.py                 # M4 — graph loading + grounding helpers
├── adapters/
│   ├── bundle.py                   # DB incident → M4 bundle adapter
│   └── pipeline.py                 # run agent + persist hypotheses/audit
├── api/
│   ├── main.py                     # M7 — FastAPI app (12 endpoints)
│   └── db.py                       # DB connection + audit helper
├── frontend/                       # M6 — SOC Command Center dashboard
│   ├── index.html                  # active dashboard shell
│   ├── styles.css
│   ├── js/
│   │   ├── main.js                 # bootstrap + state coordination
│   │   ├── api.js                  # data layer / store / poller
│   │   ├── charts.js, anim.js
│   │   └── components/             # KpiCards, AnalyticsDashboard,
│   │       │                       # EvidenceMatrix, RootCausePanel,
│   │       │                       # KnowledgeGraph, NetworkTopology,
│   │       │                       # Timeline, ExplainabilityPanel,
│   │       └── …                   # AuditConsole, Sidebar, LandingPage…
│   └── vendor/                     # d3.min.js, anime.min.js
├── data/
│   ├── raw/                        # UNSW-NB15 train/test parquet
│   └── processed/
│       ├── rca.db                  # single SQLite database (ships pre-built)
│       └── all_impact_paths.json   # cached impact paths
├── run_pipeline.py                 # end-to-end orchestrator
├── requirements.txt
└── .env.example                    # GROQ_API_KEY / GROQ_MODEL (optional)
```

> ⚠️ **Legacy / unused files.** `ml/incident_db.py` and
> `db/schema_original_m3.sql` define an earlier schema that predates the
> integrated build and isn't used by the current pipeline (the live schema
> lives in `db/schema_downstream.sql`). Similarly, `frontend/index_m4_original.html`
> and a couple of standalone scripts under `frontend/js/` are earlier
> prototypes; `frontend/index.html` is the active dashboard. These are kept
> for reference and can be removed without affecting the running system.

### Standalone Module 4 demo layout

```
custom_input/
├── synth/                  # M1 — synthetic multi-source data generator
├── db/                     # schema + topology setup
├── ml/                     # M2 — training, detection, SHAP
├── correlation/            # M3 — evidence engine, M5 — timeline builder
├── module4_rca_agent/      # M4 — LangGraph reasoning agent (standalone demo)
│   ├── agent/
│   │   ├── schemas.py      # Pydantic models for the pipeline state
│   │   ├── topology.py     # NetworkX dependency graph + impact-path logic
│   │   ├── llm_engine.py   # Groq API integration for narrative generation
│   │   ├── llm_stub.py     # Deterministic offline fallback
│   │   └── graph.py        # The LangGraph state machine pipeline
│   ├── api/
│   │   └── main.py         # FastAPI app, serves the API + the frontend
│   ├── frontend/           # M6 — SOC Command Center dashboard
│   │   ├── index.html      # Dashboard (topology, evidence, hypothesis cards)
│   │   └── styles.css
│   └── requirements.txt    # Module 4 specific dependencies
├── adapters/                # DB ↔ agent bundle adapters
├── data/                    # raw parquet + processed rca.db
└── run_pipeline.py          # end-to-end orchestrator
```

---

## 📦 Installation

**Prerequisites:** Python 3.10+ and `pip`.

Set up the root virtual environment:

```bash
cd custom_input
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
```

`data/raw/` already contains the UNSW-NB15 parquet files, and
`data/processed/rca.db` ships pre-built and pre-populated. To regenerate
everything from scratch:

```bash
python synth/generate_multisource.py     # builds rca.db from the parquet files
python run_pipeline.py                    # M2 → M3 → M4, seeds all hypotheses
```

For the **standalone Module 4 demo**, install its own dependencies:

```bash
cd module4_rca_agent
pip install -r requirements.txt
```

**Set your Groq API key** for live LLM narratives (get one at the Groq console):

```bash
export GROQ_API_KEY="your-api-key-here"
```

*(Or copy `.env.example` to `.env` inside `module4_rca_agent` and place your
key there.)* Without a key, or if the API fails, the pipeline safely falls
back to offline deterministic stubs.

---

## ▶️ Running the Project

**Full integrated pipeline:**

```bash
uvicorn api.main:app --port 8000
```

Then open `http://127.0.0.1:8000` (Swagger UI at `/docs`).

**Standalone Module 4 demo** (from inside `module4_rca_agent`):

```bash
uvicorn api.main:app --reload --port 8421
```

Then open `http://localhost:8421`, select an incident, and click **Run
Analysis**. The UI shows the topology graph (primary node + causal edges in
amber), a color-coded evidence bundle, ranked hypotheses with confidence
bars (rejected ones greyed out — proving the anti-hallucination check works),
and a raw node-by-node trace log from the LangGraph execution.

---

## 🔄 Integration Notes

- **LLM engine** — Groq API calls are bound by Pydantic JSON schemas; the
  rest of the LangGraph pipeline just consumes standard `Hypothesis` objects,
  so swapping providers only touches `llm_engine.py`/`llm_stub.py`.
- **Real evidence bundle (Module 3)** — replace the dummy incident data with
  a call to Module 3's live DB; as long as the dictionary shape matches
  (`incident_id`, `primary_node`, `attack_cat`, `shap_features`, `evidence`),
  Module 4 processes it seamlessly.
- **Real topology (Module 1/3)** — point `agent/topology.py`'s
  `build_graph()` to wherever the live NetworkX graph is exposed.

**Known simplifications in the standalone demo:** confidence scoring is a
weighted sum rather than a trained model (for transparency), and a caught
LLM hallucination is currently rejected/dropped rather than routed through a
revision loop (planned for the full production `revise_hypothesis` node).

---

<sub>Built as an integrated, single-machine SOC root-cause assistant over the
UNSW-NB15 dataset. Detection, grounding, and ranking are deterministic; the
LLM writes narrative only. For full module-by-module technical details,
design decisions, and API reference, see `SUMMARY_REPORT.md`.</sub>
