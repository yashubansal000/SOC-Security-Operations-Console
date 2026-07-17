"""
Service layer — runs the Module 4 agent for a DB incident and persists the
result (hypotheses + audit_log). Reused by the batch orchestrator and by the
API's regenerate endpoint.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from adapters.bundle import build_incident_bundle
from agent.topology import get_impact_path
from agent.graph import run_pipeline


def generate_hypotheses_for_incident(
    conn: sqlite3.Connection, incident_id: int, actor: str = "system"
) -> dict[str, Any] | None:
    """Build the bundle, run the LangGraph agent, persist hypotheses, audit."""
    bundle = build_incident_bundle(conn, incident_id)
    if bundle is None:
        return None

    impact = get_impact_path(bundle["primary_node"])
    result = run_pipeline(bundle, impact_path=impact)

    ranked = result.ranked_hypotheses
    remediation = [r.model_dump() for r in result.remediation]

    cur = conn.cursor()
    cur.execute("DELETE FROM hypotheses WHERE incident_id = ?", (incident_id,))
    for rank, h in enumerate(ranked, start=1):
        cur.execute(
            """INSERT INTO hypotheses
               (incident_id, rank, root_cause_node, summary, confidence_pct,
                evidence_refs, next_steps)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                incident_id,
                rank,
                h.root_cause_node,
                h.claim,
                round((h.confidence or 0.0) * 100, 1),
                json.dumps(h.cited_evidence_ids),
                json.dumps(remediation) if rank == 1 else json.dumps([]),
            ),
        )
    conn.execute(
        "INSERT INTO audit_log (actor, action, incident_id, details) VALUES (?, ?, ?, ?)",
        (actor, "hypotheses_generated", incident_id,
         f"{len(ranked)} hypotheses; top confidence "
         f"{round((ranked[0].confidence or 0)*100,1) if ranked else 0}%"),
    )
    conn.commit()

    return {
        "incident_id": incident_id,
        "primary_node": result.primary_node,
        "attack_cat": result.attack_cat,
        "ranked_hypotheses": [h.model_dump() for h in ranked],
        "remediation": remediation,
        "trace_log": result.log,
    }
