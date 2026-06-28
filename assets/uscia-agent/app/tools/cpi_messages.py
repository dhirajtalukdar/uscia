"""
SAP Integration Suite CPI Message Processing Logs — direct OData via CPIClient.

Connects to the CPI Message Processing Logs API (/api/v1/MessageProcessingLogs).
Filters for FAILED messages on the IBP_RTI_TO_S4HANA integration flow so USCIA
can diagnose RTI transfer failures between IBP and S/4HANA.

BTP Destination required:
  Name:            SAP_CPI   (override via CPI_DESTINATION_NAME env var)
  Authentication:  OAuth2ClientCredentials

Falls back to MISSING_DATA with manual guidance when the destination is not
configured (graceful degradation — same contract as the original stub).
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cpi_client import CPIClient

from cpi_client import MESSAGE_PROCESSING_ROOT

logger = logging.getLogger(__name__)

_MISSING = "SAP_CPI"

# Default iFlow name for IBP → S/4HANA RTI — override via env var if tenant uses a different name
_DEFAULT_IFLOW = os.environ.get("CPI_RTI_IFLOW", "IBP_RTI_TO_S4HANA")


async def get_cpi_message_status(
    date_from: str = "",
    date_to: str = "",
    externid: str = "",
    plant: str = "",
    cpi: "CPIClient | None" = None,
    user_identity: str | None = None,
) -> dict:
    """
    Retrieve CPI Message Processing Logs for the IBP → S/4HANA RTI interface.

    Returns failed message records so the USCIA root-cause engine can detect
    integration transfer failures as the root cause of missing planned orders.

    Credentials resolved from BTP destination 'SAP_CPI' (OAuth2ClientCredentials)
    or fallback env vars. Returns MISSING_DATA with manual guidance when CPI is
    not yet configured.
    """
    # Fast exit in testing mode — avoids real HTTP calls
    if os.environ.get("IBD_TESTING") == "1" and cpi is None:
        return _missing(date_from, date_to, externid, reason="IBD_TESTING mode — no real CPI call")

    if cpi is None:
        from cpi_client import CPIClient
        cpi = CPIClient()

    iflow = _DEFAULT_IFLOW
    filter_parts = [f"IntegrationFlowName eq '{iflow}'", "Status eq 'FAILED'"]
    if date_from:
        filter_parts.append(f"LogStart ge datetime'{date_from}T00:00:00'")
    if date_to:
        filter_parts.append(f"LogStart le datetime'{date_to}T23:59:59'")

    params: dict = {
        "$filter": " and ".join(filter_parts),
        "$orderby": "LogStart desc",
        "$top": 100,
        "$select": (
            "MessageGuid,CorrelationId,Status,IntegrationFlowName,"
            "Sender,Receiver,LogStart,LogEnd,ApplicationMessageId,"
            "ApplicationMessageType"
        ),
    }

    try:
        result = await cpi.get(MESSAGE_PROCESSING_ROOT, params=params, user_identity=user_identity)

        # Normalise: CPI OData returns {"results": [...]} inside the "d" wrapper
        # (already unwrapped by CPIClient.get); or a raw list; or an error dict.
        if isinstance(result, list):
            records = result
        else:
            if result.get("error"):
                raise RuntimeError(f"HTTP {result.get('status_code')}: {result.get('message')}")
            records = result.get("results") or []

        failed_count = len(records)
        logger.info(
            "CPI Message Processing Logs: %d FAILED messages for iFlow '%s' "
            "(date_from=%s, date_to=%s)",
            failed_count, iflow, date_from, date_to,
        )

        if failed_count == 0:
            return {
                "status": "AVAILABLE",
                "system": _MISSING,
                "data": {
                    "iflow": iflow,
                    "failed_count": 0,
                    "messages": [],
                    "interpretation": (
                        f"No FAILED messages found for iFlow '{iflow}' "
                        f"between {date_from} and {date_to}. "
                        "CPI integration transfer completed without errors — "
                        "RTI failure is not the root cause."
                    ),
                },
            }

        # Summarise key fields for the USCIA evidence graph
        summaries = []
        for msg in records[:20]:  # cap at 20 for prompt size
            summaries.append({
                "MessageGuid": msg.get("MessageGuid", ""),
                "CorrelationId": msg.get("CorrelationId", ""),
                "Status": msg.get("Status", ""),
                "IntegrationFlowName": msg.get("IntegrationFlowName", ""),
                "Sender": msg.get("Sender", ""),
                "Receiver": msg.get("Receiver", ""),
                "LogStart": msg.get("LogStart", ""),
                "LogEnd": msg.get("LogEnd", ""),
                "ApplicationMessageId": msg.get("ApplicationMessageId", ""),
            })

        # Derive likely error category from message count and correlation IDs
        unique_corr = len({m.get("CorrelationId", "") for m in records if m.get("CorrelationId")})
        interpretation = (
            f"{failed_count} FAILED message(s) found for iFlow '{iflow}' "
            f"between {date_from} and {date_to}. "
            + (f"{unique_corr} unique correlation IDs. " if unique_corr else "")
            + "CPI integration failures are the root cause — planned orders from IBP "
            "did NOT arrive in S/4HANA because the RTI transfer failed. "
            "Typical causes: S/4HANA receiver HTTP 500, IDOC posting error, "
            "CPI mapping failure, or OAuth token expiry on the S/4HANA adapter."
        )
        if externid:
            interpretation += (
                f" Search for ApplicationMessageId or CorrelationId containing '{externid}' "
                "to find the specific failed transfer for this material."
            )

        return {
            "status": "AVAILABLE",
            "system": _MISSING,
            "data": {
                "iflow": iflow,
                "failed_count": failed_count,
                "messages": summaries,
                "interpretation": interpretation,
            },
        }

    except Exception as exc:
        logger.warning("get_cpi_message_status failed: %s", exc)
        return _missing(date_from, date_to, externid, reason=str(exc))


def _missing(date_from: str, date_to: str, externid: str, reason: str = "") -> dict:
    """Return structured MISSING_DATA when CPI is not connected or call fails."""
    iflow = _DEFAULT_IFLOW
    base_reason = (
        "SAP Integration Suite (CPI) Message Processing Logs are not available. "
        + (f"Error: {reason}. " if reason else "")
        + "Live CPI data requires a BTP Destination named 'SAP_CPI' "
        "(override via CPI_DESTINATION_NAME env var) with OAuth2ClientCredentials "
        "pointing to the CPI tenant. This is a Phase 2 integration item — "
        "configure CPI_BASE_URL, CPI_CLIENT_ID, and CPI_CLIENT_SECRET "
        "(or CPI_CLIENT_KEY) on this BTP subaccount to activate."
    )
    return {
        "status": "MISSING_DATA",
        "system": _MISSING,
        "reason": base_reason,
        "what_was_expected": (
            f"CPI message processing logs for the IBP → S/4HANA RTI interface "
            f"(iFlow: {iflow}) between {date_from} and {date_to}. "
            "FAILED messages here are the definitive proof that planned orders from IBP "
            "did not arrive in S/4HANA because the CPI integration transfer failed."
            + (f" IBP EXTERNID for correlation: {externid}." if externid else "")
        ),
        "manual_investigation": (
            f"RIGHT NOW — Go to SAP Integration Suite → Monitor → Message Monitor. "
            f"Filter: iFlow = {iflow}, Status = FAILED, Date = {date_from} to {date_to}. "
            + (f"Search Message ID / EXTERNID: {externid}. " if externid else "")
            + "Alternatively open transaction SXMB_MONI in S/4HANA (PI/PO legacy path). "
            "Look for status FAILED or CANCELLED. Typical root causes: "
            "HTTP 500 from S/4HANA receiver, IDOC posting failure, mapping error in "
            "the CPI integration flow, or authentication token expiry on the S/4HANA adapter."
        ),
    }
