"""Pydantic models for the Module 4 agent state and outputs."""

from typing import Optional
from pydantic import BaseModel, Field


class EvidenceItem(BaseModel):
    evidence_id: str
    tier: str  # "confirmed" | "correlated" | "missing"
    type: str
    node: str
    timestamp: Optional[str] = None
    description: str


class Hypothesis(BaseModel):
    hypothesis_id: str
    claim: str
    root_cause_node: str
    cited_evidence_ids: list[str]
    grounded: bool = False
    rejected_reason: Optional[str] = None
    confidence: Optional[float] = None
    evidence_tier_breakdown: Optional[dict] = None


class RemediationStep(BaseModel):
    step: str
    rationale: str


class IncidentState(BaseModel):
    """The object that flows through every LangGraph node."""

    incident_id: str
    primary_node: str
    attack_cat: str
    shap_features: list[dict]
    evidence_bundle: list[EvidenceItem]
    impact_path: Optional[dict] = None

    candidate_hypotheses: list[Hypothesis] = Field(default_factory=list)
    grounded_hypotheses: list[Hypothesis] = Field(default_factory=list)
    ranked_hypotheses: list[Hypothesis] = Field(default_factory=list)
    remediation: list[RemediationStep] = Field(default_factory=list)

    log: list[str] = Field(default_factory=list)  # trace of what each node did,
    # useful for both debugging and the "show your work" demo moment
    
    # CRUCIAL ADDITION: Tracks revision iterations to prevent infinite demo hangs
    loop_count: int = Field(default=0)