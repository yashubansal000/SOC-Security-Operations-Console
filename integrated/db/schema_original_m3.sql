-- ============================================================
-- Network Anomaly Root-Cause Assistant — SQLite Schema
-- Single file: data/processed/rca.db
--
-- Owner of this file: Member B (Module 3), in coordination with
-- Member A (M1/M2) and Member D (M7 API). This is the CONTRACT
-- shared with C (agent) and D (API) — do not change table/column
-- names without a heads-up in the group chat.
-- ============================================================

PRAGMA foreign_keys = ON;

-- ------------------------------------------------------------
-- M1 tables (owned by Member A — included here so M3 code can
-- be written and tested against the correct shape before M1
-- ships. If A's real script produces different column names,
-- update this file, not evidence_engine.py's queries piecemeal.)
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS flows (
    flow_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    source_row_id       INTEGER NOT NULL,       -- index into original UNSW-NB15 df
    dataset_split       TEXT NOT NULL,           -- 'train' | 'test'
    synthetic_ts        TEXT NOT NULL,           -- ISO8601, deterministic synthetic timestamp
    node_id             TEXT NOT NULL,           -- synthetic host, from hash(proto+service+state)
    proto               TEXT,
    service             TEXT,
    state               TEXT,
    attack_cat          TEXT NOT NULL,           -- 'Normal' or one of 9 attack classes
    label               INTEGER NOT NULL,        -- 0/1 binary
    ct_src_dport_ltm     INTEGER,
    ct_dst_sport_ltm     INTEGER,
    -- other raw UNSW-NB15 feature columns are NOT duplicated here;
    -- join back to the parquet by source_row_id if a feature is needed
    UNIQUE(source_row_id, dataset_split)
);
CREATE INDEX IF NOT EXISTS idx_flows_node_ts ON flows(node_id, synthetic_ts);
CREATE INDEX IF NOT EXISTS idx_flows_attack_cat ON flows(attack_cat);

CREATE TABLE IF NOT EXISTS synthetic_topology (
    node_id      TEXT PRIMARY KEY,
    node_type    TEXT NOT NULL,       -- 'web-tier' | 'db-tier' | 'dns' | 'firewall' | 'external-api' | ...
    depends_on   TEXT                 -- comma-separated node_ids this node depends on (adjacency)
);

CREATE TABLE IF NOT EXISTS synthetic_config_changes (
    change_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id      TEXT NOT NULL,
    change_ts    TEXT NOT NULL,       -- ISO8601
    description  TEXT NOT NULL,       -- e.g. "firewall rule modified on node X"
    FOREIGN KEY (node_id) REFERENCES synthetic_topology(node_id)
);
CREATE INDEX IF NOT EXISTS idx_cfg_node_ts ON synthetic_config_changes(node_id, change_ts);

CREATE TABLE IF NOT EXISTS synthetic_logs (
    log_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    flow_id      INTEGER NOT NULL,
    node_id      TEXT NOT NULL,
    log_ts       TEXT NOT NULL,
    log_line     TEXT NOT NULL,
    FOREIGN KEY (flow_id) REFERENCES flows(flow_id)
);
CREATE INDEX IF NOT EXISTS idx_logs_flow ON synthetic_logs(flow_id);

-- ------------------------------------------------------------
-- M2 table (owned by Member A)
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS anomaly_scores (
    flow_id           INTEGER PRIMARY KEY,
    attack_cat_pred   TEXT NOT NULL,
    confidence        REAL NOT NULL,          -- model confidence 0-1 for attack_cat_pred
    binary_pred       INTEGER,                -- fallback model 0/1
    shap_top_features TEXT,                   -- JSON string: [{feature, contribution}, ...]
    FOREIGN KEY (flow_id) REFERENCES flows(flow_id)
);

-- ------------------------------------------------------------
-- M3 tables (owned by Member B — this module)
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS incidents (
    incident_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id         TEXT NOT NULL,          -- primary host the incident is anchored to
    attack_cat      TEXT NOT NULL,          -- dominant attack_cat among clustered flows
    start_ts        TEXT NOT NULL,
    end_ts          TEXT NOT NULL,
    flow_count      INTEGER NOT NULL,       -- number of anomalous flows clustered into this incident
    severity        TEXT NOT NULL,          -- 'low' | 'medium' | 'high' | 'critical' (derived, see engine)
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_incidents_node ON incidents(node_id);
CREATE INDEX IF NOT EXISTS idx_incidents_ts ON incidents(start_ts);

-- Links each anomalous flow to the incident it was clustered into
CREATE TABLE IF NOT EXISTS incident_flows (
    incident_id  INTEGER NOT NULL,
    flow_id      INTEGER NOT NULL,
    PRIMARY KEY (incident_id, flow_id),
    FOREIGN KEY (incident_id) REFERENCES incidents(incident_id),
    FOREIGN KEY (flow_id) REFERENCES flows(flow_id)
);

CREATE TABLE IF NOT EXISTS evidence (
    evidence_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id     INTEGER NOT NULL,
    bucket          TEXT NOT NULL CHECK (bucket IN ('confirmed', 'correlated', 'missing')),
    evidence_type   TEXT NOT NULL,          -- 'config_change' | 'repeat_connection' | 'topology_adjacency' | 'no_config_change_found'
    node_id         TEXT,                   -- node this evidence pertains to (may differ from incident's primary node)
    ref_id          INTEGER,                -- e.g. change_id from synthetic_config_changes, nullable for 'missing'
    description     TEXT NOT NULL,          -- human-readable, feeds directly into UI EvidencePanel + agent grounding
    confidence_weight REAL NOT NULL,        -- 0-1, used by M4's rank_hypotheses node
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (incident_id) REFERENCES incidents(incident_id)
);
CREATE INDEX IF NOT EXISTS idx_evidence_incident ON evidence(incident_id);
CREATE INDEX IF NOT EXISTS idx_evidence_bucket ON evidence(bucket);

-- ------------------------------------------------------------
-- Downstream tables (owned by C / D — included for FK completeness,
-- not populated by M3 code)
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS hypotheses (
    hypothesis_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id     INTEGER NOT NULL,
    rank            INTEGER NOT NULL,
    summary         TEXT NOT NULL,
    confidence_pct  REAL NOT NULL,
    evidence_refs   TEXT NOT NULL,          -- JSON array of evidence_id
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (incident_id) REFERENCES incidents(incident_id)
);

CREATE TABLE IF NOT EXISTS audit_log (
    audit_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id  INTEGER,
    actor        TEXT NOT NULL,             -- 'system' | reviewer name
    action       TEXT NOT NULL,
    details      TEXT,
    ts           TEXT NOT NULL DEFAULT (datetime('now'))
);