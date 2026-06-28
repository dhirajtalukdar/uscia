"""
Unit tests for S/4HANA PP/DS Flexible Constraints tool wrapper.

QL8 reality:
  - API: UI_SCM_FLEX_CONSTR_V2 / Constraint
  - No material/plant filter on this entity — returns top constraints for the planning landscape
  - OP_APIFLEXIBLECONSTRAINTS_0001 is NOT registered on QL8 — replaced by UI_SCM_FLEX_CONSTR_V2
"""
import pytest
from helpers import make_fake


@pytest.mark.asyncio
async def test_get_ppds_constraints_success():
    """Successful response returns AVAILABLE with correct system tag."""
    fake = make_fake({"Constraint": {"results": [{"AdvncdPlngFlxCnsKey": "C001"}]}})
    from tools.s4_ppds_constraints import get_ppds_flexible_constraints
    result = await get_ppds_flexible_constraints("MAT-001", "1000", s4=fake)
    assert result["status"] == "AVAILABLE"
    assert result["system"] == "S4HANA_PPDS_CONSTRAINTS"


@pytest.mark.asyncio
async def test_get_ppds_constraints_missing_data_on_service_error():
    """
    MISSING_DATA returned when service itself errors.
    QL8: Constraint entity has no material filter — a service error triggers MISSING_DATA.
    """
    fake = make_fake()
    fake.responses["Constraint"] = {"error": True, "status_code": 503, "message": "down"}
    from tools.s4_ppds_constraints import get_ppds_flexible_constraints
    result = await get_ppds_flexible_constraints("MAT-001", "1000", s4=fake)
    assert result["status"] == "MISSING_DATA"
    assert "manual_investigation" in result
    assert "CDPS0" in result["manual_investigation"]


@pytest.mark.asyncio
async def test_get_ppds_constraints_no_material_filter():
    """
    QL8 reality: Constraint entity has no material/plant filter fields.
    The call uses $select and $top only — no $filter param is sent.
    """
    fake = make_fake({"Constraint": {"results": []}})
    from tools.s4_ppds_constraints import get_ppds_flexible_constraints
    await get_ppds_flexible_constraints("MAT-001", "1000", s4=fake)
    assert len(fake.calls) == 1
    assert "$filter" not in fake.calls[0].params


@pytest.mark.asyncio
async def test_get_ppds_constraints_uses_select_and_top():
    """Request must include $select and $top."""
    fake = make_fake({"Constraint": {"results": []}})
    from tools.s4_ppds_constraints import get_ppds_flexible_constraints
    await get_ppds_flexible_constraints("MAT-001", "1000", s4=fake)
    assert "$select" in fake.calls[0].params
    assert fake.calls[0].params.get("$top") is not None
