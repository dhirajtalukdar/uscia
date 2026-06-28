"""Unit tests for evidence collector — parallel gather, MISSING_DATA handling,
KG system prioritisation, BDC integration, and IBP job monitor.

System count: 15 (14 original + IBP_JOB_MONITOR added as 15th system).
"""
import pytest
from unittest.mock import patch, AsyncMock
from evidence.models import InvestigationContext


def _make_ctx(kg_relevant_systems=None):
    return InvestigationContext(
        material="MAT-001", plant="1000", planning_version="000",
        date_from="2024-01-01", date_to="2024-12-31",
        incident_type="planned order missing in MD04", continuity_keys={},
        kg_relevant_systems=kg_relevant_systems or [],
    )


def _missing(system: str) -> dict:
    return {"status": "MISSING_DATA", "system": system, "guidance": f"Check {system} manually."}


def _available(system: str, data=None) -> dict:
    return {"status": "AVAILABLE", "system": system, "data": data or [{"key": "val"}]}


def _all_missing_patches():
    """Return patch context for all 15 systems returning MISSING_DATA."""
    return [
        patch("evidence.collector.get_planned_orders",                  AsyncMock(return_value=_missing("S4HANA_PLANNED_ORDER"))),
        patch("evidence.collector.get_material_planning_data",          AsyncMock(return_value=_missing("S4HANA_MATERIAL_PLANNING"))),
        patch("evidence.collector.get_planned_independent_requirements", AsyncMock(return_value=_missing("S4HANA_PIR"))),
        patch("evidence.collector.get_ppds_stock_level",                AsyncMock(return_value=_missing("S4HANA_PPDS_STOCK"))),
        patch("evidence.collector.get_ppds_flexible_constraints",       AsyncMock(return_value=_missing("S4HANA_PPDS_CONSTRAINTS"))),
        patch("evidence.collector.get_atp_check_result",                AsyncMock(return_value=_missing("S4HANA_ATP"))),
        patch("evidence.collector.get_application_logs",                AsyncMock(return_value=_missing("S4HANA_APPLICATION_LOGS"))),
        patch("evidence.collector.get_bgrfc_queue_status",              AsyncMock(return_value=_missing("S4HANA_BGRFC_QUEUE"))),
        patch("evidence.collector.get_ppds_config_and_mrp_issues",      AsyncMock(return_value=_missing("S4HANA_PPDS_CONFIG"))),
        patch("evidence.collector.get_ibp_supply_data",                 AsyncMock(return_value=_missing("IBP_SUPPLY"))),
        patch("evidence.collector.get_cpi_message_status",              AsyncMock(return_value=_missing("SAP_CPI"))),
        patch("evidence.collector.get_pipo_message_status",             AsyncMock(return_value=_missing("SAP_PIPO"))),
        patch("evidence.collector.get_cloud_alm_health_events",         AsyncMock(return_value=_missing("CLOUD_ALM"))),
        patch("evidence.collector.get_bdc_supply_chain_analytics",      AsyncMock(return_value=_missing("SAP_BDC"))),
        patch("evidence.collector.get_ibp_job_status",                  AsyncMock(return_value=_missing("IBP_JOB_MONITOR"))),
    ]


@pytest.mark.asyncio
async def test_collector_all_missing():
    """All 15 systems return MISSING_DATA — payload must have 15 nodes all MISSING_DATA."""
    patches = _all_missing_patches()
    for p in patches:
        p.start()
    try:
        from evidence.collector import collect_evidence
        ctx = _make_ctx()
        payload = await collect_evidence(ctx)
    finally:
        for p in patches:
            p.stop()

    assert len(payload.nodes) == 15
    missing_nodes = [n for n in payload.nodes if n.status == "MISSING_DATA"]
    assert len(missing_nodes) == 15
    assert payload.insufficient_coverage_warning is True


@pytest.mark.asyncio
async def test_collector_partial_available():
    """3 systems available — payload must correctly count available/missing nodes."""
    with patch("evidence.collector.get_planned_orders",                  AsyncMock(return_value=_available("S4HANA_PLANNED_ORDER"))), \
         patch("evidence.collector.get_material_planning_data",          AsyncMock(return_value=_available("S4HANA_MATERIAL_PLANNING"))), \
         patch("evidence.collector.get_planned_independent_requirements", AsyncMock(return_value=_available("S4HANA_PIR"))), \
         patch("evidence.collector.get_ppds_stock_level",                AsyncMock(return_value=_missing("S4HANA_PPDS_STOCK"))), \
         patch("evidence.collector.get_ppds_flexible_constraints",       AsyncMock(return_value=_missing("S4HANA_PPDS_CONSTRAINTS"))), \
         patch("evidence.collector.get_atp_check_result",                AsyncMock(return_value=_missing("S4HANA_ATP"))), \
         patch("evidence.collector.get_application_logs",                AsyncMock(return_value=_missing("S4HANA_APPLICATION_LOGS"))), \
         patch("evidence.collector.get_bgrfc_queue_status",              AsyncMock(return_value=_missing("S4HANA_BGRFC_QUEUE"))), \
         patch("evidence.collector.get_ppds_config_and_mrp_issues",      AsyncMock(return_value=_missing("S4HANA_PPDS_CONFIG"))), \
         patch("evidence.collector.get_ibp_supply_data",                 AsyncMock(return_value=_missing("IBP_SUPPLY"))), \
         patch("evidence.collector.get_cpi_message_status",              AsyncMock(return_value=_missing("SAP_CPI"))), \
         patch("evidence.collector.get_pipo_message_status",             AsyncMock(return_value=_missing("SAP_PIPO"))), \
         patch("evidence.collector.get_cloud_alm_health_events",         AsyncMock(return_value=_missing("CLOUD_ALM"))), \
         patch("evidence.collector.get_bdc_supply_chain_analytics",      AsyncMock(return_value=_missing("SAP_BDC"))), \
         patch("evidence.collector.get_ibp_job_status",                  AsyncMock(return_value=_missing("IBP_JOB_MONITOR"))):
        from evidence.collector import collect_evidence
        ctx = _make_ctx()
        payload = await collect_evidence(ctx)

    available_nodes = [n for n in payload.nodes if n.status == "AVAILABLE"]
    missing_nodes = [n for n in payload.nodes if n.status == "MISSING_DATA"]
    assert len(available_nodes) == 3
    assert len(missing_nodes) == 12
    assert len(payload.nodes) == 15
    assert payload.insufficient_coverage_warning is False


@pytest.mark.asyncio
async def test_collector_insufficient_coverage_warning():
    """Fewer than 3 available systems triggers insufficient_coverage_warning=True."""
    with patch("evidence.collector.get_planned_orders",                  AsyncMock(return_value=_available("S4HANA_PLANNED_ORDER"))), \
         patch("evidence.collector.get_material_planning_data",          AsyncMock(return_value=_missing("S4HANA_MATERIAL_PLANNING"))), \
         patch("evidence.collector.get_planned_independent_requirements", AsyncMock(return_value=_missing("S4HANA_PIR"))), \
         patch("evidence.collector.get_ppds_stock_level",                AsyncMock(return_value=_missing("S4HANA_PPDS_STOCK"))), \
         patch("evidence.collector.get_ppds_flexible_constraints",       AsyncMock(return_value=_missing("S4HANA_PPDS_CONSTRAINTS"))), \
         patch("evidence.collector.get_atp_check_result",                AsyncMock(return_value=_missing("S4HANA_ATP"))), \
         patch("evidence.collector.get_application_logs",                AsyncMock(return_value=_missing("S4HANA_APPLICATION_LOGS"))), \
         patch("evidence.collector.get_bgrfc_queue_status",              AsyncMock(return_value=_missing("S4HANA_BGRFC_QUEUE"))), \
         patch("evidence.collector.get_ppds_config_and_mrp_issues",      AsyncMock(return_value=_missing("S4HANA_PPDS_CONFIG"))), \
         patch("evidence.collector.get_ibp_supply_data",                 AsyncMock(return_value=_missing("IBP_SUPPLY"))), \
         patch("evidence.collector.get_cpi_message_status",              AsyncMock(return_value=_missing("SAP_CPI"))), \
         patch("evidence.collector.get_pipo_message_status",             AsyncMock(return_value=_missing("SAP_PIPO"))), \
         patch("evidence.collector.get_cloud_alm_health_events",         AsyncMock(return_value=_missing("CLOUD_ALM"))), \
         patch("evidence.collector.get_bdc_supply_chain_analytics",      AsyncMock(return_value=_missing("SAP_BDC"))), \
         patch("evidence.collector.get_ibp_job_status",                  AsyncMock(return_value=_missing("IBP_JOB_MONITOR"))):
        from evidence.collector import collect_evidence
        ctx = _make_ctx()
        payload = await collect_evidence(ctx)

    assert payload.insufficient_coverage_warning is True
    assert payload.available_count == 1


# ──────────────────────────────────────────────────────────────────────────────
# KG system prioritisation tests
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_kg_priority_tags_nodes():
    """
    When ctx.kg_relevant_systems = ['SAP_CPI', 'S4HANA_BGRFC_QUEUE'],
    those nodes must have kg_priority=True and appear first in payload.nodes.
    """
    patches = _all_missing_patches()
    for p in patches:
        p.start()
    try:
        from evidence.collector import collect_evidence
        ctx = _make_ctx(kg_relevant_systems=["SAP_CPI", "S4HANA_BGRFC_QUEUE"])
        payload = await collect_evidence(ctx)
    finally:
        for p in patches:
            p.stop()

    # First two nodes must be the KG-priority systems
    assert payload.nodes[0].system_name in ("SAP_CPI", "S4HANA_BGRFC_QUEUE")
    assert payload.nodes[1].system_name in ("SAP_CPI", "S4HANA_BGRFC_QUEUE")

    # They must be tagged
    priority_nodes = [n for n in payload.nodes if n.kg_priority]
    assert len(priority_nodes) == 2
    priority_names = {n.system_name for n in priority_nodes}
    assert "SAP_CPI" in priority_names
    assert "S4HANA_BGRFC_QUEUE" in priority_names

    # Non-priority nodes must NOT be tagged
    other_nodes = [n for n in payload.nodes if not n.kg_priority]
    assert all(not n.kg_priority for n in other_nodes)


@pytest.mark.asyncio
async def test_kg_priority_stored_in_payload():
    """payload.priority_systems must mirror ctx.kg_relevant_systems."""
    patches = _all_missing_patches()
    for p in patches:
        p.start()
    try:
        from evidence.collector import collect_evidence
        ctx = _make_ctx(kg_relevant_systems=["IBP_SUPPLY", "SAP_CPI"])
        payload = await collect_evidence(ctx)
    finally:
        for p in patches:
            p.stop()

    assert payload.priority_systems == ["IBP_SUPPLY", "SAP_CPI"]


@pytest.mark.asyncio
async def test_no_kg_priority_when_empty():
    """When ctx.kg_relevant_systems is empty, all nodes have kg_priority=False."""
    patches = _all_missing_patches()
    for p in patches:
        p.start()
    try:
        from evidence.collector import collect_evidence
        ctx = _make_ctx(kg_relevant_systems=[])
        payload = await collect_evidence(ctx)
    finally:
        for p in patches:
            p.stop()

    assert payload.priority_systems == []
    assert all(not n.kg_priority for n in payload.nodes)


@pytest.mark.asyncio
async def test_all_15_systems_always_queried():
    """Even with KG priority, ALL 15 systems appear in the payload."""
    patches = _all_missing_patches()
    for p in patches:
        p.start()
    try:
        from evidence.collector import collect_evidence
        ctx = _make_ctx(kg_relevant_systems=["SAP_CPI"])
        payload = await collect_evidence(ctx)
    finally:
        for p in patches:
            p.stop()

    names = {n.system_name for n in payload.nodes}
    expected = {
        "S4HANA_PLANNED_ORDER", "S4HANA_MATERIAL_PLANNING", "S4HANA_PIR",
        "S4HANA_PPDS_STOCK", "S4HANA_PPDS_CONSTRAINTS", "S4HANA_ATP",
        "S4HANA_APPLICATION_LOGS", "S4HANA_BGRFC_QUEUE", "S4HANA_PPDS_CONFIG",
        "IBP_SUPPLY", "SAP_CPI", "SAP_PIPO", "CLOUD_ALM", "SAP_BDC",
        "IBP_JOB_MONITOR",
    }
    assert names == expected


# ──────────────────────────────────────────────────────────────────────────────
# BDC integration tests
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bdc_available_counts_as_evidence():
    """When BDC returns AVAILABLE, available_count increments correctly."""
    bdc_data = {
        "demand_history": [{"CalYear": "2024", "CalMonth": "01", "PlannedQuantity": "100"}],
        "production_order_history": [],
        "material_master_changes": [],
        "summary": {"demand_months_available": 1, "historical_orders_count": 0, "recent_mrp_changes": 0},
    }
    with patch("evidence.collector.get_planned_orders",                  AsyncMock(return_value=_missing("S4HANA_PLANNED_ORDER"))), \
         patch("evidence.collector.get_material_planning_data",          AsyncMock(return_value=_missing("S4HANA_MATERIAL_PLANNING"))), \
         patch("evidence.collector.get_planned_independent_requirements", AsyncMock(return_value=_missing("S4HANA_PIR"))), \
         patch("evidence.collector.get_ppds_stock_level",                AsyncMock(return_value=_missing("S4HANA_PPDS_STOCK"))), \
         patch("evidence.collector.get_ppds_flexible_constraints",       AsyncMock(return_value=_missing("S4HANA_PPDS_CONSTRAINTS"))), \
         patch("evidence.collector.get_atp_check_result",                AsyncMock(return_value=_missing("S4HANA_ATP"))), \
         patch("evidence.collector.get_application_logs",                AsyncMock(return_value=_missing("S4HANA_APPLICATION_LOGS"))), \
         patch("evidence.collector.get_bgrfc_queue_status",              AsyncMock(return_value=_missing("S4HANA_BGRFC_QUEUE"))), \
         patch("evidence.collector.get_ppds_config_and_mrp_issues",      AsyncMock(return_value=_missing("S4HANA_PPDS_CONFIG"))), \
         patch("evidence.collector.get_ibp_supply_data",                 AsyncMock(return_value=_missing("IBP_SUPPLY"))), \
         patch("evidence.collector.get_cpi_message_status",              AsyncMock(return_value=_missing("SAP_CPI"))), \
         patch("evidence.collector.get_pipo_message_status",             AsyncMock(return_value=_missing("SAP_PIPO"))), \
         patch("evidence.collector.get_cloud_alm_health_events",         AsyncMock(return_value=_missing("CLOUD_ALM"))), \
         patch("evidence.collector.get_bdc_supply_chain_analytics",      AsyncMock(return_value={"status": "AVAILABLE", "data": bdc_data})), \
         patch("evidence.collector.get_ibp_job_status",                  AsyncMock(return_value=_missing("IBP_JOB_MONITOR"))):
        from evidence.collector import collect_evidence
        ctx = _make_ctx()
        payload = await collect_evidence(ctx)

    bdc_node = next(n for n in payload.nodes if n.system_name == "SAP_BDC")
    assert bdc_node.status == "AVAILABLE"
    assert bdc_node.raw_payload == bdc_data
    assert payload.available_count == 1


@pytest.mark.asyncio
async def test_bdc_missing_does_not_break_other_systems():
    """BDC returning MISSING_DATA must not affect other system node counts."""
    patches = _all_missing_patches()
    for p in patches:
        p.start()
    try:
        from evidence.collector import collect_evidence
        ctx = _make_ctx()
        payload = await collect_evidence(ctx)
    finally:
        for p in patches:
            p.stop()

    # 15 nodes total; BDC is MISSING_DATA
    assert len(payload.nodes) == 15
    bdc_node = next(n for n in payload.nodes if n.system_name == "SAP_BDC")
    assert bdc_node.status == "MISSING_DATA"
    assert payload.unavailable_count == 15


# ──────────────────────────────────────────────────────────────────────────────
# IBP Job Monitor tests (system 15)
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ibp_job_monitor_available_counts_as_evidence():
    """When IBP Monitor returns AVAILABLE, available_count increments correctly."""
    job_data = {
        "total_tasks": 2,
        "failed_count": 1,
        "completed_count": 1,
        "running_count": 0,
        "tasks": [
            {"TaskId": "T001", "TaskStatus": "FAILED", "ErrorMessage": "Master data error"},
            {"TaskId": "T002", "TaskStatus": "COMPLETED", "ErrorMessage": ""},
        ],
        "interpretation": "1 IBP planning job(s) FAILED between 2024-01-01 and 2024-12-31.",
    }
    with patch("evidence.collector.get_planned_orders",                  AsyncMock(return_value=_missing("S4HANA_PLANNED_ORDER"))), \
         patch("evidence.collector.get_material_planning_data",          AsyncMock(return_value=_missing("S4HANA_MATERIAL_PLANNING"))), \
         patch("evidence.collector.get_planned_independent_requirements", AsyncMock(return_value=_missing("S4HANA_PIR"))), \
         patch("evidence.collector.get_ppds_stock_level",                AsyncMock(return_value=_missing("S4HANA_PPDS_STOCK"))), \
         patch("evidence.collector.get_ppds_flexible_constraints",       AsyncMock(return_value=_missing("S4HANA_PPDS_CONSTRAINTS"))), \
         patch("evidence.collector.get_atp_check_result",                AsyncMock(return_value=_missing("S4HANA_ATP"))), \
         patch("evidence.collector.get_application_logs",                AsyncMock(return_value=_missing("S4HANA_APPLICATION_LOGS"))), \
         patch("evidence.collector.get_bgrfc_queue_status",              AsyncMock(return_value=_missing("S4HANA_BGRFC_QUEUE"))), \
         patch("evidence.collector.get_ppds_config_and_mrp_issues",      AsyncMock(return_value=_missing("S4HANA_PPDS_CONFIG"))), \
         patch("evidence.collector.get_ibp_supply_data",                 AsyncMock(return_value=_missing("IBP_SUPPLY"))), \
         patch("evidence.collector.get_cpi_message_status",              AsyncMock(return_value=_missing("SAP_CPI"))), \
         patch("evidence.collector.get_pipo_message_status",             AsyncMock(return_value=_missing("SAP_PIPO"))), \
         patch("evidence.collector.get_cloud_alm_health_events",         AsyncMock(return_value=_missing("CLOUD_ALM"))), \
         patch("evidence.collector.get_bdc_supply_chain_analytics",      AsyncMock(return_value=_missing("SAP_BDC"))), \
         patch("evidence.collector.get_ibp_job_status",                  AsyncMock(return_value={"status": "AVAILABLE", "system": "IBP_SUPPLY", "data": job_data})):
        from evidence.collector import collect_evidence
        ctx = _make_ctx()
        payload = await collect_evidence(ctx)

    ibp_job_node = next(n for n in payload.nodes if n.system_name == "IBP_JOB_MONITOR")
    assert ibp_job_node.status == "AVAILABLE"
    assert ibp_job_node.raw_payload == job_data
    assert payload.available_count == 1


@pytest.mark.asyncio
async def test_ibp_job_monitor_missing_does_not_break_pipeline():
    """IBP Monitor MISSING_DATA must not affect counts for other systems."""
    patches = _all_missing_patches()
    for p in patches:
        p.start()
    try:
        from evidence.collector import collect_evidence
        ctx = _make_ctx()
        payload = await collect_evidence(ctx)
    finally:
        for p in patches:
            p.stop()

    ibp_job_node = next(n for n in payload.nodes if n.system_name == "IBP_JOB_MONITOR")
    assert ibp_job_node.status == "MISSING_DATA"
    assert len(payload.nodes) == 15
