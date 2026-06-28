"""Unit tests for CPI/PIPO/Cloud ALM stubs — all must return MISSING_DATA with structured guidance."""
import pytest


@pytest.mark.asyncio
async def test_cpi_always_missing_data():
    from tools.cpi_messages import get_cpi_message_status
    result = await get_cpi_message_status("2024-01-01", "2024-12-31", "1000", "SUPPLY_PLAN_OUT")
    assert result["status"] == "MISSING_DATA"
    assert result["system"] in ("CPI_RTI", "SAP_CPI")
    # New structured keys replace flat "guidance"
    assert "reason" in result
    assert "Phase 2" in result["reason"]
    assert "CPI_BASE_URL" in result["reason"]
    assert "what_was_expected" in result
    assert "IBP_RTI_TO_S4HANA" in result["what_was_expected"]
    assert "manual_investigation" in result
    assert "SXMB_MONI" in result["manual_investigation"]


@pytest.mark.asyncio
async def test_pipo_always_missing_data():
    from tools.pipo_messages import get_pipo_message_status
    result = await get_pipo_message_status("2024-01-01", "2024-12-31")
    assert result["status"] == "MISSING_DATA"
    assert result["system"] in ("PIPO", "SAP_PIPO")
    assert "reason" in result
    assert "Phase 2" in result["reason"]
    assert "manual_investigation" in result
    assert "SXMB_MONI" in result["manual_investigation"]


@pytest.mark.asyncio
async def test_cloud_alm_always_missing_data():
    from tools.cloud_alm import get_cloud_alm_health_events
    result = await get_cloud_alm_health_events("1000", "2024-01-01", "2024-12-31")
    assert result["status"] == "MISSING_DATA"
    assert result["system"] == "CLOUD_ALM"
    assert "reason" in result
    assert "Phase 2" in result["reason"]
    assert "manual_investigation" in result
    assert "Cloud ALM" in result["manual_investigation"]
