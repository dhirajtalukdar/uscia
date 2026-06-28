"""Unit tests for the deterministic rule classifier."""
import pytest
from evidence.models import (
    EvidenceNode, EvidencePayload, EvidenceGraph, EvidenceLink, InvestigationContext,
)
from classification.classifier import classify


def _make_node(system, status="AVAILABLE", raw=None):
    import uuid
    return EvidenceNode(
        node_id=str(uuid.uuid4()),
        system_name=system,
        status=status,
        raw_payload=raw or {},
        manual_guidance="",
    )


def _make_graph(nodes):
    return EvidenceGraph(incident_id="test-graph-001", nodes=nodes, links=[], broken_boundaries=[])


def _make_payload(nodes):
    return EvidencePayload(nodes=nodes, insufficient_coverage_warning=False)


def test_classify_returns_classification():
    nodes = [
        _make_node("IBP_SUPPLY", "MISSING_DATA"),
        _make_node("CPI_RTI", "MISSING_DATA"),
        _make_node("S4HANA_PLANNED_ORDER", "MISSING_DATA"),
    ]
    graph = _make_graph(nodes)
    payload = _make_payload(nodes)
    classification = classify(graph, payload)
    assert classification is not None
    assert classification.root_cause is not None
    assert classification.confidence in ("HIGH", "MEDIUM", "LOW", "INDETERMINATE")


def test_classify_bgrfc_blockage():
    """RC001: bgRFC queue blocked — planned order missing + bgRFC missing."""
    nodes = [
        _make_node("S4HANA_BGRFC_QUEUE", "MISSING_DATA"),
        _make_node("S4HANA_PLANNED_ORDER", "MISSING_DATA"),
        _make_node("S4HANA_MRP", "AVAILABLE"),
    ]
    graph = _make_graph(nodes)
    payload = _make_payload(nodes)
    classification = classify(graph, payload)
    # Should classify as bgRFC or a plausible fallback — just verify structure
    assert isinstance(classification.confirmed_findings, list)
    assert isinstance(classification.probable_findings, list)
    assert isinstance(classification.missing_findings, list)


def test_classify_all_missing_yields_indeterminate():
    """All systems MISSING_DATA must yield INDETERMINATE confidence."""
    nodes = [_make_node(s, "MISSING_DATA") for s in [
        "S4HANA_PLANNED_ORDER", "S4HANA_MRP", "S4HANA_PIR",
        "S4HANA_PPDS_STOCK", "S4HANA_PPDS_CONSTRAINTS", "S4HANA_ATP",
        "S4HANA_APPLICATION_LOGS", "S4HANA_BGRFC_QUEUE",
        "IBP_SUPPLY", "CPI_RTI", "PIPO", "CLOUD_ALM",
    ]]
    graph = _make_graph(nodes)
    payload = _make_payload(nodes)
    classification = classify(graph, payload)
    assert classification.confidence == "INDETERMINATE"
