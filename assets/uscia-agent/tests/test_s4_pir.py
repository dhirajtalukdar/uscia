"""Unit tests for S/4HANA PIR tool wrapper (direct-API version)."""
import pytest
from helpers import make_fake


@pytest.mark.asyncio
async def test_get_pir_success():
    fake = make_fake({"A_PlndIndepRqmt": {"results": [{"PlannedIndepRqmtNumber": "42"}]}})
    from tools.s4_pir import get_planned_independent_requirements
    result = await get_planned_independent_requirements(
        "MAT-001", "1000", "000", "2024-01-01", "2024-12-31", s4=fake
    )
    assert result["status"] == "AVAILABLE"
    assert result["system"] == "S4HANA_PIR"
    assert fake.calls[0].params["$top"] == 100


@pytest.mark.asyncio
async def test_get_pir_missing_data_on_error():
    fake = make_fake()
    fake.responses["A_PlndIndepRqmt"] = {"error": True, "status_code": 500, "message": "error"}
    from tools.s4_pir import get_planned_independent_requirements
    result = await get_planned_independent_requirements(
        "MAT-001", "1000", "000", "2024-01-01", "2024-12-31", s4=fake
    )
    assert result["status"] == "MISSING_DATA"
    assert "MD61" in result["guidance"]


@pytest.mark.asyncio
async def test_get_pir_filter_contains_version():
    fake = make_fake({"A_PlndIndepRqmt": {"results": []}})
    from tools.s4_pir import get_planned_independent_requirements
    await get_planned_independent_requirements("M", "P", "001", "2024-01-01", "2024-12-31", s4=fake)
    assert "001" in fake.calls[0].params["$filter"]
