"""
Unit tests for S/4HANA Material Planning tool wrapper.

QL8 reality:
  - API: API_MRP_MATERIALS_SRV_01 / A_MRPMaterial
  - Filter: Material + MRPPlant
  - FakeClient resolves by path substring — must use "A_MRPMaterial" as response key
"""
import pytest
from helpers import make_fake


@pytest.mark.asyncio
async def test_get_material_planning_success():
    """Successful response returns AVAILABLE with correct system tag."""
    fake = make_fake({"A_MRPMaterial": {"results": [{"Material": "MAT-001", "MRPType": "PD"}]}})
    from tools.s4_material_planning import get_material_planning_data
    result = await get_material_planning_data("MAT-001", "1000", s4=fake)
    assert result["status"] == "AVAILABLE"
    assert result["system"] == "S4HANA_MATERIAL_PLANNING"
    assert "data" in result
    assert fake.calls[0].params["$top"] == 1


@pytest.mark.asyncio
async def test_get_material_planning_missing_data_on_error():
    """
    MISSING_DATA returned when service errors.
    FakeClient must match the actual entity path used in the tool: A_MRPMaterial.
    """
    fake = make_fake()
    # Must match the path used in the tool: f"{MRP_MATERIALS_ROOT}/A_MRPMaterial"
    fake.responses["A_MRPMaterial"] = {"error": True, "status_code": 404, "message": "Not found"}

    from tools.s4_material_planning import get_material_planning_data

    # Patch S4Client.get to return the error response directly
    from unittest.mock import AsyncMock, patch
    with patch.object(fake, "get", new=AsyncMock(return_value={"error": True, "status_code": 404, "message": "Not found"})):
        result = await get_material_planning_data("MAT-001", "1000", s4=fake)

    assert result["status"] == "MISSING_DATA"
    assert "manual_investigation" in result
    assert "MM03" in result["manual_investigation"]


@pytest.mark.asyncio
async def test_get_material_planning_filter_correct():
    """Filter must contain both material and plant using correct field names."""
    fake = make_fake({"A_MRPMaterial": {"results": []}})
    from tools.s4_material_planning import get_material_planning_data
    await get_material_planning_data("WIDGET-X", "PLNT", s4=fake)
    assert "WIDGET-X" in fake.calls[0].params["$filter"]
    assert "PLNT" in fake.calls[0].params["$filter"]


@pytest.mark.asyncio
async def test_get_material_planning_select_contains_mrp_type():
    """$select must include MRPType — core diagnostic field."""
    fake = make_fake({"A_MRPMaterial": {"results": []}})
    from tools.s4_material_planning import get_material_planning_data
    await get_material_planning_data("MAT-001", "1000", s4=fake)
    assert "MRPType" in fake.calls[0].params["$select"]
