import time
import hashlib
import pandas as pd
from typing import Dict, Any, List, Optional
def _resolve_incident_timestamp(row_raw) -> str:
    """Uses the flow's actual synthetic timestamp (consistent with M1's
    fake demo-day timeline that config changes are also anchored against),
    instead of real wall-clock time - which would never align with
    anything else in the synthetic timeline for evidence-window matching."""
    ts = row_raw.get('ts') if hasattr(row_raw, 'get') else None
    if ts:
        # normalize to the Z-suffixed format the rest of the code expects
        return ts if ts.endswith("Z") else f"{ts}Z"
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def build_incident_object(
    orig_idx: int,
    row_raw: pd.Series,
    prob_score: float,
    shap_data: List[Dict[str, Any]],
    evidence: List[str],
    imputed_features: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Generates structural incident objects mapped against strict hackathon design specifications."""

    attack_cat = str(row_raw.get('attack_cat', 'Intrusion Attempt')).strip()
    if attack_cat in ['0', '', 'Normal', 'nan']:
        attack_cat = 'Intrusion Attempt'

    unique_hash = hashlib.sha256(f"{attack_cat}_{orig_idx}".encode()).hexdigest()

    nodes = ["Router01", "Switch03", "FirewallCore", "EdgeNode02", "AppServer05"]
    services = ["HTTP", "DNS", "FTP", "SSH", "SMTP"]

    node_idx = int(unique_hash[0:2], 16) % len(nodes)
    serv_idx = int(unique_hash[2:4], 16) % len(services)
    severity = "Critical" if prob_score > 0.90 else ("High" if prob_score > 0.70 else "Medium")

    imputed_features = imputed_features or []

    # Tag each SHAP entry with whether it's leaning on an imputed (estimated),
    # not observed, feature value - so downstream (M3/M4) can discount it.
    shap_tagged = [
        {**s, "imputed": s.get("feature") in imputed_features}
        for s in shap_data
    ]

    return {
        "incident_id": f"INC-{orig_idx + 10000:05d}",
        "timestamp": _resolve_incident_timestamp(row_raw),
        "attack_type": attack_cat,
        "confidence": round(prob_score, 2),
        "severity": severity,
        "source_ip": f"192.168.1.{100 + (orig_idx % 50)}",
        "destination_ip": f"10.0.0.{5 + (orig_idx % 20)}",
        "protocol": str(row_raw.get('proto', 'TCP')),
        "service": str(row_raw.get('service', 'HTTP')),
        "affected_node": nodes[node_idx],
        "affected_service": services[serv_idx],
        "model": "XGBoost",
        "shap": shap_tagged,
        "evidence": evidence,
        "imputed_features": imputed_features,
    }