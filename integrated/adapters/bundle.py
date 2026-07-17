"""
Adapter — builds the Module 4 incident bundle from the real database.

Bridges Module 3's output shape to Module 4's input contract:
  - evidence.bucket        -> EvidenceItem.tier
  - evidence.evidence_type -> EvidenceItem.type
  - evidence.node_id       -> EvidenceItem.node
  - evidence.evidence_id   -> "EV-<id>" (string, as M4 cites them)
  - shap_top_features (per-flow JSON in anomaly_scores) is aggregated into a
    single per-incident shap_features list M4's ranking node consumes.
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from typing import Any


def _aggregate_shap(conn: sqlite3.Connection, incident_id: int, top_n: int = 5) -> list[dict]:
    """Aggregate per-flow SHAP contributions across an incident's flows."""
    rows = conn.execute(
        """
        SELECT a.shap_top_features
        FROM anomaly_scores a
        JOIN incident_flows inf ON a.flow_id = inf.flow_id
        WHERE inf.incident_id = ?
        """,
        (incident_id,),
    ).fetchall()

    totals: dict[str, float] = defaultdict(float)
    for (shap_json,) in rows:
        if not shap_json:
            continue
        try:
            feats = json.loads(shap_json)
        except (json.JSONDecodeError, TypeError):
            continue
        for f in feats:
            name = f.get("feature")
            contrib = f.get("contribution", 0.0)
            if name is not None:
                totals[name] += abs(float(contrib))

    if not totals:
        return []

    grand = sum(totals.values()) or 1.0
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
    return [{"feature": name, "contribution": round(val / grand, 4)} for name, val in ranked]


def build_incident_bundle(conn: sqlite3.Connection, incident_id: int) -> dict[str, Any] | None:
    """Return the M4-ready bundle for an incident, or None if it doesn't exist."""
    conn.row_factory = sqlite3.Row
    inc = conn.execute(
        "SELECT incident_id, node_id, attack_cat, start_ts, end_ts FROM incidents WHERE incident_id = ?",
        (incident_id,),
    ).fetchone()
    if inc is None:
        return None

    ev_rows = conn.execute(
        """
        SELECT e.evidence_id, e.bucket, e.evidence_type, e.node_id, e.ref_id, e.description,
               c.ts AS change_ts
        FROM evidence e
        LEFT JOIN synthetic_config_changes c ON e.ref_id = c.change_id
        WHERE e.incident_id = ?
        ORDER BY e.evidence_id
        """,
        (incident_id,),
    ).fetchall()

    evidence = [
        {
            "evidence_id": f"EV-{r['evidence_id']}",
            "tier": r["bucket"],
            "type": r["evidence_type"],
            "node": r["node_id"] or inc["node_id"],
            "timestamp": r["change_ts"],
            "description": r["description"],
        }
        for r in ev_rows
    ]

    return {
        "incident_id": f"INC-{inc['incident_id']:05d}",
        "db_incident_id": inc["incident_id"],
        "primary_node": inc["node_id"],
        "attack_cat": inc["attack_cat"],
        "window": {"start": inc["start_ts"], "end": inc["end_ts"]},
        "shap_features": _aggregate_shap(conn, incident_id),
        "evidence": evidence,
    }
