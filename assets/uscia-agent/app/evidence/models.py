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


@dataclass
class EvidenceNode:
    node_id: str
    system_name: str
    status: str          # AVAILABLE | MISSING_DATA
    raw_payload: Any = None
    manual_guidance: str = ""


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
