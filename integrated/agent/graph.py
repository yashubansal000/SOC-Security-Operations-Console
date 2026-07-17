from langgraph.graph import StateGraph, END
from agent.schemas import IncidentState, Hypothesis
from collections import defaultdict

# Replaced 'generate_hypotheses' with the new targeted 'generate_narrative' import
from agent.llm_engine import (
    call_claude_generate_narrative, 
    call_claude_revise_hypotheses, 
    call_claude_remediation
)
from agent.topology import path_exists
from typing import Dict, Any, List

MAX_HOPS = 3
MAX_LOOP_ITERATIONS = 2

# ---------------------------------------------------------------------------
# Node 1: generate_hypotheses (Now Deterministic Scope + LLM Narrative)
# ---------------------------------------------------------------------------
def generate_hypotheses(state: IncidentState) -> Dict[str, Any]:
    # 1. Deterministic Step: Group evidence by node
    evidence_by_node = defaultdict(list)
    for ev in state.evidence_bundle:
        if ev.tier in ("confirmed", "correlated"):
            evidence_by_node[ev.node].append(ev)
    
    # 2. Loop Step: Create one hypothesis per candidate node dynamically
    candidate_hypotheses = []
    for node, node_evidence in evidence_by_node.items():
        # Call the LLM specifically for this node's narrative
        hyp = call_claude_generate_narrative(
            node=node,
            evidence=node_evidence,
            attack_cat=state.attack_cat
        )
        candidate_hypotheses.append(hyp)

    return {
        "candidate_hypotheses": candidate_hypotheses,
        "log": state.log + [f"generate_hypotheses: Deterministically scoped {len(candidate_hypotheses)} candidate nodes."]
    }

# ---------------------------------------------------------------------------
# Node 2: ground_check (100% Deterministic Python Gate)
# ---------------------------------------------------------------------------
def ground_check(state: IncidentState) -> Dict[str, Any]:
    evidence_by_id = {e.evidence_id: e for e in state.evidence_bundle}
    processed_candidates = []

    for h in state.candidate_hypotheses:
        # Rule 1: Evidence verification
        unknown_ids = [eid for eid in h.cited_evidence_ids if eid not in evidence_by_id]
        if unknown_ids:
            h.grounded = False
            h.rejected_reason = f"Cites non-existent evidence id(s): {unknown_ids}"
            processed_candidates.append(h)
            continue

        cited = [evidence_by_id[eid] for eid in h.cited_evidence_ids]

        # Rule 2: Correlated asset verification
        if not any(e.tier in ("confirmed", "correlated") for e in cited):
            h.grounded = False
            h.rejected_reason = "Only cites 'missing' evidence - cannot assert a root cause from an absence."
            processed_candidates.append(h)
            continue

        # Rule 3: Topology validation
        if h.root_cause_node != state.primary_node:
            exists, _ = path_exists(h.root_cause_node, state.primary_node, MAX_HOPS)
            if not exists:
                h.grounded = False
                h.rejected_reason = f"No topology path to primary node within {MAX_HOPS} hops."
                processed_candidates.append(h)
                continue

        # Passes all validation checks
        h.grounded = True
        h.rejected_reason = None
        h.evidence_tier_breakdown = {
            "confirmed": sum(1 for e in cited if e.tier == "confirmed"),
            "correlated": sum(1 for e in cited if e.tier == "correlated"),
            "missing": sum(1 for e in cited if e.tier == "missing"),
        }
        processed_candidates.append(h)

    return {
        "candidate_hypotheses": processed_candidates,
        "log": state.log + [f"ground_check: Evaluated {len(processed_candidates)} hypotheses."]
    }

# ---------------------------------------------------------------------------
# Conditional Router: Decides if we loop to revise or advance
# ---------------------------------------------------------------------------
def route_post_ground_check(state: IncidentState) -> str:
    has_ungrounded = any(not h.grounded for h in state.candidate_hypotheses)
    
    if has_ungrounded and state.loop_count < MAX_LOOP_ITERATIONS:
        return "revise_hypothesis"
    
    return "rank_hypotheses"

# ---------------------------------------------------------------------------
# Node 3: revise_hypothesis (LLM-backed loop to strip hallucinated claims)
# ---------------------------------------------------------------------------
def revise_hypothesis(state: IncidentState) -> Dict[str, Any]:
    # Filter out what failed the code-gate
    failed_hyps = [h for h in state.candidate_hypotheses if not h.grounded]
    
    # Prompt Claude to explicitly strip out the ungrounded assertions/evidence strings
    revised_hyps = call_claude_revise_hypotheses(failed_hyps, state.evidence_bundle)
    
    # Maintain the valid ones, mix in the newly revised ones
    clean_pool = [h for h in state.candidate_hypotheses if h.grounded] + revised_hyps
    
    return {
        "candidate_hypotheses": clean_pool,
        "loop_count": state.loop_count + 1,
        "log": state.log + [f"revise_hypothesis: Attempting revision loop iteration {state.loop_count + 1}."]
    }

# ---------------------------------------------------------------------------
# Node 4: rank_hypotheses (Deterministic Scoring Engine)
# ---------------------------------------------------------------------------
def rank_hypotheses(state: IncidentState) -> Dict[str, Any]:
    shap_weight_by_node = {f["feature"]: f["contribution"] for f in state.shap_features}
    scored = []
    
    for h in state.candidate_hypotheses:
        if not h.grounded:
            h.confidence = 0.0
            scored.append(h)
            continue

        breakdown = h.evidence_tier_breakdown or {}
        score = 0.0
        score += breakdown.get("confirmed", 0) * 0.45
        score += breakdown.get("correlated", 0) * 0.20
        score -= breakdown.get("missing", 0) * 0.10

        if h.root_cause_node == state.primary_node:
            score += 0.15

        score += max(shap_weight_by_node.values(), default=0) * 0.25
        
        # Enforce highly distinct UI scaling output targets (91%, 54%, 21% scale patterns)
        h.confidence = round(min(max(score, 0.05), 0.99), 2)
        scored.append(h)

    scored.sort(key=lambda x: x.confidence, reverse=True)
    
    return {
        "ranked_hypotheses": scored,
        "log": state.log + ["rank_hypotheses: Scored and organized candidates by graph certainty metrics."]
    }

# ---------------------------------------------------------------------------
# Node 5: recommend_next_steps (LLM Powered)
# ---------------------------------------------------------------------------
def recommend_next_steps(state: IncidentState) -> Dict[str, Any]:
    top_grounded = [h for h in state.ranked_hypotheses if h.grounded]
    if not top_grounded:
        return {"remediation": [], "log": state.log + ["recommend_next_steps: No grounded models available."]}

    top = top_grounded[0]
    remediation_plan = call_claude_remediation(top, state.attack_cat)
    return {
        "remediation": remediation_plan,
        "log": state.log + [f"recommend_next_steps: Formulated mitigation steps for root cause node {top.root_cause_node}."]
    }

# ---------------------------------------------------------------------------
# Orchestration Assembly
# ---------------------------------------------------------------------------

def build_app():
    workflow = StateGraph(IncidentState)
    
    # Register all 5 structural nodes
    workflow.add_node("generate_hypotheses", generate_hypotheses)
    workflow.add_node("ground_check", ground_check)
    workflow.add_node("revise_hypothesis", revise_hypothesis)
    workflow.add_node("rank_hypotheses", rank_hypotheses)
    workflow.add_node("recommend_next_steps", recommend_next_steps)

    workflow.set_entry_point("generate_hypotheses")
    workflow.add_edge("generate_hypotheses", "ground_check")
    
    # THIS SENDS FAILING ITEMS TO REVISE NODE, PASSING ITEMS TO RANKING NODE
    workflow.add_conditional_edges(
        "ground_check",
        route_post_ground_check,
        {
            "revise_hypothesis": "revise_hypothesis",
            "rank_hypotheses": "rank_hypotheses"
        }
    )
    
    # Cycle the output of the revision engine right back through the code gate verification step!
    workflow.add_edge("revise_hypothesis", "ground_check")
    
    workflow.add_edge("rank_hypotheses", "recommend_next_steps")
    workflow.add_edge("recommend_next_steps", END)

    return workflow.compile()

def run_pipeline(incident_bundle: dict, impact_path: dict | None = None) -> IncidentState:
    """
    The main execution wrapper called by the API.
    Transforms the raw incoming dict into our strict Pydantic state, 
    runs the LangGraph state machine, and spits the structured state back out.
    """
    app = build_app()
    
    initial_state = IncidentState(
        incident_id=incident_bundle["incident_id"],
        primary_node=incident_bundle["primary_node"],
        attack_cat=incident_bundle["attack_cat"],
        shap_features=incident_bundle["shap_features"],
        evidence_bundle=incident_bundle["evidence"],
        impact_path=impact_path,
        loop_count=0  # Initialize our new safety counter
    )
    
    # Execute the graph!
    result = app.invoke(initial_state)
    
    # LangGraph returns a dict representation of the state; 
    # we coerce it back into our strict Pydantic schema for the API response.
    return IncidentState(**result)