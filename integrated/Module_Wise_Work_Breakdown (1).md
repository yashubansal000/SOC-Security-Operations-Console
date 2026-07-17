# Module-Wise Work Breakdown — Network Anomaly Root-Cause Assistant

Each module below lists concrete tasks, deliverables, and a checklist so any team member can pick it up and know exactly what "done" looks like. Owners follow the 5-person split from the team plan.

---

## Module 1 — Data & Synthetic Multi-Source Generator
**Owner:** Member A (Data/ML Engineer) | **Effort:** 4–5 hrs | **Blocks:** everyone else — do this first

**Tasks:**
1. Load `UNSW_NB15_training-set.parquet` + `UNSW_NB15_testing-set.parquet`, confirm schema (36 cols, no nulls).
2. Assign each flow a deterministic synthetic timestamp spread across a fake 24h window (seeded random, so re-runs are reproducible for demo).
3. Build a fixed 15–20 node synthetic topology (`web-tier`, `db-tier`, `dns`, `firewall`, `external-api`, etc.) as a Python dict/JSON — this is your static "topology graph."
4. Write a deterministic mapping function: `hash(proto + service + state) → node_id` so every flow lands on a consistent synthetic host.
5. Identify attack clusters (rows where `attack_cat != 'Normal'`), and for a subset of clusters, inject 1–2 synthetic config-change events in the time window just before the cluster (e.g. "firewall rule modified on node X").
6. Generate one templated log line per flow (Python f-string, not LLM — must be fast): timestamp, host, proto, service, state, byte counts.
7. Write everything to SQLite tables: `flows`, `synthetic_topology`, `synthetic_config_changes`, `synthetic_logs`.

**Deliverable:** `synth/generate_multisource.py` — runs once, populates `data/processed/rca.db`.

**Checklist:**
- [ ] All 4 tables populated and queryable
- [ ] Topology has real adjacency (nodes depend on other nodes, not isolated)
- [ ] Config-change events only appear near actual attack clusters (not random noise)
- [ ] Script is idempotent / re-runnable without duplicating rows

---

## Module 2 — Anomaly Detection Engine
**Owner:** Member A (Data/ML Engineer) | **Effort:** 5–6 hrs | **Depends on:** M1 schema (not data)

**Tasks:**
1. Encode categoricals (`proto`, `service`, `state`) — one-hot or target encoding.
2. Train a multiclass XGBoost/LightGBM model on `attack_cat` (9 classes) using the provided train split.
3. Train a simpler binary fallback model on `label` (0/1) as a sanity check / secondary signal.
4. Evaluate on the provided test split — capture accuracy, F1 per class, confusion matrix (you'll want these numbers for the pitch deck).
5. Wire up SHAP (`TreeExplainer`) to compute top-N feature contributions per prediction.
6. Batch-score the full test set once, write results to `anomaly_scores` table.
7. Wrap single-record scoring in a function reusable by the `/score` live-demo endpoint later.

**Deliverable:** `ml/train.py`, `ml/model.pkl`, `ml/shap_explain.py`.

**Checklist:**
- [ ] Model F1 ≥ 0.90 on multiclass (published UNSW-NB15 baselines hit 93–97%, so this is achievable)
- [ ] SHAP values returned as `[{feature, contribution}]` JSON-serializable list
- [ ] `anomaly_scores` table populated for full test set
- [ ] Single-flow scoring function tested with a hand-crafted "obvious attack" row for demo

---

## Module 3 — Correlation & Evidence Engine
**Owner:** Member B (Backend/Correlation Engineer) | **Effort:** 5 hrs | **Depends on:** M1 + M2 output

**Tasks:**
1. Design and create the SQLite schema (`incidents`, `evidence`, plus finalize M1/M2 table shapes with A).
2. Write incident-clustering logic: group anomalous flows into incidents using time-window + shared-synthetic-host rules (e.g., 3+ anomalies on same host within 10 min = 1 incident).
3. For each incident, check for a synthetic config-change on the same host or a topology-adjacent node in the prior window.
4. Classify each piece of evidence into exactly one bucket: `confirmed` (direct causal link, e.g. config-change on the exact host), `correlated` (time/topology co-occurrence without direct proof), or `missing` (no config-change record exists at all — flag explicitly, never assume).
5. Use `ct_src_dport_ltm` / `ct_dst_sport_ltm` repeat-connection counters as a causation-strengthening signal — this is your literal answer to "avoid simple time-based blame."
6. Build the topology impact-path function using `networkx` (given an incident's host, walk the adjacency graph to find downstream dependents).

**Deliverable:** `correlation/evidence_engine.py`, finalized `db/schema.sql`.

**Checklist:**
- [ ] Every incident has at least one evidence item, correctly bucketed
- [ ] No hypothesis-relevant fact is asserted without an evidence row backing it
- [ ] Impact-path function returns a valid subgraph for any incident's host
- [ ] Schema reviewed and shared with D (API) and C (agent) before they build against it

---

## Module 4 — Root-Cause Agent Layer (LangGraph)
**Owner:** Member C (AI/Agent Engineer) | **Effort:** 6–7 hrs | **Depends on:** M3 evidence bundle shape (can start on mocked data before M3 is done)

**Tasks:**
1. Define the LangGraph state schema: `{incident_id, evidence_bundle, shap_features, candidate_hypotheses, grounded_hypotheses, ranked_hypotheses, final_output}`.
2. Build `generate_hypotheses` node — LLM call (Claude API), forced structured JSON output, 3–5 candidate causes per incident.
3. Build `ground_check` node — **deterministic Python, not LLM** — cross-references every claim in each hypothesis against the evidence bundle; rejects/flags unsupported claims.
4. Build `revise_hypothesis` node — loops back to strip ungrounded claims and reclassify them as "missing evidence"; cap at 2 loop iterations to avoid a demo hang.
5. Build `rank_hypotheses` node — deterministic scoring function combining evidence count, evidence confidence, and SHAP feature weight. Output the 91%/54%/21%-style confidence numbers for the UI.
6. Build `recommend_next_steps` node — LLM call producing diagnostic + remediation text, templated per `attack_cat` bucket for speed/consistency.
7. Wire the full graph together and test end-to-end against 3–4 real incidents from M3.

**Deliverable:** `agent/graph.py`, `agent/prompts.py`, `agent/schemas.py` (Pydantic output models).

**Checklist:**
- [ ] Every hypothesis in final output cites at least one evidence ref
- [ ] Ground-check node demonstrably rejects/revises at least one hallucinated claim in testing (prove this works, don't assume)
- [ ] Ranking produces distinct, sensible confidence percentages, not clustered near 50%
- [ ] Full graph runs in a demo-safe time (a few seconds, not 30+)

---

## Module 5 — Incident Timeline Builder
**Owner:** Member C (AI/Agent Engineer, folded into M4 downtime) | **Effort:** 1–2 hrs | **Depends on:** M1 + M3

**Tasks:**
1. Write a query/function that merges `flows`, `synthetic_config_changes`, and `synthetic_logs` for a given `incident_id`, sorted by timestamp.
2. Tag each event with its source type (`flow` / `config_change` / `log`) so the UI can color-code them.
3. Return as a clean JSON list ready for the frontend timeline component.

**Deliverable:** function inside `correlation/evidence_engine.py` or a small standalone `timeline.py`.

**Checklist:**
- [ ] Timeline is chronologically ordered and includes all 3 source types where present
- [ ] Output format matches what E (frontend) expects (confirm early)

---

## Module 6 — Dashboard / UI
**Owner:** Member E (Frontend Engineer) | **Effort:** 10–12 hrs | **Depends on:** M7 API contract (build against mocks first)

**Tasks:**
1. Set up React + Tailwind project shell, routing (`IncidentList`, `IncidentDetail`).
2. Build `IncidentList` page — table/cards of incidents with severity, `attack_cat`, timestamp.
3. Build `IncidentDetail` page composed of:
   - `EvidencePanel.jsx` — confirmed / correlated / missing evidence, clearly visually separated
   - `HypothesisCard.jsx` — ranked root causes with confidence % (91%/54%/21% style bars)
   - `Timeline.jsx` — chronological event view from M5
   - `TopologyGraph.jsx` — mini impact-path graph (use `react-flow` or simple SVG)
   - Remediation steps section
   - Approve/Reject buttons wired to `/incidents/{id}/review`
4. Style the dashboard shell as an **"Incident Command Center"** (per the naming inspiration from the reference diagram) — landing page with summary stats via `/stats`.
5. Build the demo lever: a small form hitting `POST /score` to feed a hand-crafted "attack" flow live on stage.
6. Polish pass: loading states, empty states, consistent dark theme.

**Deliverable:** `frontend/` full React app.

**Checklist:**
- [ ] Works end-to-end against real API (not just mocks) before Day 2 evening
- [ ] Evidence bucket separation is visually unambiguous (this is a named judging criterion)
- [ ] Confidence percentages render clearly on hypothesis cards
- [ ] No console errors during a full incident click-through

---

## Module 7 — API Layer & Audit Trail
**Owner:** Member D (Backend/API Engineer) | **Effort:** 4 hrs (API) + 2 hrs (audit trail) | **Depends on:** M3 schema

**Tasks:**
1. Scaffold FastAPI app (`api/main.py`), CORS enabled for the frontend.
2. Implement endpoints:
   - `GET /incidents` (filterable by attack_cat/time range)
   - `GET /incidents/{id}` (full detail: evidence + timeline + hypotheses)
   - `POST /incidents/{id}/hypotheses/regenerate` (re-invokes M4 graph — your demo lever)
   - `GET /incidents/{id}/timeline`
   - `GET /incidents/{id}/topology`
   - `POST /incidents/{id}/review` (human approve/reject)
   - `GET /audit-log/{incident_id}`
   - `POST /score` (live single-flow scoring, calls M2)
   - `GET /stats` (dashboard summary counts)
3. Every write to `hypotheses` or a reviewer action appends a row to `audit_log` (actor, action, timestamp, details) — non-negotiable, this is a named requirement in the problem statement.
4. Return mock/stub JSON for every endpoint on Day 1 morning so E is never blocked, then swap in real DB queries as M1–M4 land.
5. Basic error handling (404s for missing incidents, validation errors).

**Deliverable:** `api/main.py`, `api/routers/*.py`, `api/db.py`.

**Checklist:**
- [ ] All 9 endpoints implemented and returning real data by Day 2 midday
- [ ] Every mutating action produces an audit_log row — verify by querying the table after a demo click-through
- [ ] API contract shared with E in writing (OpenAPI/Swagger docs via FastAPI auto-docs is enough) before Day 1 PM

---

## Cross-Cutting: Demo Prep (All Members, Day 2 midday)
- Seed 3–4 hand-picked incidents that produce visually strong, clearly differentiated root-cause hypotheses (not edge cases).
- Rehearse a live click-through: incident list → detail → evidence → ranked hypotheses → timeline → topology → remediation → approve → audit log confirms it.
- Rehearse the `/score` live-attack lever as your "wow" moment.
- Build the pitch deck (8–10 slides) — architecture diagram, dataset grounding table, model accuracy numbers, live demo screenshots as backup if anything breaks on stage.

---

## Dependency Order (who blocks whom)
```
M1 (A) ──────► M2 (A) ──────► M3 (B) ──────► M4 (C) ──► M5 (C)
   │                              │               │
   └──────────────────────────────┴───► M7 (D) ───┴───► M6 (E)
```
M1 is the single hard blocker — prioritize shipping a rough version of it within the first 3–4 hours even if imperfect, then refine in parallel with everyone else building against it.
