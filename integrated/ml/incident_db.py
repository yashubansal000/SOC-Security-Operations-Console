import sqlite3
import os
from contextlib import contextmanager

@contextmanager
def get_db_connection(db_path="data/processed/rca.db"):
    """
    Context-managed connection. Ensures the connection is always closed,
    even if the caller raises. Prevents the 'forgot to close it' class of bug
    that silently exhausts SQLite file handles during repeated test runs.
    """
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()

def init_db(conn):
    """
    Initializes the database schema by creating all required tables and indexes.
    Aligned with the actual Module 1 database schema (ts, host_id columns).
    """
    cursor = conn.cursor()
    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS incidents (
            incident_id INTEGER PRIMARY KEY AUTOINCREMENT,
            host_id TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            description TEXT
        );
        
        CREATE TABLE IF NOT EXISTS flows (
            flow_id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            host_id TEXT NOT NULL,
            proto TEXT,
            service TEXT,
            state TEXT,
            sbytes INTEGER,
            dbytes INTEGER,
            attack_cat TEXT,
            label INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_flows_host_ts ON flows(host_id, ts);

        CREATE TABLE IF NOT EXISTS synthetic_config_changes (
            change_id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            host_id TEXT NOT NULL,
            event_description TEXT NOT NULL,
            severity TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_config_host_ts ON synthetic_config_changes(host_id, ts);

        CREATE TABLE IF NOT EXISTS synthetic_logs (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            host_id TEXT NOT NULL,
            log_message TEXT NOT NULL,
            severity TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_logs_host_ts ON synthetic_logs(host_id, ts);

        CREATE TABLE IF NOT EXISTS synthetic_topology (
            topology_id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id TEXT NOT NULL UNIQUE,
            adjacent_nodes TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS anomaly_scores (
            score_id INTEGER PRIMARY KEY AUTOINCREMENT,
            flow_id INTEGER NOT NULL,
            attack_cat_pred TEXT NOT NULL,
            confidence REAL NOT NULL,
            shap_top_features TEXT NOT NULL,
            FOREIGN KEY(flow_id) REFERENCES flows(flow_id)
        );

        CREATE TABLE IF NOT EXISTS evidence (
            evidence_id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            description TEXT NOT NULL,
            FOREIGN KEY(incident_id) REFERENCES incidents(incident_id)
        );

        CREATE TABLE IF NOT EXISTS hypotheses (
            hypothesis_id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_id INTEGER NOT NULL,
            summary TEXT NOT NULL,
            confidence REAL NOT NULL,
            remediation TEXT NOT NULL,
            FOREIGN KEY(incident_id) REFERENCES incidents(incident_id)
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            log_entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            incident_id INTEGER,
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            details TEXT
        );
    """)
    conn.commit()

def seed_mock_data(conn):
    """
    Seeds a scenario deliberately designed to exercise Module 5's edge cases.
    """
    cursor = conn.cursor()
    
    # Clear tables to allow clean re-runs
    cursor.execute("DELETE FROM incidents")
    cursor.execute("DELETE FROM flows")
    cursor.execute("DELETE FROM synthetic_config_changes")
    cursor.execute("DELETE FROM synthetic_logs")
    
    # Incident 1: web-tier
    cursor.execute(
        "INSERT INTO incidents (incident_id, host_id, start_time, end_time, description) VALUES (?, ?, ?, ?, ?)",
        (1, "web-tier", "2026-07-14T14:15:00+00:00", "2026-07-14T15:15:00+00:00", "Exploit traffic spike on web-tier"),
    )
    
    # Config changes:
    cursor.execute(
        "INSERT INTO synthetic_config_changes (ts, host_id, event_description, severity) VALUES (?, ?, ?, ?)",
        ("2026-07-14T13:30:00+00:00", "web-tier", "Modified firewall rule to allow inbound port 80", "High"),
    )
    cursor.execute(
        "INSERT INTO synthetic_config_changes (ts, host_id, event_description, severity) VALUES (?, ?, ?, ?)",
        ("2026-07-14T11:45:00+00:00", "web-tier", "Routine SSH port service reload", "Low"),
    )
    cursor.execute(
        "INSERT INTO synthetic_config_changes (ts, host_id, event_description, severity) VALUES (?, ?, ?, ?)",
        ("2026-07-14T13:45:00+00:00", "db-tier", "Updated MySQL database root user access rules", "Medium"),
    )

    # 3 flows inside Incident 1 window on web-tier
    for i, ts in enumerate(["2026-07-14T14:20:00+00:00",
                            "2026-07-14T14:25:00+00:00",
                            "2026-07-14T14:30:00+00:00"]):
        cursor.execute(
            "INSERT INTO flows (ts, host_id, proto, service, state, sbytes, dbytes, attack_cat, label) "
            "VALUES (?, 'web-tier', 'tcp', 'http', 'FIN', ?, ?, 'Exploits', 1)",
            (ts, 5000 + i * 100, 200 + i * 10),
        )
        cursor.execute(
            "INSERT INTO synthetic_logs (ts, host_id, log_message, severity) "
            "VALUES (?, 'web-tier', ?, ?)",
            (ts, f"[SYS_LOG] HOST: web-tier | PROTO: tcp | STATE: FIN | BYTES: {5200 + i*110}", "High"),
        )

    # Flow outside Incident 1 window on web-tier (Should be excluded)
    cursor.execute(
        "INSERT INTO flows (ts, host_id, proto, service, state, sbytes, dbytes, attack_cat, label) "
        "VALUES ('2026-07-14T16:30:00+00:00', 'web-tier', 'tcp', 'http', 'FIN', 100, 100, 'Normal', 0)"
    )

    # Incident 2: db-tier (starts at 16:00, ends at 16:30) - no config changes
    cursor.execute(
        "INSERT INTO incidents (incident_id, host_id, start_time, end_time, description) VALUES (?, ?, ?, ?, ?)",
        (2, "db-tier", "2026-07-14T16:00:00+00:00", "2026-07-14T16:30:00+00:00", "Anomalous db-tier traffic, no known cause"),
    )
    cursor.execute(
        "INSERT INTO flows (ts, host_id, proto, service, state, sbytes, dbytes, attack_cat, label) "
        "VALUES ('2026-07-14T16:05:00+00:00', 'db-tier', 'tcp', 'mysql', 'CON', 3000, 150, 'DoS', 1)"
    )

    # Incident 3: dns (starts at 17:00, ends at 17:10) - duplicate timestamps
    cursor.execute(
        "INSERT INTO incidents (incident_id, host_id, start_time, end_time, description) VALUES (?, ?, ?, ?, ?)",
        (3, "dns", "2026-07-14T17:00:00+00:00", "2026-07-14T17:10:00+00:00", "Simultaneous flow burst on dns"),
    )
    for _ in range(2):
        cursor.execute(
            "INSERT INTO flows (ts, host_id, proto, service, state, sbytes, dbytes, attack_cat, label) "
            "VALUES ('2026-07-14T17:05:00+00:00', 'dns', 'udp', 'dns', 'REQ', 500, 500, 'Reconnaissance', 1)"
        )

    conn.commit()

if __name__ == "__main__":
    with get_db_connection() as conn:
        init_db(conn)
        seed_mock_data(conn)
        print("Database initialized and seeded successfully.")
