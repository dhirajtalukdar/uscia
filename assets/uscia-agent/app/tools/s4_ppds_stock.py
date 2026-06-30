"""
S/4HANA PP/DS material-level supply evidence tool.

J4C verification (2026-07-01):
  PPDS_MRP_COCKPIT_SRV/ResourceUtilizations is EXCLUSIVELY resource/capacity
  oriented — no material number, no planned order, no supply element.
  RETIRED for material-level PP/DS forensics per J4C recommendation.

Replacement: API_PLANNED_ORDERS/A_PlannedOrder filtered by PlannedOrderType
  for PP/DS-relevant order types. Returns material-level PP/DS planned orders.
  PP/DS scheduling order evidence is now covered by system 16 (PPDS_RES_SCHEDULE).

PPDS_MRP_COCKPIT_SRV/ResourceUtilizations IS still valid for capacity overload
  detection (is a work center over-capacity?) — but that is not what this system
  is used for in USCIA's evidence collection.
"""
from __future__ import annotations
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from s4hana_client import S4Client

from s4hana_client import PLANNED_ORDER_ROOT

logger = logging.getLogger(__name__)

_MISSING = "S4HANA_PPDS_STOCK"

# PP/DS planned order types in S/4HANA embedded PP/DS
# PE = PP/DS planned order, LA = MRP planned order (both relevant)
_SELECT = (
    "PlannedOrder,Material,ProductionPlant,MRPPlant,PlannedOrderType,"
    "TotalQuantity,BaseUnit,ScheduledBasicStartDate,ScheduledBasicEndDate,"
    "PlannedOrderOpeningDate,PlannedOrderIsFirm,PlannedOrderIsConvertible,"
    "MRPController,ProductionVersion"
)


async def get_ppds_stock_level(
    material: str,
    plant: str,
    date_from: str,
    date_to: str,
    s4: "S4Client | None" = None,
    user_identity: str | None = None,
) -> dict:
    """
    Retrieve PP/DS planned orders for a material/plant via API_PLANNED_ORDERS.

    J4C correction: PPDS_MRP_COCKPIT_SRV/ResourceUtilizations is capacity-only
    and was structurally wrong for this purpose. Replaced with A_PlannedOrder
    which exposes material-level planned order data including PP/DS order types.
    PP/DS scheduling board evidence is covered by system 16 (PPDS_RES_SCHEDULE).
    """
    if s4 is None:
        from s4hana_client import S4Client
        s4 = S4Client()

    try:
        result = await s4.get(
            f"{PLANNED_ORDER_ROOT}/A_PlannedOrder",
            params={
                "$filter": (
                    f"Material eq '{material}' and MRPPlant eq '{plant}' "
                    f"and ScheduledBasicEndDate ge datetime'{date_from}T00:00:00' "
                    f"and ScheduledBasicStartDate le datetime'{date_to}T23:59:59'"
                ),
                "$select": _SELECT,
                "$top": 100,
                "$orderby": "ScheduledBasicStartDate desc",
            },
            user_identity=user_identity,
        )
        if result.get("error"):
            raise RuntimeError(f"HTTP {result.get('status_code')}: {result.get('message')}")

        items = result.get("value") or result.get("results") or []
        # Tag PP/DS-specific order types
        ppds_orders = [o for o in items if o.get("PlannedOrderType") in ("PE", "KE")]
        mrp_orders  = [o for o in items if o.get("PlannedOrderType") not in ("PE", "KE")]
        logger.info(
            "PPDS_STOCK: material=%s plant=%s total_orders=%d ppds_orders=%d mrp_orders=%d",
            material, plant, len(items), len(ppds_orders), len(mrp_orders),
        )
        return {"status": "AVAILABLE", "system": _MISSING, "data": result}

    except Exception as exc:
        logger.warning("get_ppds_stock_level failed: %s", exc)
        return {
            "status": "MISSING_DATA",
            "system": _MISSING,
            "reason": (
                f"S/4HANA planned order API (API_PLANNED_ORDERS) failed for "
                f"material {material} / plant {plant}. Error: {exc}."
            ),
            "what_was_expected": (
                f"PP/DS and MRP planned orders for material {material} / plant {plant} "
                f"between {date_from} and {date_to}. "
                "PP/DS order types PE/KE indicate orders visible in RRP3. "
                "Zero results means PP/DS has not scheduled this material — "
                "check CIF integration model (CURTO_SIMU) and PP/DS activation in MM02."
            ),
            "manual_investigation": (
                f"Run /SAPAPO/RRP3 for material {material}, plant {plant}. "
                "Empty board = CIF transfer failed or material not in active integration model. "
                "Check SMQ1 queues APOC* and SLG1 object APOCIF for errors."
            ),
        }



async def get_ppds_stock_level(
    material: str,
    plant: str,
    date_from: str,
    date_to: str,
    s4: "S4Client | None" = None,
    user_identity: str | None = None,
) -> dict:
    """
    Retrieve PP/DS capacity/stock data via PPDS_MRP_COCKPIT_SRV / ResourceUtilizations.
    OP_PPDSPRODTDSTLV_0001 is not registered on QL8 — PPDS_MRP_COCKPIT_SRV is the
    confirmed working alternative. Returns stock evidence or a MISSING_DATA stub.
    """
    if s4 is None:
        from s4hana_client import S4Client
        s4 = S4Client()

    try:
        result = await s4.get(
            f"{PPDS_STOCK_ROOT}/ResourceUtilizations",
            params={
                "$filter": f"Plant eq '{plant}'",
                "$top": 100,
            },
            user_identity=user_identity,
        )
        if result.get("error"):
            raise RuntimeError(f"HTTP {result.get('status_code')}: {result.get('message')}")
        return {"status": "AVAILABLE", "system": _MISSING, "data": result}
    except Exception as exc:
        logger.warning("get_ppds_stock_level failed: %s", exc)
        return {
            "status": "MISSING_DATA",
            "system": _MISSING,
            "reason": (
                f"S/4HANA PP/DS stock / resource availability API failed for material "
                f"{material} / plant {plant}. "
                f"Error: {exc}. "
                "This API queries the PP/DS supply board (RRP3 equivalent). "
                "The failure may indicate: PP/DS is not activated in this system, "
                "CIF has never transferred this material to PP/DS, or the API user "
                "lacks PP/DS authorisation objects."
            ),
            "what_was_expected": (
                f"PP/DS stock and supply element data for material {material} / plant {plant} — "
                "including available stock, PP/DS planned orders, capacity pegging, "
                "and resource load. "
                "Zero supply elements here means PP/DS has no visibility of this material, "
                "which typically means CIF transfer failed or the material is not in "
                "any active integration model."
            ),
            "manual_investigation": (
                f"RIGHT NOW — Run transaction /SAPAPO/RRP3 in S/4HANA for material {material}, "
                f"plant {plant}. "
                "If the supply board is EMPTY: CIF has not transferred the material to PP/DS. "
                "Check: CURTO_SIMU (integration model) — is this material/plant included? "
                "Check: SMQ1 queues APOC* — are there stuck outbound queues? "
                "Check: SLG1 → object APOCIF → error messages for this material. "
                "If RRP3 shows data but S/4HANA MRP (MD04) is empty, the PP/DS → S/4HANA "
                "transfer (bgRFC reverse) is stuck — check SM58 for RSMPP* queues."
            ),
        }
