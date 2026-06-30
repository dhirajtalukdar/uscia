"""
S/4HANA Application Logs tool — APL_LOG_MANAGEMENT_SRV.

J4C correction (2026-07-01):
  1. Added /IBP/ECC_INT as primary object — this is the RTI-specific log object
     for inbound order processing errors. Previously missing from filter.
  2. Added ApplicationLogItemSet call to fetch actual error message text.
     Prior implementation returned headers only (LogHandle, Severity) with no
     message detail — forensically insufficient per J4C analysis.
  3. PII: CreatedByUser (AlUser) excluded from item select per J4C guidance.

SLG1 objects covered:
  /IBP/ECC_INT  ORDER_INBOUND   ← RTI inbound order errors (NEW — J4C)
  /SAPAPO/CIF   (various)       ← CIF transfer errors
  MPLANORD                      ← MRP planned order creation/deletion
  APOCIF                        ← CIF transfer errors (legacy object)
  MRP_PP_DS                     ← PP/DS scheduling errors
"""
from __future__ import annotations
import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from s4hana_client import S4Client

logger = logging.getLogger(__name__)

_APP_LOG_ROOT = "/sap/opu/odata/sap/APL_LOG_MANAGEMENT_SRV"
_MISSING = "S4HANA_APPLICATION_LOGS"

# RTI-specific object added first per J4C — this is the forensic primary
_RELEVANT_OBJECTS = ["/IBP/ECC_INT", "/SAPAPO/CIF", "MPLANORD", "APOCIF", "MRP_PP_DS", "QPAPER", "MRP"]

_HEADER_SELECT = (
    "LogHandle,Object,SubObject,ExternalNumber,CreatedAt,"
    "Severity,MessageTotalCount"
    # CreatedByUser excluded — PII per J4C guidance
)

_ITEM_SELECT = (
    "LogHandle,MsgNumber,MsgType,MsgId,MsgNo,"
    "MsgV1,MsgV2,MsgV3,MsgV4"
    # No user-identifying fields per J4C PII guidance
)


async def get_application_logs(
    date_from: str = "",
    date_to: str = "",
    material: str = "",
    plant: str = "",
    s4: "S4Client | None" = None,
) -> dict:
    """
    Retrieve application log headers + message items from APL_LOG_MANAGEMENT_SRV.

    J4C correction: added /IBP/ECC_INT as primary RTI log object, and added
    ApplicationLogItemSet call to retrieve actual error message text (MsgV1-V4).
    Headers alone are forensically insufficient — message text is needed.
    """
    if s4 is None:
        from s4hana_client import S4Client
        s4 = S4Client()

    try:
        # Build object filter — /IBP/ECC_INT first (RTI-specific, highest priority)
        obj_filter = " or ".join(f"Object eq '{o}'" for o in _RELEVANT_OBJECTS)
        filter_str = f"({obj_filter})"
        if plant:
            filter_str += f" and SubObject eq '{plant}'"

        # Step 1: fetch log headers
        header_result = await s4.get(
            f"{_APP_LOG_ROOT}/ApplicationLogHeaderSet",
            params={
                "$filter": filter_str,
                "$select": _HEADER_SELECT,
                "$top": 100,
                "$orderby": "CreatedAt desc",
            },
        )
        if header_result.get("error"):
            raise RuntimeError(f"HTTP {header_result.get('status_code')}: {header_result.get('message')}")

        headers = header_result.get("value") or header_result.get("results") or []

        # Step 2: for ERROR/WARNING headers, fetch message item detail
        # Limit to top 10 error headers to avoid excessive calls
        error_headers = [h for h in headers if h.get("Severity") in ("E", "W")][:10]

        items_by_handle: dict = {}
        if error_headers:
            item_tasks = [
                s4.get(
                    f"{_APP_LOG_ROOT}/ApplicationLogItemSet",
                    params={
                        "$filter": f"LogHandle eq '{h['LogHandle']}'",
                        "$select": _ITEM_SELECT,
                        "$top": 20,
                    },
                )
                for h in error_headers
            ]
            item_results = await asyncio.gather(*item_tasks, return_exceptions=True)
            for h, r in zip(error_headers, item_results):
                if isinstance(r, Exception) or (isinstance(r, dict) and r.get("error")):
                    continue
                msgs = r.get("value") or r.get("results") or []
                if msgs:
                    items_by_handle[h["LogHandle"]] = msgs

        logger.info(
            "APP_LOGS: plant=%s headers=%d error_headers=%d handles_with_items=%d",
            plant, len(headers), len(error_headers), len(items_by_handle),
        )

        # Attach message items to headers for downstream narration
        enriched_headers = []
        for h in headers:
            entry = dict(h)
            if h.get("LogHandle") in items_by_handle:
                entry["MessageItems"] = items_by_handle[h["LogHandle"]]
            enriched_headers.append(entry)

        return {
            "status": "AVAILABLE",
            "system": _MISSING,
            "data": {"value": enriched_headers},
        }

    except Exception as exc:
        logger.warning("get_application_logs failed: %s", exc)
        return {
            "status": "MISSING_DATA",
            "system": _MISSING,
            "reason": (
                f"S/4HANA Application Logs API (APL_LOG_MANAGEMENT_SRV) failed "
                f"for material {material} / plant {plant}. Error: {exc}."
            ),
            "what_was_expected": (
                f"Application log entries from SLG1 for RTI/CIF/MRP objects: "
                "/IBP/ECC_INT ORDER_INBOUND (RTI inbound order errors), "
                "/SAPAPO/CIF (CIF transfer failures), "
                "MPLANORD (MRP planned order errors), "
                f"MRP_PP_DS (PP/DS scheduling errors). "
                f"Date range: {date_from} to {date_to}. "
                "Error message text (MsgV1-V4) needed for root cause — headers alone insufficient."
            ),
            "manual_investigation": (
                f"Run SLG1 in S/4HANA. "
                f"Object /IBP/ECC_INT, Subobject ORDER_INBOUND — RTI inbound errors. "
                f"Object /SAPAPO/CIF — CIF transfer errors. "
                f"Object MPLANORD — planned order errors. "
                f"Date: {date_from} to {date_to}, Plant: {plant}."
            ),
        }

from __future__ import annotations
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from s4hana_client import S4Client

logger = logging.getLogger(__name__)

_APP_LOG_ROOT = "/sap/opu/odata/sap/APL_LOG_MANAGEMENT_SRV"
_MISSING = "S4HANA_APPLICATION_LOGS"

# Supply-chain-relevant SLG1 log objects
_RELEVANT_OBJECTS = ["MPLANORD", "APOCIF", "MRP_PP_DS", "QPAPER", "MRP"]

_SELECT = (
    "LogHandle,Object,SubObject,ExternalNumber,CreatedAt,"
    "Severity,MessageTotalCount,CreatedByUser"
)


async def get_application_logs(
    date_from: str = "",
    date_to: str = "",
    material: str = "",
    plant: str = "",
    s4: "S4Client | None" = None,
) -> dict:
    """
    Retrieve application log headers from APL_LOG_MANAGEMENT_SRV for supply chain objects.
    Filters by relevant log objects (MPLANORD, APOCIF, MRP_PP_DS).
    """
    if s4 is None:
        from s4hana_client import S4Client
        s4 = S4Client()

    try:
        # Build object filter — OR across relevant log objects
        obj_filter = " or ".join(f"Object eq '{o}'" for o in _RELEVANT_OBJECTS)
        filter_str = f"({obj_filter})"
        if plant:
            filter_str += f" and SubObject eq '{plant}'"

        result = await s4.get(
            f"{_APP_LOG_ROOT}/ApplicationLogHeaderSet",
            params={
                "$filter": filter_str,
                "$select": _SELECT,
                "$top": 100,
                "$orderby": "CreatedAt desc",
            },
        )
        if result.get("error"):
            raise RuntimeError(f"HTTP {result.get('status_code')}: {result.get('message')}")
        return {"status": "AVAILABLE", "system": _MISSING, "data": result}
    except Exception as exc:
        logger.warning("get_application_logs failed: %s", exc)
        return {
            "status": "MISSING_DATA",
            "system": _MISSING,
            "reason": (
                f"S/4HANA Application Logs API (APL_LOG_MANAGEMENT_SRV) returned an error "
                f"for material {material} / plant {plant}. "
                f"The S/4HANA system may be temporarily unreachable, the service may not be "
                "activated on this system, or the API user may lack the required authorisation "
                "object S_APPL_LOG."
            ),
            "what_was_expected": (
                f"Application log headers from SLG1 for supply chain objects: "
                "MPLANORD (MRP planned order creation/deletion errors), "
                "APOCIF (CIF transfer failures between S/4HANA and IBP/PP/DS), "
                f"MRP_PP_DS (PP/DS scheduling and heuristic run errors). "
                f"Date range: {date_from} to {date_to}. "
                "These logs directly record which MRP or CIF steps failed and why."
            ),
            "manual_investigation": (
                f"RIGHT NOW — Run transaction SLG1 in S/4HANA. "
                f"Object: MPLANORD (for planned order errors) or APOCIF (for CIF/IBP transfer issues) "
                f"or MRP_PP_DS (for PP/DS scheduling failures). "
                f"Date: {date_from} to {date_to}. "
                f"Plant: {plant}, Material: {material}. "
                "Severity: Error and Warning. "
                "Error messages starting with M7 (inventory), M3 (MRP), or CIF* (integration) "
                "are the most relevant for supply chain planning failures."
            ),
        }
