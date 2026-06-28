"""Unit tests for evidence collector — parallel gather, MISSING_DATA handling."""
import pytest
from unittest.mock import patch, AsyncMock
from evidence.models import InvestigationContext


def _make_ctx():
    return InvestigationContext(
        material="MAT-001", plant="1000", planning_version="000",
        date_from="2024-01-01", date_to="2024-12-31",
        incident_type="planned order missing in MD04", continuity_keys={},
    )


def _missing(system: str) -> dict:
    return {"status": "MISSING_DATA", "system": system, "guidance": f"Check {system} manually."}


def _available(system: str, data=None) -> dict:
    return {"status": "AVAILABLE", "system": system, "data": data or [{"key": "val"}]}


@pytest.mark.asyncio
async def test_collector_all_missing():
    """All 12 systems return MISSING_DATA — payload must have 12 nodes all MISSING_DATA."""
    tools_patch = {
        "tools.s4_planned_order.get_planned_orders": AsyncMock(return_value=_missing("S4HANA_PLANNED_ORDER")),
        "tools.s4_material_planning.get_material_planning_data": AsyncMock(return_value=_missing("S4HANA_MRP")),
        "tools.s4_pir.get_planned_independent_requirements": AsyncMock(return_value=_missing("S4HANA_PIR")),
        "tools.s4_ppds_stock.get_ppds_stock_level": AsyncMock(return_value=_missing("S4HANA_PPDS_STOCK")),
        "tools.s4_ppds_constraints.get_ppds_flexible_constraints": AsyncMock(return_value=_missing("S4HANA_PPDS_CONSTRAINTS")),
        "tools.s4_atp.get_atp_check_result": AsyncMock(return_value=_missing("S4HANA_ATP")),
        "tools.s4_app_logs.get_application_logs": AsyncMock(return_value=_missing("S4HANA_APPLICATION_LOGS")),
        "tools.s4_bgrfc.get_bgrfc_queue_status": AsyncMock(return_value=_missing("S4HANA_BGRFC_QUEUE")),
        "tools.ibp_supply.get_ibp_supply_data": AsyncMock(return_value=_missing("IBP_SUPPLY")),
        "tools.cpi_messages.get_cpi_message_status": AsyncMock(return_value=_missing("CPI_RTI")),
        "tools.pipo_messages.get_pipo_message_status": AsyncMock(return_value=_missing("PIPO")),
        "tools.cloud_alm.get_cloud_alm_health_events": AsyncMock(return_value=_missing("CLOUD_ALM")),
    }
    with patch.multiple("evidence.collector", **{k.split(".")[-1]: v for k, v in tools_patch.items()}):
        # patch the actual functions used in collector
        with patch("evidence.collector.get_planned_orders", AsyncMock(return_value=_missing("S4HANA_PLANNED_ORDER"))), \
             patch("evidence.collector.get_material_planning_data", AsyncMock(return_value=_missing("S4HANA_MRP"))), \
             patch("evidence.collector.get_planned_independent_requirements", AsyncMock(return_value=_missing("S4HANA_PIR"))), \
             patch("evidence.collector.get_ppds_stock_level", AsyncMock(return_value=_missing("S4HANA_PPDS_STOCK"))), \
             patch("evidence.collector.get_ppds_flexible_constraints", AsyncMock(return_value=_missing("S4HANA_PPDS_CONSTRAINTS"))), \
             patch("evidence.collector.get_atp_check_result", AsyncMock(return_value=_missing("S4HANA_ATP"))), \
             patch("evidence.collector.get_application_logs", AsyncMock(return_value=_missing("S4HANA_APPLICATION_LOGS"))), \
             patch("evidence.collector.get_bgrfc_queue_status", AsyncMock(return_value=_missing("S4HANA_BGRFC_QUEUE"))), \
             patch("evidence.collector.get_ibp_supply_data", AsyncMock(return_value=_missing("IBP_SUPPLY"))), \
             patch("evidence.collector.get_cpi_message_status", AsyncMock(return_value=_missing("CPI_RTI"))), \
             patch("evidence.collector.get_pipo_message_status", AsyncMock(return_value=_missing("PIPO"))), \
             patch("evidence.collector.get_cloud_alm_health_events", AsyncMock(return_value=_missing("CLOUD_ALM"))):
            from evidence.collector import collect_evidence
            ctx = _make_ctx()
            payload = await collect_evidence(ctx)

    assert len(payload.nodes) == 12
    missing_nodes = [n for n in payload.nodes if n.status == "MISSING_DATA"]
    assert len(missing_nodes) == 12
    assert payload.insufficient_coverage_warning is True


@pytest.mark.asyncio
async def test_collector_partial_available():
    """Some systems available — payload must have mix of statuses."""
    with patch("evidence.collector.get_planned_orders", AsyncMock(return_value=_available("S4HANA_PLANNED_ORDER"))), \
         patch("evidence.collector.get_material_planning_data", AsyncMock(return_value=_available("S4HANA_MRP"))), \
         patch("evidence.collector.get_planned_independent_requirements", AsyncMock(return_value=_available("S4HANA_PIR"))), \
         patch("evidence.collector.get_ppds_stock_level", AsyncMock(return_value=_missing("S4HANA_PPDS_STOCK"))), \
         patch("evidence.collector.get_ppds_flexible_constraints", AsyncMock(return_value=_missing("S4HANA_PPDS_CONSTRAINTS"))), \
         patch("evidence.collector.get_atp_check_result", AsyncMock(return_value=_missing("S4HANA_ATP"))), \
         patch("evidence.collector.get_application_logs", AsyncMock(return_value=_missing("S4HANA_APPLICATION_LOGS"))), \
         patch("evidence.collector.get_bgrfc_queue_status", AsyncMock(return_value=_missing("S4HANA_BGRFC_QUEUE"))), \
         patch("evidence.collector.get_ibp_supply_data", AsyncMock(return_value=_missing("IBP_SUPPLY"))), \
         patch("evidence.collector.get_cpi_message_status", AsyncMock(return_value=_missing("CPI_RTI"))), \
         patch("evidence.collector.get_pipo_message_status", AsyncMock(return_value=_missing("PIPO"))), \
         patch("evidence.collector.get_cloud_alm_health_events", AsyncMock(return_value=_missing("CLOUD_ALM"))):
        from evidence.collector import collect_evidence
        ctx = _make_ctx()
        payload = await collect_evidence(ctx)

    available_nodes = [n for n in payload.nodes if n.status == "AVAILABLE"]
    assert len(available_nodes) == 3
    assert payload.insufficient_coverage_warning is False
