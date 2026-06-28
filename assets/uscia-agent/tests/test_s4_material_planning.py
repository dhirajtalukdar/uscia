"""Unit tests for S/4HANA Material Planning tool wrapper (direct-API version)."""
import pytest
from helpers import make_fake


@pytest.mark.asyncio
async def test_get_material_planning_success():
    fake = make_fake({"A_MrpMaterial": {"results": [{"Material": "MAT-001", "MRPType": "PD"}]}})
    from tools.s4_material_planning import get_material_planning_data
    result = await get_material_planning_data("MAT-001", "1000", s4=fake)

    assert result["status"] == "AVAILABLE"
    assert result["system"] == "S4HANA_MATERIAL_PLANNING"
    assert "data" in result
    assert fake.calls[0].params["$top"] == 1


@pytest.mark.asyncio
async def test_get_material_planning_missing_data_on_error():
    fake = make_fake()
    fake.responses["A_MrpMaterial"] = {"error": True, "status_code": 404, "message": "Not found"}
    from tools.s4_material_planning import get_material_planning_data
    result = await get_material_planning_data("MAT-001", "1000", s4=fake)

    assert result["status"] == "MISSING_DATA"
    assert "MM03" in result["guidance"]


@pytest.mark.asyncio
async def test_get_material_planning_filter_correct():
    fake = make_fake({"A_MrpMaterial": {"results": []}})
    from tools.s4_material_planning import get_material_planning_data
    await get_material_planning_data("WIDGET-X", "PLNT", s4=fake)

    assert "WIDGET-X" in fake.calls[0].params["$filter"]
    assert "PLNT" in fake.calls[0].params["$filter"]
