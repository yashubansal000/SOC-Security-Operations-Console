"""
bridge_to_agent.py — hands one M2-scored incident + its session db to
Module 4's LangGraph pipeline, via M3's evidence classification.

REWRITTEN: previously only ran in batch mode over a static
incident_objects.json and passed M2's raw string evidence straight
through with no real classification. Now calls the real
build_evidence_bundle() per incident, and exposes a function callable
directly from process_custom_upload()'s output - no file round-trip
required for the custom-input path.
"""

import json
from correlation.evidence_engine import build_evidence_bundle, build_impact_path


def process_incident_for_agent(db_path: str, incident: dict, lookback_minutes: int = 30) -> dict:
    """
    Takes one incident (from M2's predict_single / anomalous_incidents list)
    and this session's db_path, and returns the exact bundle shape M4's
    run_pipeline() expects:
      {incident_id, primary_node, attack_cat, shap_features, evidence}
    plus 'impact_path' alongside it (M4's run_pipeline takes this as a
    separate argument, not nested inside the bundle - see agent/graph.py).
    """
    bundle = build_evidence_bundle(db_path, incident, lookback_minutes=lookback_minutes)
    impact_path = build_impact_path(db_path, bundle["primary_node"])

    return {
        "bundle": bundle,
        "impact_path": impact_path,
    }


def process_all_incidents_for_agent(db_path: str, incidents: list, lookback_minutes: int = 30) -> list:
    """Convenience wrapper for multiple incidents from the same session db."""
    results = []
    for incident in incidents:
        try:
            results.append(process_incident_for_agent(db_path, incident, lookback_minutes))
        except Exception as e:
            print(f"[bridge_to_agent] Failed to process incident "
                  f"{incident.get('incident_id')}: {e}")
    return results


# ---------------------------------------------------------------------
# Batch mode kept for the old static-file path (dataset.db test-split
# incidents from M2's batch predict.py) - separate from the custom-input
# path above, which never needs incident_objects.json at all.
# ---------------------------------------------------------------------
def run_batch_process(json_path: str, db_path: str = "data/processed/rca.db"):
    with open(json_path, "r") as f:
        all_incidents = json.load(f)

    print(f"--- STARTING BUNDLE GENERATION FOR {len(all_incidents)} INCIDENTS ---")

    results = process_all_incidents_for_agent(db_path, all_incidents)

    for r in results:
        print(json.dumps(r, indent=2))
        print("-" * 50)

    print("Batch processing complete.")
    return results


if __name__ == "__main__":
    run_batch_process("incident_objects.json")