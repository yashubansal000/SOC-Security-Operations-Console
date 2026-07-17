"""
run_from_module3.py — full pipeline: raw text -> M1 -> M2 -> M3 -> M4.
"""

import sys
import os
import json
from pathlib import Path

# ---------------------------------------------------------------------
# PATH SETUP
# ---------------------------------------------------------------------
_COMBINED_ROOT = Path(__file__).resolve().parent
M1_PATH = os.environ.get("M1_PATH", str(_COMBINED_ROOT / "module-1new"))
M3_PATH = os.environ.get("M3_PATH", str(_COMBINED_ROOT / "module3"))
M4_PATH = os.environ.get("M4_PATH", str(_COMBINED_ROOT / "module4_rca_agent")) # <-- ADDED M4

for p in (M1_PATH, M3_PATH, M4_PATH):
    if p not in sys.path:
        sys.path.insert(0, p)

from synth.process_custom import process_custom_upload
from bridge_to_agent import process_incident_for_agent
from agent.graph import run_pipeline 

def run_full_pipeline(raw_text: str, lookback_minutes: int = 30) -> list:
    """Runs M1-M4 and returns the exact JSON schema required by the frontend."""
    upload_result = process_custom_upload(raw_text)

    if not upload_result["anomalous_incidents"]:
        print("No anomalous incidents detected in this upload.")
        return []

    results = []
    for incident in upload_result["anomalous_incidents"]:
        # Run Module 3
        agent_input = process_incident_for_agent(
            upload_result["db_path"], incident, lookback_minutes=lookback_minutes
        )
        
        # Run Module 4
        final_state = run_pipeline(
            incident_bundle=agent_input["bundle"],
            impact_path=agent_input["impact_path"],
        )
        
        # Map to the EXACT schema expected by module4_rca_agent/api/main.py
        results.append({
            "incident_id": getattr(final_state, 'incident_id', 'Unknown'),
            "primary_node": getattr(final_state, 'primary_node', 'Unknown'),
            "attack_cat": getattr(final_state, 'attack_cat', 'Unknown'),
            "shap_features": getattr(final_state, 'shap_features', {}),
            "evidence_bundle": [e.model_dump() for e in getattr(final_state, 'evidence_bundle', [])],
            "impact_path": getattr(final_state, 'impact_path', []),
            "ranked_hypotheses": [h.model_dump() for h in getattr(final_state, 'ranked_hypotheses', [])],
            "remediation": [r.model_dump() for r in getattr(final_state, 'remediation', [])],
            "trace_log": getattr(final_state, 'log', []),
        })

    return results

if __name__ == "__main__":
    # Fallback testing execution
    sample_text = """
    Firewall firewall-01 sits upstream of web-tier web-srv-01.
    A firewall rule was modified on firewall-01 shortly before the incident.
    Shortly after, web-srv-01 experienced a DoS-style traffic spike:
    proto=tcp, service=http, state=FIN, roughly 4500 bytes sent, 300 bytes received,
    connection duration around 0.8 seconds.
    """
    res = run_full_pipeline(sample_text)
    if res:
        print(f"Pipeline success! Root Cause Node: {res[0]['primary_node']}")