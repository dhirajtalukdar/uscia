"""Unit tests for S4 Application Logs tool — on API error returns structured MISSING_DATA."""
import pytest


@pytest.mark.asyncio
async def test_get_application_logs_always_missing_data():
    from tools.s4_app_logs import get_application_logs
    result = await get_application_logs("2024-01-01", "2024-12-31", "M1", "1000")
    assert result["status"] == "MISSING_DATA"
    assert result["system"] == "S4HANA_APPLICATION_LOGS"
    # New structured keys replace flat "guidance"
    assert "reason" in result
    assert "manual_investigation" in result
    assert "SLG1" in result["manual_investigation"]


@pytest.mark.asyncio
async def test_get_application_logs_no_args():
    from tools.s4_app_logs import get_application_logs
    result = await get_application_logs()
    assert result["status"] == "MISSING_DATA"
    assert "manual_investigation" in result
    assert "SLG1" in result["manual_investigation"]
