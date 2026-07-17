"""
Integration setup — bridges Module 1's real database to Modules 3/4/7.

Idempotent. Does two things:
  1. Applies db/schema_downstream.sql (adds anomaly_scores, topology,
     incidents, incident_flows, evidence, hypotheses, audit_log — never
     touches M1's tables).
  2. Rebuilds the directed `topology` edge table from Module 1's REAL
     topology definition, so Module 3's impact-path logic runs on the
     genuine 20-node enterprise graph instead of the discarded
     timestamp-co-occurrence heuristic.

Edge semantics: (source_node -> target_node) means "target depends on
source". If `source` is compromised/changed, `target` is downstream impact.
This is derived from Module 1's `upstream` lists (a node's upstream = the
nodes it depends on), so edge = (upstream_parent -> node).

Run:
    python -m db.setup_integration
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

# Import Module 1's authoritative topology (single source of truth).
from synth.generate_multisource import TOPOLOGY_DEFINITION

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "processed" / "rca.db"
SCHEMA_PATH = PROJECT_ROOT / "db" / "schema_downstream.sql"


def apply_downstream_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text())


def rebuild_topology_edges(conn: sqlite3.Connection) -> int:
    """Populate the directed `topology` edge table from M1's real graph."""
    cur = conn.cursor()
    cur.execute("DELETE FROM topology")
    edges: set[tuple[str, str]] = set()
    for node_id, meta in TOPOLOGY_DEFINITION.items():
        for parent in meta.get("upstream", []):
            # parent -> node : node depends on parent
            edges.add((parent, node_id))
    cur.executemany(
        "INSERT OR IGNORE INTO topology (source_node, target_node) VALUES (?, ?)",
        sorted(edges),
    )
    conn.commit()
    return len(edges)


def main() -> None:
    if not DB_PATH.exists():
        raise SystemExit(
            f"DB not found at {DB_PATH}. Run Module 1 first "
            f"(python synth/generate_multisource.py)."
        )
    conn = sqlite3.connect(DB_PATH)
    try:
        apply_downstream_schema(conn)
        n_edges = rebuild_topology_edges(conn)
        n_nodes = conn.execute(
            "SELECT COUNT(*) FROM synthetic_topology"
        ).fetchone()[0]
        print(
            f"[setup_integration] downstream schema applied; "
            f"topology rebuilt: {n_nodes} nodes, {n_edges} directed edges."
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
