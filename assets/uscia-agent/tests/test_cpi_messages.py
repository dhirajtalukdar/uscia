"""Unit tests for the CPI Message Processing Logs tool.

Covers:
- MISSING_DATA structured response when CPI not configured (graceful degradation)
- AVAILABLE response with failed messages
- AVAILABLE response with no failed messages
- IBD_TESTING fast-exit path
- Error path (HTTP error from CPIClient)
"""
import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _fake_cpi(response: dict) -> MagicMock:
    """Return a mock CPIClient whose .get() returns `response`."""
    cpi = MagicMock()
    cpi.get = AsyncMock(return_value=response)
    return cpi


# ──────────────────────────────────────────────────────────────────────────────
# Graceful degradation — MISSING_DATA when no CPI configured
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cpi_missing_data_when_not_configured():
    """No IBD_TESTING, no cpi arg — CPIClient raises EnvironmentError → MISSING_DATA."""
    from tools.cpi_messages import get_cpi_message_status
    result = await get_cpi_message_status("2024-01-01", "2024-12-31", "EXTID001", "1000")
    assert result["status"] == "MISSING_DATA"
    assert result["system"] == "SAP_CPI"
    assert "reason" in result
    assert "Phase 2" in result["reason"]
    assert "CPI_BASE_URL" in result["reason"]
    assert "what_was_expected" in result
    assert "IBP_RTI_TO_S4HANA" in result["what_was_expected"]
    assert "manual_investigation" in result
    assert "SXMB_MONI" in result["manual_investigation"]


@pytest.mark.asyncio
async def test_cpi_ibd_testing_fast_exit():
    """IBD_TESTING=1 with no cpi arg triggers fast-exit MISSING_DATA."""
    with patch.dict(os.environ, {"IBD_TESTING": "1"}):
        from tools.cpi_messages import get_cpi_message_status
        result = await get_cpi_message_status("2024-01-01", "2024-12-31")
    assert result["status"] == "MISSING_DATA"
    assert result["system"] == "SAP_CPI"
    assert "reason" in result
    assert "IBD_TESTING" in result["reason"]


# ──────────────────────────────────────────────────────────────────────────────
# AVAILABLE path — failed messages found
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cpi_returns_available_with_failed_messages():
    """When CPI returns failed messages, status=AVAILABLE with structured data."""
    mock_response = {
        "results": [
            {
                "MessageGuid": "GUID-001",
                "CorrelationId": "CORR-001",
                "Status": "FAILED",
                "IntegrationFlowName": "IBP_RTI_TO_S4HANA",
                "Sender": "IBP",
                "Receiver": "S4HANA",
                "LogStart": "2024-06-01T08:00:00",
                "LogEnd": "2024-06-01T08:00:05",
                "ApplicationMessageId": "MSG-001",
                "ApplicationMessageType": "PlannedOrder",
            },
            {
                "MessageGuid": "GUID-002",
                "CorrelationId": "CORR-002",
                "Status": "FAILED",
                "IntegrationFlowName": "IBP_RTI_TO_S4HANA",
                "Sender": "IBP",
                "Receiver": "S4HANA",
                "LogStart": "2024-06-02T09:00:00",
                "LogEnd": "2024-06-02T09:00:03",
                "ApplicationMessageId": "MSG-002",
                "ApplicationMessageType": "PlannedOrder",
            },
        ]
    }
    cpi = _fake_cpi(mock_response)
    from tools.cpi_messages import get_cpi_message_status
    result = await get_cpi_message_status("2024-01-01", "2024-12-31", "EXTID001", "1000", cpi=cpi)

    assert result["status"] == "AVAILABLE"
    assert result["system"] == "SAP_CPI"
    assert result["data"]["failed_count"] == 2
    assert len(result["data"]["messages"]) == 2
    assert result["data"]["messages"][0]["MessageGuid"] == "GUID-001"
    assert "FAILED" in result["data"]["interpretation"]
    assert "IBP_RTI_TO_S4HANA" in result["data"]["interpretation"]
    # externid correlation hint should appear when externid provided
    assert "EXTID001" in result["data"]["interpretation"]


@pytest.mark.asyncio
async def test_cpi_returns_available_no_failures():
    """When CPI returns empty results, status=AVAILABLE with failed_count=0."""
    mock_response = {"results": []}
    cpi = _fake_cpi(mock_response)
    from tools.cpi_messages import get_cpi_message_status
    result = await get_cpi_message_status("2024-01-01", "2024-12-31", cpi=cpi)

    assert result["status"] == "AVAILABLE"
    assert result["system"] == "SAP_CPI"
    assert result["data"]["failed_count"] == 0
    assert result["data"]["messages"] == []
    assert "No FAILED messages" in result["data"]["interpretation"]
    assert "not the root cause" in result["data"]["interpretation"]


@pytest.mark.asyncio
async def test_cpi_handles_list_response():
    """CPIClient may return a list directly (no 'results' wrapper)."""
    mock_response = [
        {
            "MessageGuid": "GUID-LIST",
            "CorrelationId": "CORR-LIST",
            "Status": "FAILED",
            "IntegrationFlowName": "IBP_RTI_TO_S4HANA",
            "Sender": "IBP",
            "Receiver": "S4HANA",
            "LogStart": "2024-03-01T10:00:00",
            "LogEnd": "2024-03-01T10:00:02",
            "ApplicationMessageId": "",
            "ApplicationMessageType": "",
        }
    ]
    cpi = _fake_cpi(mock_response)
    from tools.cpi_messages import get_cpi_message_status
    result = await get_cpi_message_status("2024-01-01", "2024-12-31", cpi=cpi)

    assert result["status"] == "AVAILABLE"
    assert result["data"]["failed_count"] == 1


# ──────────────────────────────────────────────────────────────────────────────
# Error path — HTTP error or exception
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cpi_http_error_returns_missing_data():
    """When CPIClient returns an error dict, falls back to MISSING_DATA."""
    mock_response = {"error": True, "status_code": 401, "message": "Unauthorized"}
    cpi = _fake_cpi(mock_response)
    from tools.cpi_messages import get_cpi_message_status
    result = await get_cpi_message_status("2024-01-01", "2024-12-31", cpi=cpi)

    assert result["status"] == "MISSING_DATA"
    assert result["system"] == "SAP_CPI"
    assert "reason" in result
    assert "401" in result["reason"] or "Unauthorized" in result["reason"]
    assert "manual_investigation" in result


@pytest.mark.asyncio
async def test_cpi_exception_returns_missing_data():
    """When CPIClient.get raises an exception, falls back to MISSING_DATA."""
    cpi = MagicMock()
    cpi.get = AsyncMock(side_effect=RuntimeError("connection refused"))
    from tools.cpi_messages import get_cpi_message_status
    result = await get_cpi_message_status("2024-01-01", "2024-12-31", cpi=cpi)

    assert result["status"] == "MISSING_DATA"
    assert result["system"] == "SAP_CPI"
    assert "connection refused" in result["reason"]
    assert "what_was_expected" in result
    assert "manual_investigation" in result


# ──────────────────────────────────────────────────────────────────────────────
# Structured MISSING_DATA keys — backward compat with test_cpi_pipo_cloud_alm.py
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cpi_missing_data_structured_keys_present():
    """All three structured MISSING_DATA keys must always be present."""
    from tools.cpi_messages import get_cpi_message_status
    result = await get_cpi_message_status("2024-01-01", "2024-12-31")
    assert result["status"] == "MISSING_DATA"
    assert "reason" in result
    assert "what_was_expected" in result
    assert "manual_investigation" in result
    # SXMB_MONI must appear for manual fallback
    assert "SXMB_MONI" in result["manual_investigation"]
