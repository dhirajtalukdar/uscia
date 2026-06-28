"""
Unit tests for S/4HANA PP/DS Stock Level tool wrapper.

QL8 reality:
  - API: PPDS_MRP_COCKPIT_SRV / ResourceUtilizations
  - Filter: Plant only (no material filter on this entity)
  - OP_PPDSPRODTDSTLV_0001 is NOT registered on QL8 — replaced by PPDS_MRP_COCKPIT_SRV
"""
import pytest
from helpers import make_fake


@pytest.mark.asyncio
async def test_get_ppds_stock_success():
    """Successful response returns AVAILABLE with correct system tag."""
    fake = make_fake({"ResourceUtilizations": {"results": [{"Product": "MAT-001"}]}})
    from tools.s4_ppds_stock import get_ppds_stock_level
    result = await get_ppds_stock_level("MAT-001", "1000", "2024-01-01", "2024-12-31", s4=fake)
    assert result["status"] == "AVAILABLE"
    assert result["system"] == "S4HANA_PPDS_STOCK"


@pytest.mark.asyncio
async def test_get_ppds_stock_missing_data_on_service_error():
    """
    MISSING_DATA returned when service itself errors.
    QL8: filter is by Plant only — a service error triggers MISSING_DATA with RRP3 guidance.
    """
    fake = make_fake()
    fake.responses["ResourceUtilizations"] = {"error": True, "status_code": 503, "message": "down"}
    from tools.s4_ppds_stock import get_ppds_stock_level
    result = await get_ppds_stock_level("MAT-001", "1000", "2024-01-01", "2024-12-31", s4=fake)
    assert result["status"] == "MISSING_DATA"
    assert "manual_investigation" in result
    assert "RRP3" in result["manual_investigation"]


@pytest.mark.asyncio
async def test_get_ppds_stock_filter_uses_plant():
    """
    QL8 reality: ResourceUtilizations filters by Plant only (no material filter).
    """
    fake = make_fake({"ResourceUtilizations": {"results": []}})
    from tools.s4_ppds_stock import get_ppds_stock_level
    await get_ppds_stock_level("MAT-001", "1000", "2024-01-01", "2024-12-31", s4=fake)
    assert "1000" in fake.calls[0].params["$filter"]


@pytest.mark.asyncio
async def test_get_ppds_stock_uses_top_param():
    """Request must include $top to cap results."""
    fake = make_fake({"ResourceUtilizations": {"results": []}})
    from tools.s4_ppds_stock import get_ppds_stock_level
    await get_ppds_stock_level("MAT-001", "1000", "2024-01-01", "2024-12-31", s4=fake)
    assert fake.calls[0].params.get("$top") is not None
