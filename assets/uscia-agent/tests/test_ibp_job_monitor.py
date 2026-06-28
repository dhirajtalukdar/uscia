"""Unit tests for the IBP Monitor System Tasks tool.

Covers:
- MISSING_DATA structured response when IBP not configured (graceful degradation)
- AVAILABLE response with failed planning jobs
- AVAILABLE response with completed jobs (no failures)
- AVAILABLE response with no jobs at all (heuristic never ran)
- AVAILABLE response with running jobs
- IBD_TESTING fast-exit path
- HTTP error path
"""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _fake_ibp(response: dict) -> MagicMock:
    ibp = MagicMock()
    ibp.get = AsyncMock(return_value=response)
    return ibp


def _task(task_id: str, status: str, error: str = "") -> dict:
    return {
        "TaskId": task_id,
        "TaskType": "HEURISTIC",
        "TaskStatus": status,
        "PlanningVersion": "000",
        "StartTime": "2024-06-01T06:00:00",
        "EndTime": "2024-06-01T06:10:00" if status != "RUNNING" else "",
        "ErrorMessage": error,
        "CreatedByUser": "IBPUSER",
    }


# ──────────────────────────────────────────────────────────────────────────────
# Graceful degradation
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ibp_job_missing_when_not_configured():
    """No IBP credentials → IBPClient raises EnvironmentError → MISSING_DATA."""
    from tools.ibp_job_monitor import get_ibp_job_status
    result = await get_ibp_job_status("2024-01-01", "2024-12-31", "000")
    assert result["status"] == "MISSING_DATA"
    assert result["system"] == "IBP_SUPPLY"
    assert "reason" in result
    assert "Phase 2" in result["reason"]
    assert "what_was_expected" in result
    assert "manual_investigation" in result
    assert "System Task Monitor" in result["manual_investigation"]


@pytest.mark.asyncio
async def test_ibp_job_ibd_testing_fast_exit():
    """IBD_TESTING=1 with no ibp arg triggers fast-exit MISSING_DATA."""
    from unittest.mock import patch
    with patch.dict(os.environ, {"IBD_TESTING": "1"}):
        from tools.ibp_job_monitor import get_ibp_job_status
        result = await get_ibp_job_status("2024-01-01", "2024-12-31", "000")
    assert result["status"] == "MISSING_DATA"
    assert "IBD_TESTING" in result["reason"]


# ──────────────────────────────────────────────────────────────────────────────
# AVAILABLE — failed jobs
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ibp_job_failed_tasks():
    """When IBP returns failed tasks, interpretation must report failure."""
    mock_resp = {
        "results": [
            _task("T001", "FAILED", "Master data inconsistency"),
            _task("T002", "COMPLETED"),
        ]
    }
    ibp = _fake_ibp(mock_resp)
    from tools.ibp_job_monitor import get_ibp_job_status
    result = await get_ibp_job_status("2024-01-01", "2024-12-31", "000", ibp=ibp)

    assert result["status"] == "AVAILABLE"
    assert result["system"] == "IBP_SUPPLY"
    assert result["data"]["failed_count"] == 1
    assert result["data"]["completed_count"] == 1
    assert result["data"]["total_tasks"] == 2
    assert "FAILED" in result["data"]["interpretation"]
    assert "Master data inconsistency" in result["data"]["interpretation"]


@pytest.mark.asyncio
async def test_ibp_job_all_completed():
    """When all IBP jobs completed, interpretation indicates successful plan run."""
    mock_resp = {
        "results": [
            _task("T001", "COMPLETED"),
            _task("T002", "COMPLETED"),
        ]
    }
    ibp = _fake_ibp(mock_resp)
    from tools.ibp_job_monitor import get_ibp_job_status
    result = await get_ibp_job_status("2024-01-01", "2024-12-31", ibp=ibp)

    assert result["status"] == "AVAILABLE"
    assert result["data"]["completed_count"] == 2
    assert result["data"]["failed_count"] == 0
    assert "COMPLETED" in result["data"]["interpretation"] or "completed" in result["data"]["interpretation"].lower()
    # Hint: if S4 still has no planned orders, check CPI
    assert "CPI" in result["data"]["interpretation"] or "RTI" in result["data"]["interpretation"]


@pytest.mark.asyncio
async def test_ibp_job_no_tasks():
    """When no jobs ran at all, interpretation must say heuristic never triggered."""
    mock_resp = {"results": []}
    ibp = _fake_ibp(mock_resp)
    from tools.ibp_job_monitor import get_ibp_job_status
    result = await get_ibp_job_status("2024-01-01", "2024-12-31", "000", ibp=ibp)

    assert result["status"] == "AVAILABLE"
    assert result["data"]["total_tasks"] == 0
    assert "never" in result["data"]["interpretation"].lower() or "no ibp" in result["data"]["interpretation"].lower()


@pytest.mark.asyncio
async def test_ibp_job_running_tasks():
    """When jobs are still running, interpretation must mention 'not completed'."""
    mock_resp = {"results": [_task("T001", "RUNNING")]}
    ibp = _fake_ibp(mock_resp)
    from tools.ibp_job_monitor import get_ibp_job_status
    result = await get_ibp_job_status("2024-01-01", "2024-12-31", ibp=ibp)

    assert result["status"] == "AVAILABLE"
    assert result["data"]["running_count"] == 1
    assert "not completed" in result["data"]["interpretation"].lower() or "running" in result["data"]["interpretation"].lower()


@pytest.mark.asyncio
async def test_ibp_job_list_response():
    """IBPClient may return a raw list (no 'results' wrapper)."""
    mock_resp = [_task("T001", "FAILED", "Authorisation error")]
    ibp = _fake_ibp(mock_resp)
    from tools.ibp_job_monitor import get_ibp_job_status
    result = await get_ibp_job_status("2024-01-01", "2024-12-31", ibp=ibp)

    assert result["status"] == "AVAILABLE"
    assert result["data"]["failed_count"] == 1


# ──────────────────────────────────────────────────────────────────────────────
# Error paths
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ibp_job_http_error_returns_missing():
    """HTTP error from IBPClient → MISSING_DATA with reason."""
    ibp = _fake_ibp({"error": True, "status_code": 403, "message": "Forbidden"})
    from tools.ibp_job_monitor import get_ibp_job_status
    result = await get_ibp_job_status("2024-01-01", "2024-12-31", ibp=ibp)

    assert result["status"] == "MISSING_DATA"
    assert "403" in result["reason"] or "Forbidden" in result["reason"]
    assert "manual_investigation" in result


@pytest.mark.asyncio
async def test_ibp_job_exception_returns_missing():
    """Exception from IBPClient → MISSING_DATA."""
    ibp = MagicMock()
    ibp.get = AsyncMock(side_effect=ConnectionError("timeout"))
    from tools.ibp_job_monitor import get_ibp_job_status
    result = await get_ibp_job_status("2024-01-01", "2024-12-31", ibp=ibp)

    assert result["status"] == "MISSING_DATA"
    assert "timeout" in result["reason"]
    assert "what_was_expected" in result
    assert "manual_investigation" in result
