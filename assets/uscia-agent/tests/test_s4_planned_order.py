"""Unit tests for S/4HANA Planned Order tool wrapper (direct-API version)."""
import pytest
from helpers import make_fake


@pytest.mark.asyncio
async def test_get_planned_orders_success():
    fake = make_fake({"A_PlannedOrder": {"results": [{"PlannedOrder": "1000001"}]}})
    from tools.s4_planned_order import get_planned_orders
    result = await get_planned_orders("MAT-001", "1000", "2024-01-01", "2024-12-31", s4=fake)

    assert result["status"] == "AVAILABLE"
    assert result["system"] == "S4HANA_PLANNED_ORDER"
    assert "data" in result
    assert len(fake.calls) == 1
    assert "MAT-001" in fake.calls[0].params["$filter"]
    assert fake.calls[0].params["$top"] == 100


@pytest.mark.asyncio
async def test_get_planned_orders_missing_data_on_error():
    fake = make_fake()
    # Simulate HTTP error response
    fake.responses["A_PlannedOrder"] = {"error": True, "status_code": 503, "message": "Backend down"}
    from tools.s4_planned_order import get_planned_orders
    result = await get_planned_orders("MAT-001", "1000", "2024-01-01", "2024-12-31", s4=fake)

    assert result["status"] == "MISSING_DATA"
    assert result["system"] == "S4HANA_PLANNED_ORDER"
    assert "manual_investigation" in result
    assert "MD04" in result["manual_investigation"]


@pytest.mark.asyncio
async def test_get_planned_orders_empty_results():
    fake = make_fake({"A_PlannedOrder": {"results": []}})
    from tools.s4_planned_order import get_planned_orders
    result = await get_planned_orders("MAT-001", "1000", "2024-01-01", "2024-12-31", s4=fake)

    assert result["status"] == "AVAILABLE"
    assert result["data"]["results"] == []


@pytest.mark.asyncio
async def test_get_planned_orders_filter_contains_plant():
    fake = make_fake({"A_PlannedOrder": {"results": []}})
    from tools.s4_planned_order import get_planned_orders
    await get_planned_orders("M-WIDGET", "P001", "2024-06-01", "2024-06-30", s4=fake)

    assert "P001" in fake.calls[0].params["$filter"]
    assert "M-WIDGET" in fake.calls[0].params["$filter"]
