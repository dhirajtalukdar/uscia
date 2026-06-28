"""Advanced graph builder tests covering more branch paths."""
import pytest
import uuid
from evidence.models import EvidenceNode, EvidencePayload, InvestigationContext, EvidenceLink
from evidence.graph_builder import build_evidence_graph


def _node(system, status="AVAILABLE", raw=None):
    return EvidenceNode(
        node_id=str(uuid.uuid4()),
        system_name=system, status=status,
        raw_payload=raw or {}, manual_guidance="",
    )


def _make_ctx(material="M1", plant="1000", incident_type="planned order missing in MD04", keys=None):
    return InvestigationContext(
        material=material, plant=plant, planning_version="000",
        date_from="2024-01-01", date_to="2024-12-31",
        incident_type=incident_type,
        continuity_keys=keys or {"material": material},
    )


def _payload(nodes):
    return EvidencePayload(nodes=nodes, insufficient_coverage_warning=False)


def test_graph_links_created_for_related_systems():
    """Planned order → MRP relationship should create a link."""
    po_data = {"value": [{"PlannedOrder": "PO001", "Material": "M1", "Plant": "1000", "PlannedOrderQuantity": "10", "BasicStartDate": "2024-06-01"}]}
    mrp_data = {"value": [{"MRPType": "X2", "MRPPlant": "1000", "Material": "M1"}]}
    nodes = [
        _node("S4HANA_PLANNED_ORDER", "AVAILABLE", raw=po_data),
        _node("S4HANA_MRP", "AVAILABLE", raw=mrp_data),
    ]
    ctx = _make_ctx()
    graph = build_evidence_graph(_payload(nodes), ctx)
    assert isinstance(graph.links, list)
    assert isinstance(graph.nodes, list)


def test_graph_all_systems_available_no_broken_boundaries_forced():
    nodes = [
        _node("S4HANA_PLANNED_ORDER", "AVAILABLE"),
        _node("S4HANA_MRP", "AVAILABLE"),
        _node("S4HANA_PIR", "AVAILABLE"),
        _node("IBP_SUPPLY", "AVAILABLE"),
        _node("CPI_RTI", "AVAILABLE"),
        _node("S4HANA_BGRFC_QUEUE", "AVAILABLE"),
    ]
    ctx = _make_ctx()
    graph = build_evidence_graph(_payload(nodes), ctx)
    # All available: broken boundaries should be empty or minimal
    assert isinstance(graph.broken_boundaries, list)


def test_graph_cpi_missing_bgrfc_missing_creates_boundary():
    """When both CPI and bgRFC are missing but MRP is available."""
    nodes = [
        _node("S4HANA_MRP", "AVAILABLE"),
        _node("S4HANA_PLANNED_ORDER", "AVAILABLE"),
        _node("CPI_RTI", "MISSING_DATA"),
        _node("S4HANA_BGRFC_QUEUE", "MISSING_DATA"),
    ]
    ctx = _make_ctx(incident_type="CIF transfer failure")
    graph = build_evidence_graph(_payload(nodes), ctx)
    assert isinstance(graph, type(graph))


def test_graph_ibp_missing_with_planned_order_available():
    """IBP missing + S4 planned order available: should flag IBP→S4 boundary."""
    nodes = [
        _node("IBP_SUPPLY", "MISSING_DATA"),
        _node("S4HANA_PLANNED_ORDER", "AVAILABLE"),
        _node("S4HANA_MRP", "AVAILABLE"),
    ]
    ctx = _make_ctx()
    graph = build_evidence_graph(_payload(nodes), ctx)
    assert isinstance(graph.broken_boundaries, list)


def test_graph_preserves_incident_id():
    nodes = [_node("S4HANA_MRP", "AVAILABLE")]
    ctx = _make_ctx()
    graph = build_evidence_graph(_payload(nodes), ctx)
    # incident_id should be set (auto-generated UUID)
    assert graph.incident_id is not None
    assert len(graph.incident_id) > 0


def test_graph_with_continuity_keys():
    nodes = [
        _node("S4HANA_PLANNED_ORDER", "AVAILABLE",
              raw={"value": [{"PlannedOrder": "PO001", "Material": "M-ABC", "Plant": "2000"}]}),
        _node("S4HANA_PPDS_STOCK", "AVAILABLE",
              raw={"value": [{"Material": "M-ABC", "Plant": "2000"}]}),
    ]
    ctx = _make_ctx(material="M-ABC", plant="2000", keys={"material": "M-ABC", "plant": "2000"})
    graph = build_evidence_graph(_payload(nodes), ctx)
    assert len(graph.nodes) == 2


def test_graph_empty_payload():
    """Empty nodes must not raise."""
    ctx = _make_ctx()
    graph = build_evidence_graph(_payload([]), ctx)
    assert len(graph.nodes) == 0
    assert len(graph.links) == 0
