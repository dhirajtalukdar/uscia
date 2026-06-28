"""Unit tests for bgRFC Queue Status tool — on API error returns structured MISSING_DATA."""
import pytest


@pytest.mark.asyncio
async def test_get_bgrfc_always_missing_data():
    from tools.s4_bgrfc import get_bgrfc_queue_status
    result = await get_bgrfc_queue_status("2024-01-01", "2024-12-31", "1000", "EXT-001")
    assert result["status"] == "MISSING_DATA"
    assert result["system"] == "S4HANA_BGRFC_QUEUE"
    # New structured keys replace flat "guidance"
    assert "reason" in result
    assert "manual_investigation" in result
    assert "SM58" in result["manual_investigation"]
    assert "SMQ1" in result["manual_investigation"]


@pytest.mark.asyncio
async def test_get_bgrfc_includes_externid_in_guidance():
    from tools.s4_bgrfc import get_bgrfc_queue_status
    result = await get_bgrfc_queue_status(externid="EXT-XYZ")
    # externid must appear in what_was_expected or manual_investigation
    assert "EXT-XYZ" in result.get("what_was_expected", "") or "EXT-XYZ" in result.get("manual_investigation", "")
