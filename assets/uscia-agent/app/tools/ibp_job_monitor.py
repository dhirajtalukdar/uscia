"""
SAP IBP Monitor System Tasks — direct OData via IBPClient.

Connects to the IBP Monitor System Tasks API to check whether the IBP
supply planning (heuristic) job ran successfully, when it ran, and whether
it failed — enabling USCIA to diagnose "IBP never produced a plan" as the
root cause of missing planned orders.

BTP Destination required:
  Name:            IBP   (override via IBP_DESTINATION_NAME env var)
  Authentication:  OAuth2ClientCredentials

Falls back to MISSING_DATA with manual guidance when the destination is not
configured.
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ibp_client import IBPClient

logger = logging.getLogger(__name__)

_MISSING = "IBP_SUPPLY"

# IBP Monitor System Tasks OData service root
_MONITOR_ROOT = "/sap/opu/odata/IBP/MONITOR_SRV"
_SYSTEM_TASKS_ENTITY = "SystemTasks"


async def get_ibp_job_status(
    date_from: str = "",
    date_to: str = "",
    planning_version: str = "",
    ibp: "IBPClient | None" = None,
    user_identity: str | None = None,
) -> dict:
    """
    Retrieve IBP Monitor System Tasks to check planning job run status.

    Returns job records including status (Completed/Failed/Running), start time,
    end time, and error message so USCIA can diagnose why IBP produced no plan.

    Credentials resolved from BTP destination 'IBP' via IBPClient.
    Returns MISSING_DATA with manual guidance when IBP is not yet configured.
    """
    # Fast exit in testing mode
    if os.environ.get("IBD_TESTING") == "1" and ibp is None:
        return _missing(
            date_from, date_to, planning_version,
            reason="IBD_TESTING mode — no real IBP call",
        )

    if ibp is None:
        from ibp_client import IBPClient
        ibp = IBPClient()

    filter_parts: list[str] = []
    if date_from:
        filter_parts.append(f"StartTime ge datetime'{date_from}T00:00:00'")
    if date_to:
        filter_parts.append(f"StartTime le datetime'{date_to}T23:59:59'")
    if planning_version:
        filter_parts.append(f"PlanningVersion eq '{planning_version}'")

    params: dict = {
        "$orderby": "StartTime desc",
        "$top": 50,
        "$select": (
            "TaskId,TaskType,TaskStatus,PlanningVersion,"
            "StartTime,EndTime,ErrorMessage,CreatedByUser"
        ),
    }
    if filter_parts:
        params["$filter"] = " and ".join(filter_parts)

    try:
        result = await ibp.get(
            f"{_MONITOR_ROOT}/{_SYSTEM_TASKS_ENTITY}",
            params=params,
            user_identity=user_identity,
        )

        # Normalise: OData returns {"results": [...]} inside "d" wrapper (already unwrapped
        # by IBPClient.get); or a raw list; or an error dict.
        if isinstance(result, list):
            records = result
        else:
            if result.get("error"):
                raise RuntimeError(f"HTTP {result.get('status_code')}: {result.get('message')}")
            records = result.get("results") or []

        total = len(records)
        failed = [r for r in records if str(r.get("TaskStatus", "")).upper() in ("FAILED", "ERROR", "ABORTED")]
        completed = [r for r in records if str(r.get("TaskStatus", "")).upper() == "COMPLETED"]
        running = [r for r in records if str(r.get("TaskStatus", "")).upper() in ("RUNNING", "INPROGRESS")]

        logger.info(
            "IBP Monitor System Tasks: %d total, %d failed, %d completed, %d running "
            "(date_from=%s, date_to=%s, version=%s)",
            total, len(failed), len(completed), len(running),
            date_from, date_to, planning_version,
        )

        # Build interpretation
        if total == 0:
            interpretation = (
                f"No IBP planning jobs found "
                + (f"for version '{planning_version}' " if planning_version else "")
                + f"between {date_from} and {date_to}. "
                "The IBP supply planning heuristic was never triggered in this period — "
                "this explains why no planned orders exist in IBP and none were transferred "
                "to S/4HANA via RTI."
            )
        elif failed:
            latest_fail = failed[0]
            interpretation = (
                f"{len(failed)} IBP planning job(s) FAILED "
                + (f"for version '{planning_version}' " if planning_version else "")
                + f"between {date_from} and {date_to}. "
                f"Latest failure: TaskId={latest_fail.get('TaskId','')}, "
                f"StartTime={latest_fail.get('StartTime','')}, "
                f"Error: {latest_fail.get('ErrorMessage','(no message)')}. "
                "A failed IBP planning run produced no supply plan — no planned orders "
                "were generated and no RTI transfer to S/4HANA occurred."
            )
        elif running:
            interpretation = (
                f"{len(running)} IBP planning job(s) still RUNNING. "
                "The planning run has not completed — planned orders are not yet available. "
                "Wait for the job to complete before expecting RTI transfer to S/4HANA."
            )
        else:
            latest = completed[0] if completed else records[0]
            interpretation = (
                f"{len(completed)} IBP planning job(s) COMPLETED "
                + (f"for version '{planning_version}' " if planning_version else "")
                + f"between {date_from} and {date_to}. "
                f"Latest: TaskId={latest.get('TaskId','')}, "
                f"EndTime={latest.get('EndTime','')}, "
                f"Status={latest.get('TaskStatus','')}. "
                "IBP planning ran successfully — supply plan should exist. "
                "If planned orders are still missing in S/4HANA, check the RTI/CPI "
                "transfer (IBP_RTI_TO_S4HANA iFlow) for failures."
            )

        summaries = []
        for task in records[:20]:
            summaries.append({
                "TaskId": task.get("TaskId", ""),
                "TaskType": task.get("TaskType", ""),
                "TaskStatus": task.get("TaskStatus", ""),
                "PlanningVersion": task.get("PlanningVersion", ""),
                "StartTime": task.get("StartTime", ""),
                "EndTime": task.get("EndTime", ""),
                "ErrorMessage": task.get("ErrorMessage", ""),
                "CreatedByUser": task.get("CreatedByUser", ""),
            })

        return {
            "status": "AVAILABLE",
            "system": _MISSING,
            "data": {
                "total_tasks": total,
                "failed_count": len(failed),
                "completed_count": len(completed),
                "running_count": len(running),
                "tasks": summaries,
                "interpretation": interpretation,
            },
        }

    except Exception as exc:
        logger.warning("get_ibp_job_status failed: %s", exc)
        return _missing(date_from, date_to, planning_version, reason=str(exc))


def _missing(date_from: str, date_to: str, planning_version: str, reason: str = "") -> dict:
    """Return structured MISSING_DATA when IBP Monitor is not connected or call fails."""
    return {
        "status": "MISSING_DATA",
        "system": _MISSING,
        "reason": (
            "SAP IBP Monitor System Tasks are not available. "
            + (f"Error: {reason}. " if reason else "")
            + "Live IBP job monitoring requires a BTP Destination named 'IBP' "
            "(override via IBP_DESTINATION_NAME env var) with OAuth2ClientCredentials "
            "pointing to the IBP tenant. This is a Phase 2 integration item — "
            "configure IBP_BASE_URL, IBP_TOKEN_URL, IBP_CLIENT_ID, IBP_CLIENT_SECRET "
            "on this BTP subaccount to activate."
        ),
        "what_was_expected": (
            "IBP Monitor System Tasks showing whether the supply planning heuristic "
            f"ran successfully "
            + (f"for planning version '{planning_version}' " if planning_version else "")
            + f"between {date_from} and {date_to}. "
            "A failed or missing planning run explains why IBP produced no supply plan "
            "and consequently why no planned orders were transferred to S/4HANA via RTI."
        ),
        "manual_investigation": (
            "RIGHT NOW — Log into SAP IBP. "
            "Go to IBP Monitor → System Task Monitor (or System Tasks). "
            + (f"Filter: Planning Version = {planning_version}, " if planning_version else "")
            + f"Date = {date_from} to {date_to}. "
            "Check: (1) Did a supply planning heuristic job run in this period? "
            "Status must be 'Completed'. "
            "(2) If status is FAILED — read the error message; common causes: "
            "master data inconsistency, missing EXTERNID mapping, authorisation error, "
            "or IBP system overload. "
            "(3) If no job ran at all — check the IBP job scheduler "
            "(Job Monitor → Scheduled Jobs) to see if the periodic planning run "
            "is configured and active."
        ),
    }
