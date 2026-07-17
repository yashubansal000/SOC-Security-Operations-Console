"""
Pure AI LLM Layer - Powered exclusively by Groq.
Updated for the Narrative-Only Architecture.
The scope is determined deterministically by the graph; the LLM only writes the narratives.

SETUP:
  1. Ensure GROQ_API_KEY is in your .env file.
  2. pip install groq
"""

import os
import json
import logging
from groq import Groq
from agent.schemas import Hypothesis, RemediationStep

logger = logging.getLogger("llm_layer")

GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
_client = None

def _get_client():
    """Requires a valid API key to proceed, no fallback allowed."""
    global _client
    if _client is not None:
        return _client

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError("CRITICAL: GROQ_API_KEY environment variable is missing. Cannot generate AI response.")

    _client = Groq(api_key=api_key)
    return _client


NARRATIVE_PROMPT = """You are a network root-cause analysis assistant.
Your code environment has already determined that the following node is a candidate root cause.
Your job is to write a single, highly plausible one-sentence causal claim explaining HOW the evidence makes this node the root cause of the incident.

Candidate Root-Cause Node: {node}
Attack Category: {attack_cat}
Evidence items linked specifically to this node:
{evidence_json}

CRITICAL RULES:
- You must write exactly ONE claim.
- Ground your claim STRICTLY in the provided evidence.
- Do not invent evidence or IDs.
- Include the evidence_ids you are actually citing accurately in the array.

Respond with ONLY a JSON object (no markdown fences, no extra text) in exactly this shape:
{{
  "claim": "string",
  "cited_evidence_ids": ["EV-1", "EV-2"]
}}
"""

REMEDIATION_PROMPT = """You are a network operations assistant. Given the following confirmed root-cause
hypothesis for an incident, propose 2-3 concrete remediation / diagnostic next steps.

Root cause claim: {claim}
Root cause node: {root_cause_node}
Attack category: {attack_cat}

Keep each step concrete and actionable (something an on-call engineer could execute directly),
and ground the rationale in the claim above - do not introduce new unverified facts.

Respond with ONLY a JSON object (no markdown fences, no extra text) in exactly this shape:
{{
  "steps": [
    {{"step": "string", "rationale": "string"}}
  ]
}}
"""


def mock_generate_narrative(node: str, evidence: list, attack_cat: str) -> Hypothesis:
    """Calls Groq dynamically to write a targeted narrative for a pre-scoped node."""
    client = _get_client()

    # Safely convert evidence objects to dicts if they are Pydantic models
    try:
        evidence_list = [e.model_dump() for e in evidence]
    except AttributeError:
        evidence_list = evidence

    prompt = NARRATIVE_PROMPT.format(
        node=node,
        attack_cat=attack_cat,
        evidence_json=json.dumps(evidence_list, indent=2)
    )

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {
                "role": "system",
                "content": "You are a precise assistant that only outputs valid JSON. Do not include any text outside the JSON object.",
            },
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
    )

    parsed = json.loads(response.choices[0].message.content)
    
    # We enforce the ID and node deterministically here so the LLM can't mess it up
    return Hypothesis(
        hypothesis_id=f"H_{node.replace('-', '_')}",
        claim=parsed["claim"],
        root_cause_node=node,
        cited_evidence_ids=parsed.get("cited_evidence_ids", [])
    )


def mock_recommend_next_steps(top_hypothesis: Hypothesis, attack_cat: str) -> list[RemediationStep]:
    """Calls Groq to generate dynamic remediation steps based on the winning claim."""
    client = _get_client()

    prompt = REMEDIATION_PROMPT.format(
        claim=top_hypothesis.claim,
        root_cause_node=top_hypothesis.root_cause_node,
        attack_cat=attack_cat,
    )

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {
                "role": "system",
                "content": "You are a precise assistant that only outputs valid JSON matching the requested schema. Do not include any text outside the JSON object.",
            },
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
    )

    parsed = json.loads(response.choices[0].message.content)
    steps = [RemediationStep(**s) for s in parsed["steps"]]

    if not steps:
        raise ValueError("Groq returned zero remediation steps.")

    return steps