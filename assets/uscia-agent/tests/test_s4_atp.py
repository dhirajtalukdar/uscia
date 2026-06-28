"""Unit tests for S/4HANA ATP Check tool wrapper (direct-API version)."""
import pytest
from helpers import make_fake


@pytest.mark.asyncio
async def test_get_atp_success():
    fake = make_fake({"A_AvailabilityCheckingResultItem": {"results": [{"CheckingRuleID": "AE"}]}})
    from tools.s4_atp import get_atp_check_result
    result = await get_atp_check_result("MAT-001", "1000", s4=fake)
    assert result["status"] == "AVAILABLE"
    assert result["system"] == "S4HANA_ATP"


@pytest.mark.asyncio
async def test_get_atp_missing_data():
    fake = make_fake()
    fake.responses["A_AvailabilityCheckingResultItem"] = {"error": True, "status_code": 404, "message": "Not found"}
    from tools.s4_atp import get_atp_check_result
    result = await get_atp_check_result("MAT-001", "1000", s4=fake)
    assert result["status"] == "MISSING_DATA"
    assert "CO09" in result["guidance"]


@pytest.mark.asyncio
async def test_get_atp_filter_contains_material():
    fake = make_fake({"A_AvailabilityCheckingResultItem": {"results": []}})
    from tools.s4_atp import get_atp_check_result
    await get_atp_check_result("WIDGET", "P001", s4=fake)
    assert "WIDGET" in fake.calls[0].params["$filter"]
    assert "P001" in fake.calls[0].params["$filter"]
