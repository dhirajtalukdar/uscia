"""Unit tests for IBP Supply Data tool wrapper (direct-API version)."""
import os
import pytest
from helpers import make_fake


@pytest.mark.asyncio
async def test_get_ibp_supply_data_success(monkeypatch):
    monkeypatch.setenv("IBP_BASE_URL", "https://test.ibp.cloud.sap")
    fake = make_fake({"SupplyOrders": {"results": [{"SupplyOrderID": "SO-001"}]}})
    from tools.ibp_supply import get_ibp_supply_data
    result = await get_ibp_supply_data("MAT-001", "LOC1", "000", "2024-01-01", "2024-12-31", ibp=fake)
    assert result["status"] == "AVAILABLE"
    assert result["system"] == "IBP_SUPPLY"


@pytest.mark.asyncio
async def test_get_ibp_supply_data_missing_when_not_configured(monkeypatch):
    monkeypatch.delenv("IBP_BASE_URL", raising=False)
    from tools.ibp_supply import get_ibp_supply_data
    result = await get_ibp_supply_data("MAT-001", "LOC1", "000", "2024-01-01", "2024-12-31")
    assert result["status"] == "MISSING_DATA"
    assert result["system"] == "IBP_SUPPLY"


@pytest.mark.asyncio
async def test_get_ibp_supply_data_missing_on_http_error(monkeypatch):
    monkeypatch.setenv("IBP_BASE_URL", "https://test.ibp.cloud.sap")
    fake = make_fake()
    fake.responses["SupplyOrders"] = {"error": True, "status_code": 500, "message": "Server Error"}
    from tools.ibp_supply import get_ibp_supply_data
    result = await get_ibp_supply_data("MAT-001", "LOC1", "000", "2024-01-01", "2024-12-31", ibp=fake)
    assert result["status"] == "MISSING_DATA"


@pytest.mark.asyncio
async def test_get_ibp_supply_data_filter_contains_version(monkeypatch):
    monkeypatch.setenv("IBP_BASE_URL", "https://test.ibp.cloud.sap")
    fake = make_fake({"SupplyOrders": {"results": []}})
    from tools.ibp_supply import get_ibp_supply_data
    await get_ibp_supply_data("M", "L", "VER01", "2024-01-01", "2024-12-31", ibp=fake)
    assert "VER01" in fake.calls[0].params["$filter"]
