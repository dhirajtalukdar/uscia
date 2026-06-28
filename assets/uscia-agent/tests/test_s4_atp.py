"""
Unit tests for S/4HANA ATP / Product Allocation tool wrapper.

QL8 reality:
  - API: ATP_PRODALLOCOVERVIEW / C_ProdAllocOvwPeriods
  - No material/plant filter supported on this entity — returns global allocation data
  - Error path: only fires when the service itself is unreachable (not on per-material miss)
"""
import pytest
from helpers import make_fake


@pytest.mark.asyncio
async def test_get_atp_success():
    """Successful response returns AVAILABLE with S4HANA_ATP system tag."""
    fake = make_fake({"C_ProdAllocOvwPeriods": {"results": [{"ProductAllocationObject": "AE"}]}})
    from tools.s4_atp import get_atp_check_result
    result = await get_atp_check_result("MAT-001", "1000", s4=fake)
    assert result["status"] == "AVAILABLE"
    assert result["system"] == "S4HANA_ATP"


@pytest.mark.asyncio
async def test_get_atp_missing_data_on_service_error():
    """
    MISSING_DATA is returned only when the service itself errors (HTTP 503/500).
    QL8: C_ProdAllocOvwPeriods has no material filter — a 404 on the entity
    set means the service is down, not that the material is missing.
    """
    fake = make_fake()
    fake.responses["C_ProdAllocOvwPeriods"] = {"error": True, "status_code": 503, "message": "Service unavailable"}
    from tools.s4_atp import get_atp_check_result
    result = await get_atp_check_result("MAT-001", "1000", s4=fake)
    assert result["status"] == "MISSING_DATA"
    assert "manual_investigation" in result
    assert "CO09" in result["manual_investigation"]


@pytest.mark.asyncio
async def test_get_atp_no_filter_params():
    """
    QL8 reality: C_ProdAllocOvwPeriods does not support material/plant filter.
    The call uses $select and $top only — no $filter param is sent.
    """
    fake = make_fake({"C_ProdAllocOvwPeriods": {"results": []}})
    from tools.s4_atp import get_atp_check_result
    await get_atp_check_result("WIDGET", "P001", s4=fake)
    assert len(fake.calls) == 1
    # No $filter — this entity has no material/plant filter on QL8
    assert "$filter" not in fake.calls[0].params


@pytest.mark.asyncio
async def test_get_atp_uses_top_param():
    """Request must include $top to cap results."""
    fake = make_fake({"C_ProdAllocOvwPeriods": {"results": []}})
    from tools.s4_atp import get_atp_check_result
    await get_atp_check_result("MAT-001", "1000", s4=fake)
    assert fake.calls[0].params.get("$top") is not None
