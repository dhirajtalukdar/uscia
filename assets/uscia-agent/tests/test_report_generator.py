"""Unit tests for the 14-section forensic report generator."""
import pytest
from evidence.models import (
    Classification, EvidenceGraph, EvidenceNode, ForensicReport,
    InvestigationContext, NarrationResult, RemediationAction,
)
from report.generator import generate_report, _SECTIONS


def _make_ctx():
    return InvestigationContext(
        material="MAT-001", plant="1000", planning_version="000",
        date_from="2024-01-01", date_to="2024-12-31",
        incident_type="planned order missing in MD04", continuity_keys={},
    )


def _make_node(system, status="AVAILABLE"):
    import uuid
    return EvidenceNode(
        node_id=str(uuid.uuid4()),
        system_name=system, status=status,
        raw_payload={}, manual_guidance="",
    )


def _make_action(rank=1):
    import uuid
    return RemediationAction(
        action_id=str(uuid.uuid4()),
        action_type="MANUAL_ONLY", action_params={},
        requires_approval=True, rank=rank,
    )


def _make_classification(actions=None):
    return Classification(
        root_cause="BGRFC_QUEUE_BLOCKAGE",
        confidence="HIGH",
        rule_id="RC001",
        description="bgRFC queue is blocked.",
        remediation_actions=actions or [_make_action()],
        confirmed_findings=["[CONFIRMED] bgRFC queue missing"],
        probable_findings=[],
        missing_findings=["[MISSING DATA] CPI data"],
    )


def _make_graph():
    return EvidenceGraph(
        incident_id="test-graph-001",
        nodes=[_make_node("S4HANA_BGRFC_QUEUE", "MISSING_DATA"), _make_node("S4HANA_MRP")],
        links=[],
        broken_boundaries=["S4HANA_MRP → S4HANA_PLANNED_ORDER"],
    )


def _make_narration():
    return NarrationResult(
        consultant_sections={"executive_summary": "Test exec summary."},
        planner_sections={},
        fallback_used=False,
    )


def test_generate_report_returns_forensic_report():
    report = generate_report(
        narration=_make_narration(),
        classification=_make_classification(),
        graph=_make_graph(),
        ctx=_make_ctx(),
        incident_id="test-uuid-001",
    )
    assert isinstance(report, ForensicReport)
    assert report.sections_count == 14


def test_generate_report_all_14_sections_in_consultant_view():
    report = generate_report(
        narration=_make_narration(),
        classification=_make_classification(),
        graph=_make_graph(),
        ctx=_make_ctx(),
        incident_id="test-uuid-002",
    )
    for _, header in _SECTIONS:
        assert header in report.consultant_view, f"Missing section: {header}"


def test_generate_report_all_14_sections_in_planner_view():
    report = generate_report(
        narration=_make_narration(),
        classification=_make_classification(),
        graph=_make_graph(),
        ctx=_make_ctx(),
        incident_id="test-uuid-003",
    )
    for _, header in _SECTIONS:
        assert header in report.planner_view, f"Missing section in planner view: {header}"


def test_generate_report_machine_readable_actions():
    action = _make_action(rank=1)
    report = generate_report(
        narration=_make_narration(),
        classification=_make_classification(actions=[action]),
        graph=_make_graph(),
        ctx=_make_ctx(),
        incident_id="test-uuid-004",
    )
    assert "requires_approval: True" in report.consultant_view
    assert "MANUAL_ONLY" in report.consultant_view


def test_generate_report_with_pattern_result():
    from evidence.models import PatternResult
    pattern = PatternResult(occurrence_count=5, pattern_flagged=True, systemic=True)
    report = generate_report(
        narration=_make_narration(),
        classification=_make_classification(),
        graph=_make_graph(),
        ctx=_make_ctx(),
        incident_id="test-uuid-005",
        pattern_result=pattern,
    )
    assert "SYSTEMIC ISSUE DETECTED" in report.consultant_view


def test_generate_report_missing_sections_get_placeholder():
    report = generate_report(
        narration=NarrationResult(consultant_sections={}, planner_sections={}, fallback_used=True),
        classification=_make_classification(),
        graph=_make_graph(),
        ctx=_make_ctx(),
        incident_id="test-uuid-006",
    )
    # All 14 sections must still be present (filled by auto_section or placeholder)
    assert report.sections_count == 14
    for _, header in _SECTIONS:
        assert header in report.consultant_view
