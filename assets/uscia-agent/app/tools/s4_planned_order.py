"""
S/4HANA Planned Order tool — direct OData v2 via BTP destination.
API: API_PLANNED_ORDERS (confirmed on QL8 — replaces API_PLANNED_ORDERS_SRV which is not available)
"""
from __future__ import annotations
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from s4hana_client import S4Client

from s4hana_client import PLANNED_ORDER_ROOT

logger = logging.getLogger(__name__)

_MISSING = "S4HANA_PLANNED_ORDER"

_SELECT = (
    "PlannedOrder,Material,ProductionPlant,MRPPlant,PlannedOrderType,"
    "TotalQuantity,BaseUnit,ScheduledBasicStartDate,ScheduledBasicEndDate,"
    "PlannedOrderOpeningDate,LastChangeDateTime,PlannedOrderIsFirm,PlannedOrderIsConvertible"
)


async def get_planned_orders(
    material: str,
    plant: str,
    date_from: str,
    date_to: str,
    s4: "S4Client | None" = None,
    user_identity: str | None = None,
) -> dict:
    """
    Retrieve planned orders for a material/plant within a date range.
    Returns list of planned order dicts (under key 'results') or a MISSING_DATA stub.
    """
    if s4 is None:
        from s4hana_client import S4Client
        s4 = S4Client()

    try:
        result = await s4.get(
            f"{PLANNED_ORDER_ROOT}/A_PlannedOrder",
            params={
                "$filter": (
                    f"Material eq '{material}' and ProductionPlant eq '{plant}' "
                    f"and ScheduledBasicStartDate ge datetime'{date_from}T00:00:00' "
                    f"and ScheduledBasicEndDate le datetime'{date_to}T00:00:00'"
                ),
                "$select": _SELECT,
                "$top": 100,
            },
            user_identity=user_identity,
        )
        if result.get("error"):
            raise RuntimeError(f"HTTP {result.get('status_code')}: {result.get('message')}")
        return {"status": "AVAILABLE", "system": _MISSING, "data": result}
    except Exception as exc:
        logger.warning("get_planned_orders failed: %s", exc)
        return {
            "status": "MISSING_DATA",
            "system": _MISSING,
            "guidance": (
                f"Check MD04 (transaction MD04) for material {material} plant {plant}. "
                "Verify MRP run has been executed. Check MRP controller assignment and lot-size key."
            ),
        }
