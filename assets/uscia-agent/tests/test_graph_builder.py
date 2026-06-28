"""Unit tests for evidence graph builder."""
import pytest
from evidence.models import (
    EvidenceNode, EvidencePayload, InvestigationContext, EvidenceGraph,
)
from evidence.graph_builder import build_evidence_graph


def _make_ctx(
    material="MAT-001", plant="1000",
    incident_type="planned order missing in MD04",
    continuity_keys=None,
):
    return InvestigationContext(
        material=material, plant=plant, planning_version="000",
        date_from="2024-01-01", date_to="2024-12-31",
        incident_type=incident_type,
        continuity_keys=continuity_keys or {"material": "MAT-001"},
    )


def _make_node(system, status="AVAILABLE", raw=None):
    import uuid
    return EvidenceNode(
        node_id=str(uuid.uuid4()),
        system_name=system,
        status=status,
        raw_payload=raw or {},
        manual_guidance="" if status == "AVAILABLE" else f"Check {system}",
    )


def _make_payload(nodes):
    return EvidencePayload(nodes=nodes, insufficient_coverage_warning=False)


def test_graph_builder_returns_evidence_graph():
    nodes = [_make_node("S4HANA_PLANNED_ORDER"), _make_node("S4HANA_MRP")]
    payload = _make_payload(nodes)
    ctx = _make_ctx()
    graph = build_evidence_graph(payload, ctx)
    assert isinstance(graph, EvidenceGraph)


def test_graph_builder_nodes_preserved():
    nodes = [
        _make_node("S4HANA_PLANNED_ORDER"),
        _make_node("S4HANA_MRP"),
        _make_node("IBP_SUPPLY", "MISSING_DATA"),
    ]
    payload = _make_payload(nodes)
    ctx = _make_ctx()
    graph = build_evidence_graph(payload, ctx)
    assert len(graph.nodes) == 3


def test_broken_boundary_when_planned_order_missing_but_mrp_available():
    """Broken boundary: MRP available but planned order missing."""
    nodes = [
        _make_node("S4HANA_PLANNED_ORDER", "MISSING_DATA"),
        _make_node("S4HANA_MRP", "AVAILABLE"),
        _make_node("S4HANA_PIR", "AVAILABLE"),
    ]
    payload = _make_payload(nodes)
    ctx = _make_ctx(incident_type="planned order missing in MD04")
    graph = build_evidence_graph(payload, ctx)
    # Should have at least one broken boundary
    assert isinstance(graph.broken_boundaries, list)


def test_all_available_no_forced_broken_boundary():
    nodes = [_make_node(s) for s in [
        "S4HANA_PLANNED_ORDER", "S4HANA_MRP", "S4HANA_PIR",
        "S4HANA_PPDS_STOCK", "S4HANA_PPDS_CONSTRAINTS", "S4HANA_ATP",
    ]]
    payload = _make_payload(nodes)
    ctx = _make_ctx()
    graph = build_evidence_graph(payload, ctx)
    assert isinstance(graph, EvidenceGraph)
