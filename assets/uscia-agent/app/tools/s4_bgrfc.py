"""
S/4HANA Business Event Handler Queue tool — direct OData v2 via BTP destination.
API: C_BEHQUEUEDATA_CDS (confirmed on QL8 — closest match for bgRFC/queue monitoring)
"""
from __future__ import annotations
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from s4hana_client import S4Client

from s4hana_client import BGRFC_ROOT

logger = logging.getLogger(__name__)

_MISSING = "S4HANA_BGRFC_QUEUE"

_SELECT = (
    "BusinessEvent,SAPObjectType,SAPObjectTypeName,BusEventPriority,"
    "SAPObjectTaskCode,SAPObjectTaskTypeName,BusinessEventSubscriberName,"
    "BusEventSubscriberCode"
)


async def get_bgrfc_queue_status(
    date_from: str = "",
    date_to: str = "",
    plant: str = "",
    externid: str = "",
    s4: "S4Client | None" = None,
    user_identity: str | None = None,
) -> dict:
    """
    Retrieve bgRFC / Business Event Handler queue status via C_BEHQUEUEDATA_CDS.
    Falls back to MISSING_DATA with SM58 guidance if service is unreachable.
    """
    if s4 is None:
        from s4hana_client import S4Client
        s4 = S4Client()

    try:
        filter_parts: list[str] = []
        # Note: CreationUTCDateTime is Edm.DateTimeOffset — OData v2 datetime filter
        # syntax is not compatible; omit date filter, fetch latest 100 entries

        params: dict = {
            "$select": _SELECT,
            "$top": 100,
        }
        # CreationUTCDateTime is Edm.DateTimeOffset — skip datetime filter,
        # fetch latest entries and let the agent assess queue state
        if filter_parts:
            params["$filter"] = " and ".join(filter_parts)

        result = await s4.get(
            f"{BGRFC_ROOT}/C_Behqueuedata",
            params=params,
            user_identity=user_identity,
        )
        if result.get("error"):
            raise RuntimeError(f"HTTP {result.get('status_code')}: {result.get('message')}")
        return {"status": "AVAILABLE", "system": _MISSING, "data": result}
    except Exception as exc:
        logger.warning("get_bgrfc_queue_status failed: %s", exc)
        return {
            "status": "MISSING_DATA",
            "system": _MISSING,
            "guidance": (
                f"Check bgRFC queue status in SM58 (transaction SM58). "
                f"Look for queues prefixed with APOC (CIF) or RSMPP (MRP). "
                f"Filter by date: {date_from}. "
                f"Check for SYSFAIL or CPICERR errors. "
                f"Also check SXMB_MONI for integration engine messages. "
                f"Plant: {plant}. "
                + (f"Related EXTERNID: {externid}." if externid else "")
            ),
        }
