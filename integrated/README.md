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

## 📑 Table of Contents

- [Overview](#-overview)
- [Problem Statement](#-problem-statement)
- [Why This Project](#-why-this-project)
- [Key Features](#-key-features)
- [System Architecture](#-system-architecture)
- [Complete Pipeline](#-complete-pipeline)
- [Technology Stack](#-technology-stack)
- [Module Responsibilities](#-module-responsibilities)
- [Folder Structure](#-folder-structure)
- [Working Flow](#-working-flow)
- [Explainable & Agentic AI](#-explainable--agentic-ai)
- [Dashboard Features](#-dashboard-features)
- [API Overview](#-api-overview)
- [Installation](#-installation)
- [Local Setup](#-local-setup)
- [Running the Project](#-running-the-project)
- [Screenshots](#-screenshots)
- [Future Enhancements](#-future-enhancements)
- [Contributors](#-contributors)

---

## 🔍 Overview

The **Network Anomaly Root-Cause Assistant** is a single-machine integration of
seven modules into one coherent pipeline built over a single SQLite database
(`data/processed/rca.db`). It takes raw network-flow data, scores each flow for
attacks, clusters the anomalies into incidents, gathers supporting evidence,
and runs a **LangGraph agent** that proposes and *validates* root-cause
hypotheses before ranking them and recommending remediation.

Every step is deliberately **deterministic and auditable**. The machine
learning, evidence grounding, and hypothesis ranking never depend on an LLM —
the language model is used *only* to write the human-readable narrative and
remediation text, and even that has a fully offline template fallback so the
system can run with no API key and no network.

The whole thing is exposed through a FastAPI backend and a vanilla-JS +
D3.js dashboard styled as a **SOC Command Center**.

---

## 🎯 Problem Statement

Security analysts drown in anomaly alerts but lack the context to answer the
question that actually matters: **"What caused this, and what do I do about
it?"**

- Raw anomaly detectors flag *symptoms* (a suspicious flow) but not *causes*.
- Root-cause analysis requires correlating anomalies with infrastructure
  changes and network topology — usually done manually.
- AI-generated explanations are frequently **ungrounded**: they hallucinate
  causes and cite evidence that does not exist.
- When evidence is genuinely missing, most tools quietly invent a plausible
  story instead of admitting the gap.

This project addresses those gaps by pairing explainable ML detection with a
correlation engine and an agent that is **structurally prevented** from
asserting a root cause it cannot back with real evidence and a real topology
path.

---

## 💡 Why This Project

- **Grounding over fluency.** The agent rejects any hypothesis that cites
  non-existent evidence, relies only on *missing* evidence, or has no topology
  path to the affected node. Rejections are shown to the analyst with reasons.
- **Explainability everywhere.** Each prediction ships with SHAP feature
  contributions, so an analyst can see *why* a flow was flagged.
- **Honest about gaps.** The synthetic data intentionally leaves ~65% of
  attack clusters with no configuration-change evidence, forcing the pipeline
  to report `missing` evidence rather than fabricate a cause.
- **Reproducible & offline-safe.** Fixed seeds, a shipped pre-built database,
  and a deterministic LLM fallback mean the pipeline produces the same output
  every run, with or without a network connection.
- **Full audit trail.** Every mutating action writes an `audit_log` row.

---

## ✨ Key Features

| Feature | Description |
|---|---|
| **Explainable anomaly detection** | XGBoost multiclass + binary classifiers with SHAP `TreeExplainer` top-feature attribution per flow. |
| **Incident correlation** | Groups anomalous flows into incidents by time window + shared host; assigns severity by flow volume. |
| **Evidence bucketing** | Classifies evidence as `confirmed`, `correlated`, or `missing` using host-direct and topology-adjacent config changes plus repeat-connection signals. |
| **Grounded agentic reasoning** | A LangGraph state machine generates → ground-checks → (optionally revises) → ranks hypotheses and recommends remediation. |
| **Topology-aware root cause** | Root-cause candidates are validated against Module 1's real dependency graph (impact paths, blast radius). |
| **Live single-flow scoring** | `POST /score` runs the ML models + SHAP on an ad-hoc flow in real time. |
| **Audit trail** | Structured `audit_log` on every hypothesis generation, review decision, and live score. |
| **SOC dashboard** | Nine interactive views: analytics, incident desk, evidence matrix, reasoning console, what-if simulator, knowledge graph, network topology, timeline, and SIEM audit console. |

---

## 🏗 System Architecture

```
                         ┌──────────────────────────────────────────┐
                         │        rca.db  (single SQLite file)       │
                         │  flows · synthetic_topology · logs ·      │
                         │  config_changes · anomaly_scores ·        │
                         │  topology · incidents · incident_flows ·  │
                         │  evidence · hypotheses · audit_log        │
                         └──────────────────────────────────────────┘
                                          ▲   ▲   ▲
       ┌──────────────┐   writes flows    │   │   │
       │  M1  Synth    │───────────────────┘   │   │
       │  Generator    │  (UNSW-NB15 parquet)  │   │
       └──────────────┘                        │   │
                                               │   │
       ┌──────────────┐  writes anomaly_scores │   │
       │  M2  Detect   │────────────────────────┘   │
       │  XGBoost+SHAP │                            │
       └──────────────┘                            │
                                                   │
       ┌──────────────┐  writes incidents /        │
       │  M3  Correlate│  evidence / incident_flows │
       │  + M5 Timeline│───────────────────────────┘
       └──────────────┘
              │  incident bundle (adapters/)
              ▼
       ┌──────────────┐  writes hypotheses + audit_log
       │  M4  LangGraph│─────────────────────────────►
       │  Agent + LLM  │
       └──────────────┘
              │
              ▼
       ┌──────────────┐        HTTP/JSON        ┌──────────────┐
       │  M7  FastAPI  │◄───────────────────────►│  M6 Dashboard │
       │  + audit_log  │      (12 endpoints)     │  D3 / vanilla │
       └──────────────┘                         └──────────────┘
```

---

## 🔄 Complete Pipeline

```
 UNSW-NB15 parquet (train + test)
          │
          ▼
 ┌─────────────────────────────────────────────────────────────┐
 │ M1  synth/generate_multisource.py                            │
 │  • deterministic timestamps (seed=42, 24h demo window)       │
 │  • 20-node enterprise topology (firewall→web→app→db…)        │
 │  • host placement by (proto, service, state) hash            │
 │  • synthetic config-change events (~35% injection rate)      │
 │  • syslog-style log line per flow                            │
 └─────────────────────────────────────────────────────────────┘
          │  flows, synthetic_topology, config_changes, logs
          ▼
 ┌─────────────────────────────────────────────────────────────┐
 │ db/setup_integration.py                                      │
 │  • applies downstream schema  • builds directed topology edges│
 └─────────────────────────────────────────────────────────────┘
          ▼
 ┌─────────────────────────────────────────────────────────────┐
 │ M2  ml/train.py  →  ml/detect_events.py                      │
 │  • XGBoost multiclass (10 classes) + binary, balanced weights│
 │  • batch-scores test split  • SHAP top-5 features per flow   │
 └─────────────────────────────────────────────────────────────┘
          │  anomaly_scores
          ▼
 ┌─────────────────────────────────────────────────────────────┐
 │ M3  correlation/evidence_engine.py                           │
 │  • cluster anomalies → incidents (time-window + shared host) │
 │  • evidence: confirmed / correlated / missing                │
 │  • repeat-connection (ct_*_ltm) causation signal             │
 │  • impact paths over the real topology                       │
 └─────────────────────────────────────────────────────────────┘
          │  incidents, incident_flows, evidence
          ▼
 ┌─────────────────────────────────────────────────────────────┐
 │ adapters/  →  M4  agent/graph.py (LangGraph)                 │
 │  generate_hypotheses → ground_check → [revise] →             │
 │  rank_hypotheses → recommend_next_steps                      │
 └─────────────────────────────────────────────────────────────┘
          │  hypotheses, audit_log
          ▼
 ┌─────────────────────────────────────────────────────────────┐
 │ M7  api/main.py (FastAPI)  ─►  M6  frontend/ dashboard        │
 └─────────────────────────────────────────────────────────────┘
```

Orchestrate the analytic stages end-to-end with `run_pipeline.py`.

---

## 🧰 Technology Stack

Detected directly from the codebase (`requirements.txt`, imports, and vendored assets):

**Backend & Language**
- Python 3.10+
- FastAPI + Uvicorn (single service, CORS enabled)
- Pydantic v2 (typed agent state & request bodies)
- SQLite (single-file database, accessed via the stdlib `sqlite3`)

**Machine Learning / Explainable AI**
- XGBoost (multiclass + binary classifiers)
- scikit-learn (`ColumnTransformer`, `OneHotEncoder`, `StandardScaler`, `LabelEncoder`, balanced sample weights, metrics)
- SHAP (`TreeExplainer` feature attribution)
- joblib (model + preprocessor artifact persistence)
- NumPy / pandas / PyArrow (data handling, parquet I/O)

**Agentic AI**
- LangGraph (`StateGraph` reasoning workflow with a conditional revision loop)
- Groq SDK (live LLM narratives; default model `openai/gpt-oss-120b`)
- Deterministic template fallback (no key / no network required)
- python-dotenv (config)

**Graph / Topology**
- NetworkX (topology construction, adjacency, shortest-path grounding, impact paths)

**Frontend / Dashboard**
- Vanilla JavaScript (ES modules, component classes)
- D3.js (charts, knowledge graph, topology map — vendored)
- anime.js (UI animation — vendored)
- HTML5 + CSS (custom SOC theme)

**Data**
- UNSW-NB15 network intrusion dataset (train + test parquet)

---

## 🧩 Module Responsibilities

| Path | Module | Responsibility |
|---|---|---|
| `synth/generate_multisource.py` | **M1 — Synthetic Generator** | Loads UNSW-NB15 parquet, validates schema, assigns deterministic timestamps, builds a 20-node enterprise topology, maps each flow to a host, injects config-change events (~35% of clusters), generates syslog lines, and writes everything to `rca.db`. Idempotent, seeded, self-validating. |
| `db/setup_integration.py` | **Integration setup** | Applies `schema_downstream.sql` (adds ML/correlation/agent/audit tables on top of M1's tables) and rebuilds the directed `topology` edge table from M1's real dependency definition. |
| `ml/train.py` | **M2 — Training** | Trains XGBoost multiclass (10 attack classes) and binary models with balanced sample weights; fits the preprocessor and label encoder; saves all artifacts as `.joblib`. |
| `ml/detect_events.py` | **M2 — Detection + SHAP** | Loads artifacts, batch-scores the test split, computes SHAP top-5 features per flow, and writes `anomaly_scores`. Also exposes `score_flow` / `explain_flow_shap` for live single-flow scoring. |
| `correlation/evidence_engine.py` | **M3 — Correlation & Evidence** | Clusters anomalous flows into incidents (time-window + shared host), buckets evidence into confirmed/correlated/missing (host-direct + topology-adjacent config changes, repeat-connection signal), and computes topology impact paths. |
| `correlation/timeline.py` | **M5 — Timeline** | Merges an incident's flows, logs, and evidence-linked config changes into one chronological timeline for the UI. |
| `agent/schemas.py` | **M4 — Schemas** | Pydantic models for evidence items, hypotheses, remediation steps, and the `IncidentState` that flows through the graph. |
| `agent/graph.py` | **M4 — LangGraph agent** | The five-node reasoning workflow: deterministic hypothesis scoping, a 100% deterministic ground-check gate, a bounded revision loop, deterministic ranking, and remediation recommendation. |
| `agent/llm_engine.py` | **M4 — LLM bridge** | Chooses live Groq vs. deterministic template narratives/remediation; guarantees the pipeline never hard-fails on a missing key or flaky network. |
| `agent/llm_layer.py` | **M4 — Groq layer** | Direct Groq API calls for narrative and remediation JSON (used only when `GROQ_API_KEY` is set). |
| `agent/topology.py` | **M4 — Topology helper** | Loads M1's real graph from `rca.db`; provides impact paths, path-existence checks for grounding, and a serializable graph for the frontend. |
| `adapters/bundle.py` | **Adapter** | Builds the M4-ready incident bundle from the DB, aggregating per-flow SHAP into per-incident feature weights and mapping M3 evidence shape → M4 contract. |
| `adapters/pipeline.py` | **Service layer** | Runs the agent for a given incident, persists ranked hypotheses + remediation, and writes the audit row. Reused by the batch orchestrator and the API. |
| `api/main.py` | **M7 — API** | FastAPI service exposing incidents, evidence, timeline, topology, hypotheses regeneration, review, audit log, live scoring, stats, and analytics; also serves the dashboard. |
| `api/db.py` | **M7 — DB helpers** | Shared SQLite connection factory and the `write_audit` helper every mutating action calls. |
| `frontend/` | **M6 — Dashboard** | The SOC Command Center: an ES-module component app driven by D3.js and anime.js over the API. |
| `run_pipeline.py` | **Orchestrator** | Runs M2 → M3 → M4 in order and seeds hypotheses for every incident. Idempotent. |

> ⚠️ **Legacy / unused files.** `ml/incident_db.py` and `db/schema_original_m3.sql`
> define an **earlier, different schema** that predates the integrated build and
> is **not** used by the current pipeline (the live schema lives in
> `db/schema_downstream.sql`). Similarly, `frontend/index_m4_original.html` and a
> couple of standalone scripts under `frontend/js/` are earlier prototypes;
> `frontend/index.html` is the active dashboard. These are kept for reference and
> can be removed without affecting the running system.

---

## 📂 Folder Structure

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

---

## ⚙️ Working Flow

1. **Generate data (M1).** `generate_multisource.py` builds `rca.db` from the
   UNSW-NB15 parquet files, adding timestamps, topology, hosts, config changes,
   and logs — all deterministically.
2. **Set up schema.** `db.setup_integration` layers the downstream tables and
   builds the directed topology edge table from the real graph.
3. **Detect (M2).** `train.py` fits and saves the models; `detect_events.py`
   batch-scores the test split, storing predictions, confidences, and SHAP
   top-features in `anomaly_scores`.
4. **Correlate (M3 / M5).** `evidence_engine.py` clusters anomalies into
   incidents and buckets evidence; `timeline.py` assembles per-incident
   timelines on demand.
5. **Reason (M4).** For each incident, `adapters/` builds a bundle and
   `agent/graph.py` runs the LangGraph workflow to produce grounded, ranked
   hypotheses plus remediation, persisting them and writing an audit row.
6. **Serve (M7).** FastAPI exposes everything as JSON and serves the dashboard.
7. **Investigate (M6).** The analyst browses incidents, inspects evidence and
   SHAP, re-runs the reasoning engine, approves/rejects incidents (audited),
   and explores the topology and timeline.

---

## 🧠 Explainable & Agentic AI

### Explainable AI (SHAP)

- The multiclass XGBoost model is wrapped in a SHAP `TreeExplainer`.
- Every scored flow stores its **top-5 feature contributions** in
  `anomaly_scores.shap_top_features`.
- The adapter aggregates per-flow SHAP into **per-incident feature weights**,
  which feed the agent's ranking node and the dashboard's explainability views.
- `POST /score` returns live SHAP contributions for any ad-hoc flow.

### Agentic AI (LangGraph)

The agent is a five-node `StateGraph`. Critically, **detection, grounding, and
ranking are 100% deterministic Python** — the LLM only writes narrative text.

```
        ┌────────────────────┐
        │ generate_hypotheses│  deterministic node scoping;
        │  (LLM narrative)   │  one hypothesis per candidate node
        └─────────┬──────────┘
                  ▼
        ┌────────────────────┐
        │   ground_check     │  reject if: cites unknown evidence,
        │ (deterministic gate)│  only cites 'missing' evidence, or
        └─────────┬──────────┘  no topology path (≤ 3 hops)
                  │
        ungrounded│ & loop_count < 2
                  ▼
        ┌────────────────────┐
        │ revise_hypothesis  │  strip ungrounded claims,
        │  (bounded loop)    │  re-enter ground_check
        └─────────┬──────────┘
                  ▼ (all grounded, or loop budget spent)
        ┌────────────────────┐
        │  rank_hypotheses   │  score = confirmed·0.45 + correlated·0.20
        │  (deterministic)   │       − missing·0.10 + primary-node bonus
        └─────────┬──────────┘       + SHAP weight
                  ▼
        ┌────────────────────┐
        │recommend_next_steps│  LLM/template remediation for the
        │  (LLM remediation) │  top-ranked grounded hypothesis
        └────────────────────┘
```

**Grounding rules enforced in code (`agent/graph.py`):**

1. A hypothesis citing an evidence ID that does not exist is rejected.
2. A hypothesis citing *only* `missing` evidence is rejected ("cannot assert a
   root cause from an absence").
3. A root-cause node with no dependency path to the affected node within
   `MAX_HOPS = 3` is rejected.

The revision loop is bounded (`MAX_LOOP_ITERATIONS = 2`) so it always
terminates. Ungrounded hypotheses are surfaced to the analyst with their
rejection reason rather than hidden.

### LLM provider

- When `GROQ_API_KEY` is set, narratives and remediation are generated live via
  Groq (default model `openai/gpt-oss-120b`, overridable with `GROQ_MODEL`).
- Otherwise the system falls back to **deterministic templates** — fully
  offline, fully reproducible, and unable to hard-fail.

> Note: several agent functions are named `call_claude_*` / `mock_*` for
> historical reasons; the live provider is **Groq**, and grounding/ranking are
> provider-independent.

---

## 📊 Dashboard Features

The **SOC Command Center** (`frontend/`) is a component-based ES-module app that
consumes the API only — no fabricated data. Nine views:

| View | What it shows |
|---|---|
| **Analytics Dashboard** | KPI cards + D3 charts over real DB aggregations (`/stats`, `/analytics`): protocol/service/state distributions, predicted-attack mix, confidence histograms, SHAP top-feature frequency, evidence buckets, incidents by severity/host/time. |
| **Incident Desk** | Sortable, filterable, searchable incident table with derived root-cause node, confidence, and review status. |
| **Incident Details** | Ingestion summary, live SHAP profile card, and the **Evidence Matrix** (confirmed vs. correlated vs. coverage gaps). |
| **Hypotheses Engine** | Runs the reasoning engine on demand, renders ranked hypotheses (grounded/rejected, confidence bars, cited evidence, tier weights) and the grounding **trace log**. |
| **What-if Simulator** | Interactive single-flow scoring against the live XGBoost + SHAP models. |
| **Knowledge Graph** | D3 graph linking incident → evidence → suggested actions, with a node inspector. |
| **Network Topology** | Interactive map of the enterprise topology / blast-radius impact path. |
| **Incident Timeline** | Chronological flow/log/config-change events for the selected incident. |
| **Security SIEM Logs** | Auto-refreshing audit console with approve/reject actions and CSV export. |

---

## 🌐 API Overview

FastAPI service (`api/main.py`), served from the project root. Every **mutating**
call writes an `audit_log` row.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/incidents` | List incidents (filter by `attack_cat`, `severity`). |
| `GET` | `/incidents/{id}` | Full detail: evidence (bucketed), timeline, hypotheses, impact path. |
| `POST` | `/incidents/{id}/hypotheses/regenerate` | Re-run the M4 agent for the incident *(mutating → audited)*. |
| `GET` | `/incidents/{id}/timeline` | Ordered event timeline. |
| `GET` | `/incidents/{id}/topology` | Impact-path subgraph for the incident's node. |
| `POST` | `/incidents/{id}/review` | Approve / reject an incident *(mutating → audited)*. |
| `GET` | `/audit-log/{id}` | Audit trail for one incident. |
| `GET` | `/audit-log` | Global audit feed (read-only, `limit` param). |
| `POST` | `/score` | Live single-flow scoring + SHAP *(mutating → audited)*. |
| `GET` | `/stats` | Dashboard summary counts. |
| `GET` | `/analytics` | Read-only aggregations powering the analytics charts. |
| `GET` | `/` | Serves the dashboard (`frontend/index.html`). |

---

## 📦 Installation

**Prerequisites:** Python 3.10+ and `pip`.

```bash
# clone your fork / copy of this repository, then:
cd integrated
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

---

## 🛠 Local Setup

Optional — only needed for **live** LLM narratives:

```bash
cp .env.example .env
# edit .env and set:
#   GROQ_API_KEY=your_key_here
#   GROQ_MODEL=openai/gpt-oss-120b   # optional override
```

Without a key, the agent uses deterministic template narratives automatically.

**Data:** `data/raw/` already contains the UNSW-NB15 parquet files, and
`data/processed/rca.db` **ships pre-built and pre-populated**, so you can run the
app immediately. To regenerate everything from scratch:

```bash
python synth/generate_multisource.py     # builds rca.db from the parquet files
python run_pipeline.py                    # M2 → M3 → M4, seeds all hypotheses
```

To re-run only the agent over the existing incidents:

```bash
python run_pipeline.py --agent
```

---

## ▶️ Running the Project

Start the API + dashboard (from the project root):

```bash
uvicorn api.main:app --port 8000
```

Then open:

```
http://127.0.0.1:8000
```

- Interactive API docs (Swagger UI): `http://127.0.0.1:8000/docs`

---

## 🖼 Screenshots

> _Placeholders — add real captures here._

| View | Screenshot |
|---|---|
| Analytics Dashboard | `![Analytics](docs/screenshots/analytics.png)` |
| Incident Desk | `![Incidents](docs/screenshots/incidents.png)` |
| Evidence Matrix | `![Evidence](docs/screenshots/evidence.png)` |
| Hypotheses Engine | `![Hypotheses](docs/screenshots/hypotheses.png)` |
| Network Topology | `![Topology](docs/screenshots/topology.png)` |
| SIEM Audit Console | `![Audit](docs/screenshots/audit.png)` |

---

## 🚀 Future Enhancements

- **Streaming / live ingestion** instead of batch-scoring a fixed test split.
- **Persisted timeline & impact paths** (currently computed per request).
- **Retrieval-grounded LLM narratives** with citation verification against the DB.
- **Multi-user auth & role-based review** on top of the existing audit trail.
- **Model retraining loop** driven by analyst approve/reject feedback.
- **Configurable topology import** from real CMDB / infrastructure sources.
- **Remove legacy modules** (`ml/incident_db.py`, `schema_original_m3.sql`,
  prototype frontend files) once fully deprecated.
- **Automated test suite** covering grounding rules and evidence bucketing.

---

## 👥 Contributors

<!-- Add contributor names, roles, and links below. -->

| Name | Role | Contact |
|---|---|---|
| _TBD_ | Module 1 — Synthetic Generator | _—_ |
| _TBD_ | Module 2 — Detection + SHAP | _—_ |
| _TBD_ | Module 3 / 5 — Correlation + Timeline | _—_ |
| _TBD_ | Module 4 — Agent | _—_ |
| _TBD_ | Module 6 / 7 — Dashboard + API | _—_ |

---

<sub>Built as an integrated, single-machine SOC root-cause assistant over the UNSW-NB15 dataset. Detection, grounding, and ranking are deterministic; the LLM writes narrative only.</sub>
