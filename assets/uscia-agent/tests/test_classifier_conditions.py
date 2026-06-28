"""Additional classifier coverage tests for condition evaluation and all rules."""
import pytest
import uuid
from evidence.models import (
    EvidenceNode, EvidencePayload, EvidenceGraph, Classification,
)
from classification.classifier import classify, _check_conditions, _is_available, _is_missing


def _node(system, status="AVAILABLE", raw=None):
    return EvidenceNode(
        node_id=str(uuid.uuid4()),
        system_name=system, status=status,
        raw_payload=raw or {},
        manual_guidance=f"Check {system}",
    )


def _payload(nodes):
    return EvidencePayload(nodes=nodes, insufficient_coverage_warning=False)


def _graph(nodes):
    return EvidenceGraph(incident_id="g-test", nodes=nodes, links=[], broken_boundaries=[])


def test_is_available_true():
    nodes = [_node("S4HANA_MRP", "AVAILABLE")]
    payload = _payload(nodes)
    assert _is_available(payload, "S4HANA_MRP") is True


def test_is_available_false():
    nodes = [_node("S4HANA_MRP", "MISSING_DATA")]
    payload = _payload(nodes)
    assert _is_available(payload, "S4HANA_MRP") is False


def test_is_missing_true():
    nodes = [_node("S4HANA_BGRFC_QUEUE", "MISSING_DATA")]
    payload = _payload(nodes)
    assert _is_missing(payload, "S4HANA_BGRFC_QUEUE") is True


def test_classify_with_mrp_available_po_missing():
    """RC002 or RC003-style: MRP available but planned orders missing."""
    nodes = [
        _node("S4HANA_MRP", "AVAILABLE"),
        _node("S4HANA_PLANNED_ORDER", "MISSING_DATA"),
        _node("S4HANA_PIR", "AVAILABLE"),
        _node("S4HANA_PPDS_STOCK", "AVAILABLE"),
        _node("S4HANA_PPDS_CONSTRAINTS", "AVAILABLE"),
        _node("S4HANA_ATP", "AVAILABLE"),
        _node("S4HANA_APPLICATION_LOGS", "AVAILABLE"),
        _node("S4HANA_BGRFC_QUEUE", "AVAILABLE"),
        _node("IBP_SUPPLY", "AVAILABLE"),
        _node("CPI_RTI", "AVAILABLE"),
        _node("PIPO", "AVAILABLE"),
        _node("CLOUD_ALM", "AVAILABLE"),
    ]
    payload = _payload(nodes)
    graph = _graph(nodes)
    result = classify(graph, payload)
    assert result.confidence in ("HIGH", "MEDIUM", "LOW", "INDETERMINATE")
    assert result.root_cause is not None


def test_classify_rc001_bgrfc_pattern():
    """RC001: bgRFC queue missing + planned order missing."""
    nodes = [
        _node("S4HANA_BGRFC_QUEUE", "MISSING_DATA"),
        _node("S4HANA_PLANNED_ORDER", "MISSING_DATA"),
        _node("S4HANA_MRP", "AVAILABLE", raw={"value": [{"MRPType": "X2"}]}),
        _node("S4HANA_PIR", "AVAILABLE"),
        _node("IBP_SUPPLY", "AVAILABLE"),
        _node("CPI_RTI", "AVAILABLE"),
        _node("PIPO", "AVAILABLE"),
        _node("CLOUD_ALM", "AVAILABLE"),
    ]
    payload = _payload(nodes)
    graph = _graph(nodes)
    result = classify(graph, payload)
    assert result.root_cause is not None
    assert len(result.confirmed_findings) > 0


def test_classify_returns_remediation_actions():
    nodes = [
        _node("S4HANA_PLANNED_ORDER", "AVAILABLE"),
        _node("S4HANA_MRP", "AVAILABLE"),
    ]
    payload = _payload(nodes)
    graph = _graph(nodes)
    result = classify(graph, payload)
    assert len(result.remediation_actions) >= 1
    for action in result.remediation_actions:
        assert action.requires_approval is True


def test_classify_confirmed_findings_tagged():
    nodes = [_node("S4HANA_MRP", "AVAILABLE"), _node("S4HANA_PLANNED_ORDER", "AVAILABLE")]
    payload = _payload(nodes)
    graph = _graph(nodes)
    result = classify(graph, payload)
    for finding in result.confirmed_findings:
        assert "[CONFIRMED]" in finding


def test_classify_missing_findings_tagged():
    nodes = [_node("S4HANA_BGRFC_QUEUE", "MISSING_DATA")]
    payload = _payload(nodes)
    graph = _graph(nodes)
    result = classify(graph, payload)
    for finding in result.missing_findings:
        assert "[MISSING DATA]" in finding


def test_classify_rule_id_set():
    nodes = [_node("S4HANA_MRP", "AVAILABLE")]
    payload = _payload(nodes)
    graph = _graph(nodes)
    result = classify(graph, payload)
    assert result.rule_id.startswith("RC")


def test_check_conditions_pass_empty_conditions():
    nodes = [_node("S4HANA_MRP", "AVAILABLE")]
    payload = _payload(nodes)
    assert _check_conditions({"conditions": {}}, payload) is True


def test_check_conditions_ibp_has_supply_false_when_no_data():
    """When IBP has no data dict at all, ibp_has_supply should fail."""
    nodes = [_node("IBP_SUPPLY", "MISSING_DATA", raw={})]
    payload = _payload(nodes)
    rule = {"conditions": {"ibp_has_supply": True}}
    result = _check_conditions(rule, payload)
    assert result is False


def test_check_conditions_ibp_has_supply_true_when_data():
    nodes = [_node("IBP_SUPPLY", "AVAILABLE", raw={"value": [{"order": "1"}]})]
    payload = _payload(nodes)
    rule = {"conditions": {"ibp_has_supply": True}}
    result = _check_conditions(rule, payload)
    assert result is True
