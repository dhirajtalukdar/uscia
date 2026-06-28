"""Unit tests for bgRFC Queue Status stub."""
import pytest


@pytest.mark.asyncio
async def test_get_bgrfc_always_missing_data():
    from tools.s4_bgrfc import get_bgrfc_queue_status
    result = await get_bgrfc_queue_status("2024-01-01", "2024-12-31", "1000", "EXT-001")
    assert result["status"] == "MISSING_DATA"
    assert result["system"] == "S4HANA_BGRFC_QUEUE"
    assert "SM58" in result["guidance"]
    assert "SXMB_MONI" in result["guidance"]


@pytest.mark.asyncio
async def test_get_bgrfc_includes_externid_in_guidance():
    from tools.s4_bgrfc import get_bgrfc_queue_status
    result = await get_bgrfc_queue_status(externid="EXT-XYZ")
    assert "EXT-XYZ" in result["guidance"]
