"""
SAP PI/PO Message Monitoring — MISSING_DATA stub (legacy middleware landscapes only).
"""
from __future__ import annotations


async def get_pipo_message_status(
    date_from: str = "",
    date_to: str = "",
    plant: str = "",
) -> dict:
    """
    PI/PO message monitoring stub — always returns MISSING_DATA.
    Used in landscapes with legacy SAP PI/PO middleware alongside or instead of CPI.
    """
    return {
        "status": "MISSING_DATA",
        "system": "SAP_PIPO",
        "guidance": (
            "Check PI/PO message monitoring in SXMB_MONI (transaction SXMB_MONI) "
            "or the Runtime Workbench (RWB). "
            "Filter by sender interface for IBP/RTI integration. "
            f"Date range: {date_from} to {date_to}. "
            "Check for FAILED or CANCELLED message status in the integration channel."
        ),
    }
