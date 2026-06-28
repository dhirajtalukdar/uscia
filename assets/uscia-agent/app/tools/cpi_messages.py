"""
SAP Integration Suite CPI Message Processing Logs — MISSING_DATA stub at go-live.
Returns SXMB_MONI guidance. Replaced post-deployment when CPI credentials are configured.
Stub activation: set CPI_BASE_URL, CPI_CLIENT_ID, CPI_CLIENT_SECRET env vars.
"""
from __future__ import annotations


async def get_cpi_message_status(
    date_from: str = "",
    date_to: str = "",
    externid: str = "",
    plant: str = "",
) -> dict:
    """
    CPI message processing log stub — always returns MISSING_DATA with SXMB_MONI guidance.
    """
    return {
        "status": "MISSING_DATA",
        "system": "SAP_CPI",
        "guidance": (
            f"Check CPI message processing in SXMB_MONI (transaction SXMB_MONI) "
            f"or SAP Integration Suite Message Monitor. "
            f"Filter by interface: IBP_RTI_TO_S4HANA. "
            f"Look for failed messages in the date range {date_from} to {date_to}. "
            + (f"Message ID from IBP EXTERNID: {externid}. " if externid else "")
            + "Check for HTTP 500 errors or mapping failures in the message log."
        ),
    }
