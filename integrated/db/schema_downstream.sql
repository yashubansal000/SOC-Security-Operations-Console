-- ============================================================
-- Downstream schema (M3 / M4 / M7) — layered ON TOP of Module 1's
-- real tables (flows, synthetic_topology, synthetic_config_changes,
-- synthetic_logs). This file NEVER creates or alters M1's tables;
-- it only adds the tables the rest of the pipeline writes.
-- ============================================================

-- M2 output -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS anomaly_scores (
    flow_id           INTEGER PRIMARY KEY,
    attack_cat_pred   TEXT NOT NULL,
    confidence        REAL NOT NULL,
    shap_top_features TEXT
);

-- Directed dependency edges, derived from synthetic_topology.adjacent_nodes
-- + Module 1's real upstream definition. Edge (source -> target) means
-- "target depends on source": if source is compromised, target is downstream
-- impact. Built by db/setup_integration.py, not by hand.
CREATE TABLE IF NOT EXISTS topology (
    source_node TEXT NOT NULL,
    target_node TEXT NOT NULL,
    PRIMARY KEY (source_node, target_node)
);

-- M3 tables -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS incidents (
    incident_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id      TEXT NOT NULL,
    attack_cat   TEXT NOT NULL,
    start_ts     TEXT NOT NULL,
    end_ts       TEXT NOT NULL,
    flow_count   INTEGER NOT NULL,
    severity     TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_incidents_node ON incidents(node_id);

CREATE TABLE IF NOT EXISTS incident_flows (
    incident_id  INTEGER NOT NULL,
    flow_id      INTEGER NOT NULL,
    PRIMARY KEY (incident_id, flow_id)
);

CREATE TABLE IF NOT EXISTS evidence (
    evidence_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id       INTEGER NOT NULL,
    bucket            TEXT NOT NULL CHECK (bucket IN ('confirmed','correlated','missing')),
    evidence_type     TEXT NOT NULL,
    node_id           TEXT,
    ref_id            INTEGER,
    description       TEXT NOT NULL,
    confidence_weight REAL NOT NULL,
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_evidence_incident ON evidence(incident_id);

-- M4 output -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hypotheses (
    hypothesis_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id       INTEGER NOT NULL,
    rank              INTEGER NOT NULL,
    root_cause_node   TEXT,
    summary           TEXT NOT NULL,
    confidence_pct    REAL NOT NULL,
    evidence_refs     TEXT,
    next_steps        TEXT,
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_hyp_incident ON hypotheses(incident_id);

-- M7 audit trail --------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_log (
    audit_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT NOT NULL DEFAULT (datetime('now')),
    actor        TEXT NOT NULL,
    action       TEXT NOT NULL,
    incident_id  INTEGER,
    details      TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_incident ON audit_log(incident_id);
