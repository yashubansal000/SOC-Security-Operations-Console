"""
correlation/evidence_engine.py — Module 3 correlation & evidence classification.

REWRITTEN to match M1's REAL schema (generate_multisource.py / process_custom.py),
not the earlier schema.sql plan that M1's actual code diverged from:
  - flows: host_id, ts (not node_id, synthetic_ts)
  - synthetic_topology: node_id, tier, adjacent_nodes (JSON list) — already
    undirected/bidirectional, so no separate predecessor/successor logic needed
  - synthetic_config_changes: host_id, ts, event_description (not node_id,
    change_ts, description)

Also: works against ANY session db_path (not a hardcoded constant), since
custom uploads each get their own rca_<session_id>.db. The old
cluster_incidents()/anomaly_scores-table approach is dropped for this path —
custom-input incidents already come pre-built from M2's predict_single(),
so there's nothing to cluster from a table that's never populated for
this flow.

inject_topology.py's frequency-guessed topology is no longer needed or
used — M1 already provides a real, intentional topology per session.
"""

import json
import sqlite3
import networkx as nx
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any


def get_db_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_m3_tables(conn: sqlite3.Connection, schema_path: str = "db/schema.sql") -> None:
    """Creates ONLY the M3-owned tables (incidents, incident_flows, evidence,
    hypotheses, audit_log). Deliberately does NOT run schema.sql's M1/M2
    table definitions - those tables are already created by M1's real
    generate_multisource.py/process_custom.py with different (correct)
    column names than the outdated schema.sql plan, and re-running those
    CREATE INDEX statements against the real tables fails with
    'no such column' errors."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS incidents (
            incident_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id         TEXT NOT NULL,
            attack_cat      TEXT NOT NULL,
            start_ts        TEXT NOT NULL,
            end_ts          TEXT NOT NULL,
            flow_count      INTEGER NOT NULL,
            severity        TEXT NOT NULL,
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_incidents_node ON incidents(node_id);
        CREATE INDEX IF NOT EXISTS idx_incidents_ts ON incidents(start_ts);

        CREATE TABLE IF NOT EXISTS incident_flows (
            incident_id  INTEGER NOT NULL,
            flow_id      INTEGER NOT NULL,
            PRIMARY KEY (incident_id, flow_id)
        );

        CREATE TABLE IF NOT EXISTS evidence (
            evidence_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_id     INTEGER NOT NULL,
            bucket          TEXT NOT NULL CHECK (bucket IN ('confirmed', 'correlated', 'missing')),
            evidence_type   TEXT NOT NULL,
            node_id         TEXT,
            ref_id          INTEGER,
            description     TEXT NOT NULL,
            confidence_weight REAL NOT NULL,
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (incident_id) REFERENCES incidents(incident_id)
        );
        CREATE INDEX IF NOT EXISTS idx_evidence_incident ON evidence(incident_id);
        CREATE INDEX IF NOT EXISTS idx_evidence_bucket ON evidence(bucket);

        CREATE TABLE IF NOT EXISTS hypotheses (
            hypothesis_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_id     INTEGER NOT NULL,
            rank            INTEGER NOT NULL,
            summary         TEXT NOT NULL,
            confidence_pct  REAL NOT NULL,
            evidence_refs   TEXT NOT NULL,
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (incident_id) REFERENCES incidents(incident_id)
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            audit_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_id  INTEGER,
            actor        TEXT NOT NULL,
            action       TEXT NOT NULL,
            details      TEXT,
            ts           TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)


def build_topology_graph(cursor: sqlite3.Cursor) -> nx.Graph:
    """Builds an undirected graph from M1's REAL synthetic_topology table.
    adjacent_nodes is a JSON-encoded list of neighbor node_ids, already
    bidirectional (M1's generate_multisource.py builds it from an
    undirected nx.Graph), so no predecessor/successor split is needed here."""
    G = nx.Graph()
    cursor.execute("SELECT node_id, adjacent_nodes FROM synthetic_topology")
    rows = cursor.fetchall()

    for row in rows:
        node_id = row["node_id"]
        G.add_node(node_id)
        try:
            neighbors = json.loads(row["adjacent_nodes"]) if row["adjacent_nodes"] else []
        except (json.JSONDecodeError, TypeError):
            neighbors = []
        for neighbor in neighbors:
            G.add_edge(node_id, neighbor)

    return G


def get_adjacent_nodes(G: nx.Graph, node_id: str) -> List[str]:
    """Real, direct topology neighbors of a node. Empty list if node
    isn't in the graph (e.g. Groq extracted a node name the topology
    dict didn't actually define)."""
    if node_id not in G:
        return []
    return sorted(G.neighbors(node_id))


def _resolve_primary_node(incident: Dict[str, Any]) -> Optional[str]:
    """Custom-upload incidents (from process_custom_upload) carry a REAL
    topology node in 'host_id'. 'affected_node' is a decorative/fake value
    from build_incident_object's hardcoded node list and must NOT be used
    for topology matching when host_id is present."""
    return incident.get("host_id") or incident.get("affected_node")


def build_evidence_bundle(
    db_path: str,
    incident: Dict[str, Any],
    lookback_minutes: int = 30,
    schema_path: str = "db/schema.sql",
) -> Dict[str, Any]:
    """
    Takes ONE already-scored incident (M2's predict_single() output) and
    this session's db_path, classifies evidence into confirmed/correlated/
    missing using real topology + time-window logic, persists it to the
    session db's incidents/evidence tables (audit trail), and returns a
    plain evidence_bundle shaped exactly for M4's run_pipeline().
    """
    primary_node = _resolve_primary_node(incident)
    if not primary_node:
        raise ValueError(
            "Incident has neither 'host_id' nor 'affected_node' - cannot "
            "determine which topology node this incident is anchored to."
        )

    conn = get_db_connection(db_path)
    ensure_m3_tables(conn)
    cursor = conn.cursor()

    incident_ts = incident.get("timestamp")
    if not incident_ts:
        raise ValueError("Incident is missing a 'timestamp' field.")
    incident_dt = datetime.fromisoformat(incident_ts.replace("Z", "+00:00"))
    lookback_dt = incident_dt - timedelta(minutes=lookback_minutes)

    # --- persist an incidents row for this custom incident (audit trail) ---
    cursor.execute(
        """
        INSERT INTO incidents (node_id, attack_cat, start_ts, end_ts, flow_count, severity)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            primary_node,
            incident.get("attack_type", "Unknown"),
            incident_ts,
            incident_ts,
            1,
            incident.get("severity", "Medium"),
        ),
    )
    db_incident_id = cursor.lastrowid

    evidence_rows: List[Dict[str, Any]] = []   # what we'll return to M4
    ev_counter = 1

    def add_evidence(bucket: str, evidence_type: str, node: str,
                      description: str, confidence_weight: float,
                      ts: Optional[str] = None, ref_id: Optional[int] = None):
        nonlocal ev_counter
        cursor.execute(
            """
            INSERT INTO evidence (incident_id, bucket, evidence_type, node_id,
                                   ref_id, description, confidence_weight)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (db_incident_id, bucket, evidence_type, node, ref_id, description, confidence_weight),
        )
        evidence_rows.append({
            "evidence_id": f"EV-{ev_counter}",
            "tier": bucket,
            "type": evidence_type,
            "node": node,
            "timestamp": ts,
            "description": description,
        })
        ev_counter += 1

    # --- 1. CONFIRMED: direct config change on the primary node itself ---
    cursor.execute(
        """
        SELECT change_id, ts, event_description FROM synthetic_config_changes
        WHERE host_id = ? AND ts BETWEEN ? AND ?
        """,
        (primary_node, lookback_dt.isoformat(), incident_ts),
    )
    direct_changes = cursor.fetchall()

    found_config_evidence = False
    for change in direct_changes:
        add_evidence(
            bucket="confirmed",
            evidence_type="config_change",
            node=primary_node,
            description=f"Direct config change on {primary_node}: {change['event_description']}",
            confidence_weight=0.95,
            ts=change["ts"],
            ref_id=change["change_id"],
        )
        found_config_evidence = True

    # --- 2. CORRELATED: config change on a REAL topology-adjacent node ---
    if not found_config_evidence:
        topo_graph = build_topology_graph(cursor)
        adjacent_nodes = get_adjacent_nodes(topo_graph, primary_node)

        for adj_node in adjacent_nodes:
            cursor.execute(
                """
                SELECT change_id, ts, event_description FROM synthetic_config_changes
                WHERE host_id = ? AND ts BETWEEN ? AND ?
                """,
                (adj_node, lookback_dt.isoformat(), incident_ts),
            )
            for change in cursor.fetchall():
                add_evidence(
                    bucket="correlated",
                    evidence_type="topology_adjacency",
                    node=adj_node,
                    description=(
                        f"Topology-adjacent node ({adj_node}) had a config change: "
                        f"{change['event_description']}"
                    ),
                    confidence_weight=0.65,
                    ts=change["ts"],
                    ref_id=change["change_id"],
                )
                found_config_evidence = True

    # --- 3. MISSING: explicitly checked, nothing found ---
    if not found_config_evidence:
        add_evidence(
            bucket="missing",
            evidence_type="no_config_change_found",
            node=primary_node,
            description=(
                f"No config-change record found on {primary_node} or its topology "
                f"neighbors in the {lookback_minutes}-minute window before this incident."
            ),
            confidence_weight=0.0,
        )

    # --- 4. SHAP-derived evidence, demoted if the feature was imputed ---
    for shap_item in incident.get("shap", []):
        is_imputed = shap_item.get("imputed", False)
        weight = 0.30 if is_imputed else 0.75
        note = " (estimated/imputed value, not directly observed)" if is_imputed else ""
        add_evidence(
            bucket="correlated",
            evidence_type="shap_anomaly",
            node=primary_node,
            description=(
                f"Model flagged feature '{shap_item.get('feature')}' as anomalous "
                f"(importance {shap_item.get('importance')}){note}."
            ),
            confidence_weight=weight,
            ts=incident_ts,
        )

    conn.commit()
    conn.close()

    return {
        "incident_id": incident.get("incident_id"),
        "primary_node": primary_node,
        "attack_cat": incident.get("attack_type", "Unknown"),
        "shap_features": [
            {"feature": s.get("feature"), "contribution": s.get("importance"), "imputed": s.get("imputed", False)}
            for s in incident.get("shap", [])
        ],
        "evidence": evidence_rows,
    }


def build_impact_path(db_path: str, node_id: str, max_hops: int = 3) -> Dict[str, Any]:
    """Real topology impact path for a node, using M1's actual synthetic_topology."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    G = build_topology_graph(cursor)
    conn.close()

    if node_id not in G:
        return {"node": node_id, "upstream_candidates": [], "downstream_impact": []}

    distances = nx.single_source_shortest_path_length(G, node_id, cutoff=max_hops)
    distances.pop(node_id, None)

    # undirected graph -> "upstream" and "downstream" aren't distinguishable
    # by direction here (M1's topology is undirected); report as one
    # combined "topologically reachable" list, ordered by distance.
    reachable = sorted(distances.items(), key=lambda x: x[1])

    return {
        "node": node_id,
        "upstream_candidates": reachable,
        "downstream_impact": reachable,
    }