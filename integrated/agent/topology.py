"""
Module 4 topology helper — now backed by Module 1's REAL 20-node enterprise
graph (loaded from the `topology` edge table + `synthetic_topology` metadata
in rca.db), replacing the earlier standalone dummy graph.

Convention here (M4-internal): a directed edge (X -> Y) means "X depends on Y"
(Y is a dependency / candidate root cause of X; if Y breaks, X is impacted).

The DB table `topology(source_node, target_node)` uses the opposite
convention — (source -> target) means "target depends on source" — so we
reverse each row when loading. See db/setup_integration.py.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import networkx as nx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "processed" / "rca.db"


def build_graph(db_path: str | Path = DB_PATH) -> nx.DiGraph:
    g = nx.DiGraph()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        # Node metadata (tier) from M1's real topology.
        for row in conn.execute("SELECT node_id, tier FROM synthetic_topology"):
            g.add_node(row["node_id"], id=row["node_id"], label=row["node_id"],
                       tier=row["tier"])
        # Edges: DB (source -> target) == target depends on source, so the
        # M4-convention edge is (target -> source).
        for row in conn.execute("SELECT source_node, target_node FROM topology"):
            g.add_edge(row["target_node"], row["source_node"])
    finally:
        conn.close()
    return g


def get_impact_path(node_id: str, max_hops: int = 3) -> dict:
    """
    For an anomalous node, returns:
      - upstream_candidates: nodes this node depends on (possible root causes),
        closer = more likely direct cause
      - downstream_impact: nodes that depend on this node (who else is affected)
    """
    g = build_graph()
    if node_id not in g:
        return {"node": node_id, "upstream_candidates": [], "downstream_impact": []}

    upstream = nx.single_source_shortest_path_length(g, node_id, cutoff=max_hops)
    upstream.pop(node_id, None)

    downstream = nx.single_source_shortest_path_length(g.reverse(), node_id, cutoff=max_hops)
    downstream.pop(node_id, None)

    return {
        "node": node_id,
        "upstream_candidates": sorted(upstream.items(), key=lambda x: x[1]),
        "downstream_impact": sorted(downstream.items(), key=lambda x: x[1]),
    }


def path_exists(node_a: str, node_b: str, max_hops: int = 3) -> tuple[bool, int]:
    """Checks for a dependency path between two nodes in either direction,
    within max_hops. Returns (exists, distance)."""
    g = build_graph()
    for source, target in [(node_a, node_b), (node_b, node_a)]:
        try:
            dist = nx.shortest_path_length(g, source, target)
            if dist <= max_hops:
                return True, dist
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            continue
    return False, -1


def full_graph_json() -> dict:
    """Serializable graph for the frontend to render."""
    g = build_graph()
    nodes = [dict(g.nodes[n]) for n in g.nodes]
    edges = [{"source": s, "target": t} for s, t in g.edges]
    return {"nodes": nodes, "edges": edges}
