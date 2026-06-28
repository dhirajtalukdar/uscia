"""Unit tests for S4 Application Logs stub."""
import pytest


@pytest.mark.asyncio
async def test_get_application_logs_always_missing_data():
    from tools.s4_app_logs import get_application_logs
    result = await get_application_logs("2024-01-01", "2024-12-31", "M1", "1000")
    assert result["status"] == "MISSING_DATA"
    assert result["system"] == "S4HANA_APPLICATION_LOGS"
    assert "SLG1" in result["guidance"]


@pytest.mark.asyncio
async def test_get_application_logs_no_args():
    from tools.s4_app_logs import get_application_logs
    result = await get_application_logs()
    assert result["status"] == "MISSING_DATA"
    assert "SLG1" in result["guidance"]
