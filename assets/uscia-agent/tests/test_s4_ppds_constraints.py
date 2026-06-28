"""Unit tests for S/4HANA PP/DS Flexible Constraints tool wrapper (direct-API version)."""
import pytest
from helpers import make_fake


@pytest.mark.asyncio
async def test_get_ppds_constraints_success():
    fake = make_fake({"A_FlexibleConstraint": {"results": [{"ConstraintID": "C001"}]}})
    from tools.s4_ppds_constraints import get_ppds_flexible_constraints
    result = await get_ppds_flexible_constraints("MAT-001", "1000", s4=fake)
    assert result["status"] == "AVAILABLE"
    assert result["system"] == "S4HANA_PPDS_CONSTRAINTS"


@pytest.mark.asyncio
async def test_get_ppds_constraints_missing_data():
    fake = make_fake()
    fake.responses["A_FlexibleConstraint"] = {"error": True, "status_code": 503, "message": "down"}
    from tools.s4_ppds_constraints import get_ppds_flexible_constraints
    result = await get_ppds_flexible_constraints("MAT-001", "1000", s4=fake)
    assert result["status"] == "MISSING_DATA"
    assert "CDPS0" in result["guidance"]
