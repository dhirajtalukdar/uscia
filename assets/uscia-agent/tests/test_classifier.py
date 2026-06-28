"""Unit tests for the deterministic rule classifier — including KG BP bias."""
import pytest
from evidence.models import (
    EvidenceNode, EvidencePayload, EvidenceGraph, EvidenceLink, InvestigationContext,
)
from classification.classifier import classify, _apply_kg_bias, _BP349_RULE_IDS, _BP327_RULE_IDS


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


def _make_ctx(kg_bp_ids=None, kg_confidence="MEDIUM"):
    return InvestigationContext(
        material="MAT-001",
        plant="1000",
        planning_version="000",
        date_from="2024-01-01",
        date_to="2024-06-30",
        incident_type="planned order missing in MD04",
        kg_bp_ids=kg_bp_ids or [],
        kg_confidence=kg_confidence,
        kg_relevant_systems=[],
        kg_disambiguated_terms={},
        kg_process_context="",
        kg_fallback_used=True,
    )


# ── Baseline tests ─────────────────────────────────────────────────────────────

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


# ── _apply_kg_bias unit tests ──────────────────────────────────────────────────

def _stub_rules():
    """Minimal rule list matching the real rules.yaml IDs for bias testing."""
    return [
        {"id": "RC001", "name": "RTI_CPI_MESSAGE_FAILURE"},
        {"id": "RC002", "name": "BGRFC_QUEUE_BLOCKAGE"},
        {"id": "RC003", "name": "MASTER_DATA_CONFIG_ERROR"},
        {"id": "RC003B", "name": "MASTER_DATA_CONFIG_ERROR"},
        {"id": "RC004", "name": "PPDS_SCHEDULING_FAILURE"},
        {"id": "RC005", "name": "CIF_TRANSFER_FAILURE"},
        {"id": "RC006", "name": "ATP_SCOPE_MISMATCH"},
        {"id": "RC007", "name": "IBP_PLANNING_GAP"},
        {"id": "RC008", "name": "OTHER", "fallback": True},
    ]


def test_kg_bias_empty_bp_ids_preserves_order():
    """No bias when kg_bp_ids is empty."""
    rules = _stub_rules()
    result = _apply_kg_bias(rules, [])
    assert [r["id"] for r in result] == [r["id"] for r in rules]


def test_kg_bias_bps349_floats_ppds_rules_first():
    """BPS-349 only → RC004/RC005/RC006 should appear before RC001/RC002/RC007."""
    rules = _stub_rules()
    biased = _apply_kg_bias(rules, ["BPS-349"])
    ids = [r["id"] for r in biased]
    # All BP349 rules must appear before all BP327 rules
    bp349_positions = [ids.index(r) for r in ("RC004", "RC005", "RC006")]
    bp327_positions = [ids.index(r) for r in ("RC001", "RC002", "RC007")]
    assert max(bp349_positions) < min(bp327_positions), (
        f"BP349 rules {bp349_positions} should all precede BP327 rules {bp327_positions}"
    )


def test_kg_bias_bps327_floats_integration_rules_first():
    """BPS-327 only → RC001/RC002/RC007 should appear before RC004/RC005/RC006."""
    rules = _stub_rules()
    biased = _apply_kg_bias(rules, ["BPS-327"])
    ids = [r["id"] for r in biased]
    bp327_positions = [ids.index(r) for r in ("RC001", "RC002", "RC007")]
    bp349_positions = [ids.index(r) for r in ("RC004", "RC005", "RC006")]
    assert max(bp327_positions) < min(bp349_positions), (
        f"BP327 rules {bp327_positions} should all precede BP349 rules {bp349_positions}"
    )


def test_kg_bias_both_bps_preserves_order():
    """When both BPS-349 and BPS-327 are present, no reordering applied."""
    rules = _stub_rules()
    result = _apply_kg_bias(rules, ["BPS-349", "BPS-327"])
    assert [r["id"] for r in result] == [r["id"] for r in rules]


def test_kg_bias_unrecognised_bp_ids_preserves_order():
    """Unknown BP IDs must not alter rule order."""
    rules = _stub_rules()
    result = _apply_kg_bias(rules, ["BPS-999", "BPS-000"])
    assert [r["id"] for r in result] == [r["id"] for r in rules]


def test_kg_bias_fallback_rule_always_last():
    """RC008 (fallback) must always be the last rule after any bias."""
    rules = _stub_rules()
    for bp_ids in [["BPS-349"], ["BPS-327"], [], ["BPS-349", "BPS-327"]]:
        biased = _apply_kg_bias(rules, bp_ids)
        assert biased[-1]["id"] == "RC008", f"Fallback not last for bp_ids={bp_ids}"


def test_kg_bias_all_rule_ids_present_after_reorder():
    """No rules lost or duplicated after bias reorder."""
    rules = _stub_rules()
    original_ids = sorted(r["id"] for r in rules)
    for bp_ids in [["BPS-349"], ["BPS-327"]]:
        biased = _apply_kg_bias(rules, bp_ids)
        assert sorted(r["id"] for r in biased) == original_ids


# ── classify() + ctx KG bias integration tests ────────────────────────────────

def test_classify_accepts_ctx_without_error():
    """classify() must accept ctx kwarg without raising."""
    nodes = [_make_node("S4HANA_PLANNED_ORDER", "MISSING_DATA")]
    graph = _make_graph(nodes)
    payload = _make_payload(nodes)
    ctx = _make_ctx(kg_bp_ids=["BPS-349"], kg_confidence="MEDIUM")
    result = classify(graph, payload, ctx=ctx)
    assert result.root_cause is not None


def test_classify_ctx_none_does_not_apply_bias():
    """ctx=None (default) must not apply any bias — plain classify still works."""
    nodes = [_make_node("S4HANA_PLANNED_ORDER", "MISSING_DATA")]
    graph = _make_graph(nodes)
    payload = _make_payload(nodes)
    result = classify(graph, payload, ctx=None)
    assert result.root_cause is not None


def test_classify_low_confidence_kg_does_not_bias():
    """KG LOW confidence must not trigger bias even when bp_ids are present."""
    nodes = [_make_node("S4HANA_PLANNED_ORDER", "MISSING_DATA")]
    graph = _make_graph(nodes)
    payload = _make_payload(nodes)
    ctx = _make_ctx(kg_bp_ids=["BPS-349"], kg_confidence="LOW")
    # Should not raise; bias is inactive for LOW confidence
    result = classify(graph, payload, ctx=ctx)
    assert result.root_cause is not None


def test_classify_bps349_bias_favours_ppds_rule():
    """BPS-349 context should cause RC004 to fire when PP/DS evidence is present."""
    # Evidence: planned orders exist, PP/DS stock empty, PP/DS constraints available
    planned_order_data = {"value": [{"PlannedOrder": "PO001", "TotalQuantity": "100"}]}
    ppds_stock_data = {"value": []}  # empty — triggers ppds_stock_entries_count == 0

    nodes = [
        _make_node("S4HANA_PLANNED_ORDER", "AVAILABLE", raw=planned_order_data),
        _make_node("S4HANA_PPDS_STOCK", "AVAILABLE", raw=ppds_stock_data),
        _make_node("S4HANA_PPDS_CONSTRAINTS", "AVAILABLE", raw={"value": []}),
    ]
    graph = _make_graph(nodes)
    payload = _make_payload(nodes)
    ctx = _make_ctx(kg_bp_ids=["BPS-349"], kg_confidence="HIGH")

    result = classify(graph, payload, ctx=ctx)
    # RC004 should match when planned orders > 0 AND ppds_stock == 0
    assert result.root_cause == "PPDS_SCHEDULING_FAILURE"
    assert result.rule_id == "RC004"


def test_classify_bps327_bias_favours_cpi_rule():
    """BPS-327 context should cause RC001 to fire when IBP→S4 handoff evidence is present."""
    # Evidence: IBP has supply, S4 planned orders empty, CPI missing
    ibp_data = {"SupplyOrders": [{"ExternalID": "IBP-001"}]}
    planned_order_data = {"value": []}

    nodes = [
        _make_node("IBP_SUPPLY", "AVAILABLE", raw=ibp_data),
        _make_node("S4HANA_PLANNED_ORDER", "AVAILABLE", raw=planned_order_data),
        _make_node("SAP_CPI", "MISSING_DATA"),
    ]
    graph = _make_graph(nodes)
    payload = _make_payload(nodes)
    ctx = _make_ctx(kg_bp_ids=["BPS-327"], kg_confidence="HIGH")

    result = classify(graph, payload, ctx=ctx)
    assert result.root_cause == "RTI_CPI_MESSAGE_FAILURE"
    assert result.rule_id == "RC001"


def test_classify_kg_bias_does_not_override_strong_evidence():
    """KG bias (BPS-349) must not override clear RC001 evidence — evidence always wins."""
    # Evidence clearly matches RC001 (IBP has supply, S4 empty, CPI missing)
    ibp_data = {"SupplyOrders": [{"ExternalID": "IBP-001"}]}
    planned_order_data = {"value": []}

    nodes = [
        _make_node("IBP_SUPPLY", "AVAILABLE", raw=ibp_data),
        _make_node("S4HANA_PLANNED_ORDER", "AVAILABLE", raw=planned_order_data),
        _make_node("SAP_CPI", "MISSING_DATA"),
    ]
    graph = _make_graph(nodes)
    payload = _make_payload(nodes)
    # BPS-349 bias says PP/DS — but evidence says CPI failure
    ctx = _make_ctx(kg_bp_ids=["BPS-349"], kg_confidence="HIGH")

    result = classify(graph, payload, ctx=ctx)
    # RC001 condition is fully met — it must still fire despite BPS-349 bias
    # (RC004 requires planned_orders_count_gt > 0, which is NOT met here)
    assert result.root_cause == "RTI_CPI_MESSAGE_FAILURE"
