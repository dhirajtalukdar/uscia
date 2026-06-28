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
        "reason": (
            "SAP PI/PO (Process Integration / Process Orchestration) is not connected "
            "to USCIA. This tool is a planned stub for landscapes that use legacy PI/PO "
            "middleware alongside or instead of SAP Integration Suite (CPI). "
            "Live PI/PO monitoring will be wired in Phase 2 if your landscape uses PI/PO."
        ),
        "what_was_expected": (
            "PI/PO message flow records for the IBP → S/4HANA integration channel "
            f"between {date_from} and {date_to}. "
            "Failed messages here would explain why planned orders or demand signals "
            "did not transfer between IBP and S/4HANA in legacy integration landscapes."
        ),
        "manual_investigation": (
            "RIGHT NOW — Open transaction SXMB_MONI in PI/PO system, or the "
            "Runtime Workbench (RWB) → Component Monitoring → Integration Engine. "
            f"Date range: {date_from} to {date_to}. "
            "Filter by sender interface for IBP or RTI. "
            "Look for status FAILED or SYSERR. "
            "If your landscape uses CPI (not PI/PO), check SAP Integration Suite "
            "Message Monitor instead — CPI data is also currently a stub (Phase 2)."
        ),
    }
