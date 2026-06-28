"""Unit tests for S/4HANA PP/DS Stock Level tool wrapper (direct-API version)."""
import pytest
from helpers import make_fake


@pytest.mark.asyncio
async def test_get_ppds_stock_success():
    fake = make_fake({"A_PPDSProdTimeDependentStockLvl": {"results": [{"Product": "MAT-001"}]}})
    from tools.s4_ppds_stock import get_ppds_stock_level
    result = await get_ppds_stock_level("MAT-001", "1000", "2024-01-01", "2024-12-31", s4=fake)
    assert result["status"] == "AVAILABLE"
    assert result["system"] == "S4HANA_PPDS_STOCK"


@pytest.mark.asyncio
async def test_get_ppds_stock_missing_data():
    fake = make_fake()
    fake.responses["A_PPDSProdTimeDependentStockLvl"] = {"error": True, "status_code": 404, "message": "Not found"}
    from tools.s4_ppds_stock import get_ppds_stock_level
    result = await get_ppds_stock_level("MAT-001", "1000", "2024-01-01", "2024-12-31", s4=fake)
    assert result["status"] == "MISSING_DATA"
    assert "RRP3" in result["guidance"]
