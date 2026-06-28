"""
S/4HANA Application Logs tool — reads SLG1 equivalent via APL_LOG_MANAGEMENT_SRV.
Confirmed on QL8: APL_LOG_MANAGEMENT_SRV / ApplicationLogHeaderSet + ApplicationLogMessageSet.
Filters by MRP/CIF/PP/DS relevant log objects (MPLANORD, APOCIF, MRP_PP_DS).
"""
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
            "guidance": (
                f"Check application logs in SLG1 (transaction SLG1). "
                f"Filter by object: MPLANORD (MRP planned orders), APOCIF (CIF transfer), "
                f"or MRP_PP_DS (PP/DS scheduling). "
                f"Date range: {date_from} to {date_to}. "
                f"Material: {material}, Plant: {plant}."
            ),
        }
