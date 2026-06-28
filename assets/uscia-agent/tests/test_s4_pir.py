"""
Unit tests for S/4HANA PIR tool wrapper.

QL8 reality:
  - API: API_PLND_INDEP_RQMT_SRV / PlannedIndepRqmt
  - Filter fields: Product + Plant (NOT Material + MRPPlant, NOT planning version)
  - Planning version is NOT included in the OData filter on QL8 — it is passed
    for guidance context only, not as a query parameter
"""
import pytest
from unittest.mock import AsyncMock, patch
from helpers import make_fake


@pytest.mark.asyncio
async def test_get_pir_success():
    """Successful response returns AVAILABLE with correct system tag and $top=100."""
    fake = make_fake({"PlannedIndepRqmt": {"results": [{"PlannedIndepRqmtNumber": "42"}]}})
    from tools.s4_pir import get_planned_independent_requirements
    result = await get_planned_independent_requirements(
        "MAT-001", "1000", "000", "2024-01-01", "2024-12-31", s4=fake
    )
    assert result["status"] == "AVAILABLE"
    assert result["system"] == "S4HANA_PIR"
    assert fake.calls[0].params["$top"] == 100


@pytest.mark.asyncio
async def test_get_pir_missing_data_on_error():
    """MISSING_DATA returned when service errors. Uses AsyncMock to force error path."""
    fake = make_fake()
    from tools.s4_pir import get_planned_independent_requirements
    with patch.object(fake, "get", new=AsyncMock(return_value={"error": True, "status_code": 500, "message": "error"})):
        result = await get_planned_independent_requirements(
            "MAT-001", "1000", "000", "2024-01-01", "2024-12-31", s4=fake
        )
    assert result["status"] == "MISSING_DATA"
    assert "manual_investigation" in result
    assert "MD61" in result["manual_investigation"]


@pytest.mark.asyncio
async def test_get_pir_filter_uses_product_and_plant():
    """
    QL8 reality: PIR filter uses Product and Plant — NOT planning version.
    Planning version is NOT a supported filter field on API_PLND_INDEP_RQMT_SRV.
    """
    fake = make_fake({"PlannedIndepRqmt": {"results": []}})
    from tools.s4_pir import get_planned_independent_requirements
    await get_planned_independent_requirements("MAT-X", "2000", "001", "2024-01-01", "2024-12-31", s4=fake)
    filter_val = fake.calls[0].params["$filter"]
    assert "MAT-X" in filter_val
    assert "2000" in filter_val
    # Planning version is NOT in the filter on QL8
    assert "001" not in filter_val


@pytest.mark.asyncio
async def test_get_pir_select_contains_key_fields():
    """$select must include Product, Plant, and PlndIndepRqmtType."""
    fake = make_fake({"PlannedIndepRqmt": {"results": []}})
    from tools.s4_pir import get_planned_independent_requirements
    await get_planned_independent_requirements("MAT-001", "1000", "000", "2024-01-01", "2024-12-31", s4=fake)
    select = fake.calls[0].params["$select"]
    assert "Product" in select
    assert "Plant" in select
    assert "PlndIndepRqmtType" in select
