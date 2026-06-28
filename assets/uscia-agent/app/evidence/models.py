"""
Data models for USCIA evidence collection, graph, classification, and reporting.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class InvestigationContext:
    material: str
    plant: str
    planning_version: str
    date_from: str
    date_to: str
    incident_type: str
    continuity_keys: dict = field(default_factory=dict)
    # KG Grounding fields — populated at M1 by kg_grounding.ground_investigation_context()
    # Carried through M2→M5 so narration layer can inject process context into the LLM prompt
    kg_process_context: str = ""           # SAP RBA chain description for this incident type
    kg_relevant_systems: list = field(default_factory=list)   # Priority system order from KG
    kg_disambiguated_terms: dict = field(default_factory=dict) # SAP term → functional name map
    kg_bp_ids: list = field(default_factory=list)              # e.g. ["BPS-327", "BPS-349"]
    kg_confidence: str = ""                # HIGH (live KG) | MEDIUM | LOW (fallback)
    kg_fallback_used: bool = True          # True = local fallback, False = live KG API


@dataclass
class EvidenceNode:
    node_id: str
    system_name: str
    status: str          # AVAILABLE | MISSING_DATA
    raw_payload: Any = None
    manual_guidance: str = ""
    kg_priority: bool = False   # True when system appears in KG-grounded relevant_systems list


@dataclass
class EvidenceLink:
    link_id: str
    from_node_id: str
    to_node_id: str
    continuity_key: str
    continuity_val: str
    broken_boundary: bool = False


@dataclass
class EvidencePayload:
    nodes: list = field(default_factory=list)
    available_count: int = 0
    unavailable_count: int = 0
    insufficient_coverage_warning: bool = False
    priority_systems: list = field(default_factory=list)  # KG-grounded system order (may be empty)


@dataclass
class EvidenceGraph:
    incident_id: str
    nodes: list = field(default_factory=list)
    links: list = field(default_factory=list)
    broken_boundaries: list = field(default_factory=list)


@dataclass
class RemediationAction:
    action_id: str
    action_type: str
    action_params: dict = field(default_factory=dict)
    requires_approval: bool = True
    rank: int = 1


@dataclass
class Classification:
    root_cause: str
    confidence: str
    confirmed_findings: list = field(default_factory=list)
    probable_findings: list = field(default_factory=list)
    missing_findings: list = field(default_factory=list)
    remediation_actions: list = field(default_factory=list)
    rule_id: str = ""
    description: str = ""


@dataclass
class NarrationResult:
    consultant_sections: dict = field(default_factory=dict)
    planner_sections: dict = field(default_factory=dict)
    fallback_used: bool = False


@dataclass
class ForensicReport:
    consultant_view: str
    planner_view: str
    persisted_incident_id: str
    sections_count: int = 14


@dataclass
class PatternResult:
    occurrence_count: int
    pattern_flagged: bool
    systemic: bool


@dataclass
class PredictiveAlert:
    signature_type: str
    historical_incident_ids: list
    affected_material: str
    affected_plant: str
    recommended_preventive_action: str
