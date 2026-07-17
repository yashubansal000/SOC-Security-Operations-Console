"""
Bridge engine for LLM calls (Module 4).

Architecture: the LangGraph nodes deterministically decide WHICH node is a
candidate root cause; the LLM only writes the natural-language narrative and
remediation text. Detection, grounding, and ranking never touch an LLM.

Provider strategy (demo-safe):
  1. If GROQ_API_KEY is set and the `groq` package imports, use live Groq.
  2. Otherwise fall back to a DETERMINISTIC template generator so the pipeline
     always produces grounded, reproducible output with zero network — the
     demo can never hard-fail on a missing key or flaky connection.
"""

from __future__ import annotations

import logging
import os
from typing import Any, List

from agent.schemas import Hypothesis, RemediationStep

logger = logging.getLogger("llm_engine")

# --- Try to load the live Groq layer (renamed from llm_stub.py) ------------
try:
    from agent.llm_layer import mock_generate_narrative, mock_recommend_next_steps
    _LIVE_AVAILABLE = True
except Exception as exc:  # ImportError, or missing groq package
    logger.info("Live LLM layer unavailable (%s); using deterministic fallback.", exc)
    mock_generate_narrative = None
    mock_recommend_next_steps = None
    _LIVE_AVAILABLE = False


def _live_enabled() -> bool:
    return _LIVE_AVAILABLE and bool(os.environ.get("GROQ_API_KEY"))


# ---------------------------------------------------------------------------
# Deterministic fallbacks (no network, fully reproducible)
# ---------------------------------------------------------------------------

def _ev_get(e: Any, key: str):
    if hasattr(e, key):
        return getattr(e, key)
    if isinstance(e, dict):
        return e.get(key)
    return None


def _fallback_narrative(node: str, evidence: List[Any], attack_cat: str) -> Hypothesis:
    cited = [_ev_get(e, "evidence_id") for e in evidence]
    cited = [c for c in cited if c]
    confirmed = [e for e in evidence if _ev_get(e, "tier") == "confirmed"]
    lead = _ev_get(confirmed[0], "description") if confirmed else (
        _ev_get(evidence[0], "description") if evidence else None
    )

    tier_word = "confirmed" if confirmed else "correlated"
    claim = (
        f"{node} is the most likely root cause of this {attack_cat} incident: "
        f"{len(cited)} {tier_word} evidence item(s) implicate it"
    )
    if lead:
        claim += f", notably — {lead}"
    claim += "."

    return Hypothesis(
        hypothesis_id=f"H_{node.replace('-', '_')}",
        claim=claim,
        root_cause_node=node,
        cited_evidence_ids=cited,
    )


_REMEDIATION_TEMPLATES = {
    "DoS": [
        ("Enable/verify rate-limiting and SYN-flood protection at the perimeter for the affected node.",
         "A DoS root cause is mitigated by throttling abusive traffic before it reaches the service."),
        ("Inspect and, if needed, roll back the most recent firewall/config change on the root-cause node.",
         "The confirmed config change is the strongest lead; reverting isolates whether it opened the attack surface."),
        ("Scale out or shed load on downstream dependents identified in the impact path.",
         "Protects services that depend on the affected node while the root cause is remediated."),
    ],
    "Exploits": [
        ("Patch the affected service to the latest security update and block the exploited signature at the WAF.",
         "Exploit traffic targets a known vulnerability; patching plus signature blocking closes the vector."),
        ("Quarantine the root-cause node and capture a forensic snapshot before remediation.",
         "Preserves evidence and stops lateral movement while the exploit is analysed."),
    ],
    "Reconnaissance": [
        ("Tighten ACLs and disable unneeded services/ports on the scanned node.",
         "Reconnaissance precedes attack; reducing the exposed surface limits enumeration."),
        ("Add the source pattern to watchlists and raise alerting sensitivity on adjacent nodes.",
         "Early detection of follow-on activity across the impact path."),
    ],
    "Backdoor": [
        ("Isolate the node, rotate all credentials, and scan for persistence mechanisms.",
         "A backdoor implies established access; credential rotation and persistence removal are mandatory."),
        ("Audit recent config changes and account grants on the node and its neighbours.",
         "Backdoors are frequently installed alongside a config/ACL change flagged in the evidence."),
    ],
}
_DEFAULT_REMEDIATION = [
    ("Investigate the top-ranked root-cause node and validate the confirmed evidence items.",
     "Grounding the response in the confirmed evidence keeps remediation defensible."),
    ("Review and, if warranted, revert the most recent config change on the node.",
     "Config changes are the highest-confidence causal signal in the evidence bundle."),
    ("Monitor the downstream impact-path nodes for propagation.",
     "Limits blast radius while the root cause is addressed."),
]


def _fallback_remediation(top_hypothesis: Hypothesis, attack_cat: str) -> List[RemediationStep]:
    template = _REMEDIATION_TEMPLATES.get(attack_cat, _DEFAULT_REMEDIATION)
    return [RemediationStep(step=s, rationale=r) for s, r in template]


# ---------------------------------------------------------------------------
# Public API used by agent/graph.py
# ---------------------------------------------------------------------------

def call_claude_generate_narrative(node: str, evidence: List[Any], attack_cat: str) -> Hypothesis:
    """Targeted narrative for a node the code already scoped as a candidate."""
    if _live_enabled():
        try:
            result = mock_generate_narrative(node, evidence, attack_cat)
            if result is not None:
                return result
        except Exception as exc:
            logger.warning("Live narrative failed (%s); falling back to template.", exc)
    return _fallback_narrative(node, evidence, attack_cat)


def call_claude_revise_hypotheses(failed_hyps: List[Hypothesis], evidence_bundle: List[Any]) -> List[Hypothesis]:
    """Revision loop: drop ungrounded hypotheses. Kept deterministic (returns
    the cleaned/empty set) so the graph loop always terminates safely."""
    logger.info("Revision: discarding %d ungrounded hypotheses.", len(failed_hyps))
    return []


def call_claude_remediation(top_hypothesis: Hypothesis, attack_cat: str) -> List[RemediationStep]:
    """Diagnostic + remediation steps for the winning hypothesis."""
    if _live_enabled():
        try:
            steps = mock_recommend_next_steps(top_hypothesis, attack_cat)
            if steps:
                return steps
        except Exception as exc:
            logger.warning("Live remediation failed (%s); falling back to template.", exc)
    return _fallback_remediation(top_hypothesis, attack_cat)
