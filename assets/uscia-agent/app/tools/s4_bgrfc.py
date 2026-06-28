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
            "reason": (
                f"S/4HANA bgRFC / Business Event Handler queue API (C_BEHQUEUEDATA_CDS) "
                f"is unreachable for plant {plant}. "
                f"Error: {exc}. "
                "The S/4HANA system may be temporarily unavailable, the API user may lack "
                "authorisation for C_BEHQUEUEDATA_CDS, or the BTP Destination (S4HANA) "
                "is misconfigured."
            ),
            "what_was_expected": (
                "Business Event Handler queue entries showing pending or failed "
                "bgRFC messages from the CIF integration (queues: APOC*) and MRP "
                f"background processing (queues: RSMPP*) for plant {plant} "
                f"around {date_from}. "
                "Stuck bgRFC queues are a primary cause of planned order data never "
                "reaching S/4HANA from IBP/PP/DS — every failed queue entry here "
                "corresponds to a planned order that was silently dropped."
                + (f" Related IBP EXTERNID: {externid}." if externid else "")
            ),
            "manual_investigation": (
                f"RIGHT NOW — Run transaction SM58 in S/4HANA. "
                f"Filter by: Creation date = {date_from}, Destination = APOC* (CIF queues) "
                f"or RSMPP* (MRP queues), Plant = {plant}. "
                "Status SYSFAIL = RFC destination down; CPICERR = network/timeout. "
                "To restart: select stuck entries → Edit → Repeat. "
                "Also run SMQ1 (qRFC outbound monitor) and check queues APOCQ* — "
                "stuck qRFC queues block all subsequent CIF transfers for the integration model. "
                + (f"Search for EXTERNID {externid} in SXMB_MONI to trace the originating message." if externid else "")
            ),
        }
