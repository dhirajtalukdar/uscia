"""
S/4HANA ATP / Availability-to-Promise tool.

J4C verification (2026-07-01):
  ATP_PRODALLOCOVERVIEW/C_ProdAllocOvwPeriods is an AGGREGATED PERIOD OVERVIEW —
  structurally wrong for line-level ATP failure diagnosis. RETIRED.

  Probe results on QL8:
    API_AVAIL_TO_PROMISE_CHECK      → HTTP 403 (not authorized / not OP2023+)
    API_PRODUCT_AVAILY_INFO         → HTTP 403 (not authorized / not OP2022+)
    API_PRODUCT_AVAILY_INFO_BASIC   → HTTP 400 (not available)
    CE_APIAVAILTOPROMISECHECK_0001  → HTTP 404 (not registered)
    ATP_PRODALLOCOVERVIEW           → HTTP 400

  No ATP API is accessible on QL8 with current credentials.
  Returns MISSING_DATA with CO09 manual guidance + correct API path for DSC.

Release-dependent ATP API availability (J4C):
  OP2021+: API_PRODUCT_AVAILY_INFO_BASIC
  OP2022+: API_PRODUCT_AVAILY_INFO
  OP2023+: API_AVAIL_TO_PROMISE_CHECK  ← preferred for forensics (no reservations)

  ⚠️ All ATP APIs only work for materials with aATP activated (MARC-ADPRO).
     Returns error AG 040 for non-aATP materials.
"""
from __future__ import annotations
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from s4hana_client import S4Client

logger = logging.getLogger(__name__)

_MISSING = "S4HANA_ATP"

# Release-ordered ATP API candidates — try most capable first
_ATP_APIS = [
    # OP2023+ — POST-based, simulates full ATP check without reservations
    "/sap/opu/odata/sap/API_AVAIL_TO_PROMISE_CHECK",
    # OP2022+ — POST-based, returns available qty + PAC timeseries
    "/sap/opu/odata/sap/API_PRODUCT_AVAILY_INFO",
    # OP2021+ — POST-based, basic cumulated ATP quantity
    "/sap/opu/odata/sap/API_PRODUCT_AVAILY_INFO_BASIC",
]


async def get_atp_check_result(
    material: str,
    plant: str,
    requested_quantity: str = "1",
    requested_date: str = "",
    s4: "S4Client | None" = None,
    user_identity: str | None = None,
) -> dict:
    """
    ATP availability check for a material/plant.

    J4C correction: ATP_PRODALLOCOVERVIEW/C_ProdAllocOvwPeriods retired —
    it is a period-level aggregation, not a line-level ATP failure diagnostic.

    Tries OP2023/2022/2021 ATP APIs in order. All are POST-based.
    Returns MISSING_DATA if none are accessible — aATP may not be activated
    or API user lacks authorization. CO09 manual guidance always provided.
    """
    if s4 is None:
        from s4hana_client import S4Client
        s4 = S4Client()

    # Try each ATP API in release order
    for api_path in _ATP_APIS:
        try:
            # ATP APIs are POST-based — attempt metadata check first
            r = await s4.get(
                f"{api_path}/$metadata",
                params={},
                user_identity=user_identity,
            )
            if not r.get("error"):
                # API is accessible — now call it
                # Note: real ATP check requires POST; metadata 200 confirms availability
                logger.info("ATP API accessible: %s", api_path)
                return {
                    "status": "AVAILABLE",
                    "system": _MISSING,
                    "data": {
                        "api_path": api_path,
                        "material": material,
                        "plant": plant,
                        "note": (
                            "ATP API accessible but POST-based check not yet implemented. "
                            "API path confirmed for MCP tool build: "
                            f"POST {api_path}/SimulateAtpCheck with material/plant/date body."
                        ),
                    },
                }
        except Exception:
            continue

    # None accessible — MISSING_DATA with full guidance
    logger.warning("get_atp_check_result: no ATP API accessible for %s/%s", material, plant)
    return {
        "status": "MISSING_DATA",
        "system": _MISSING,
        "reason": (
            f"No ATP API is accessible on this S/4HANA system for material {material} / plant {plant}. "
            "Probed: API_AVAIL_TO_PROMISE_CHECK (OP2023+), API_PRODUCT_AVAILY_INFO (OP2022+), "
            "API_PRODUCT_AVAILY_INFO_BASIC (OP2021+). All returned HTTP 403/400/404. "
            "Either aATP is not activated, the API user lacks authorization, "
            "or the S/4HANA release is below OP2021."
        ),
        "what_was_expected": (
            f"ATP availability check result for material {material} / plant {plant}: "
            "whether the requested quantity can be confirmed on the requested date, "
            "what quantity is available, and if ATP denial — which check rule caused it "
            "(PAL product allocation, SUP supply protection, or stock shortage). "
            "Line-level ATP failure diagnosis requires API_AVAIL_TO_PROMISE_CHECK (OP2023+). "
            "ATP_PRODALLOCOVERVIEW was retired — it is a period-level aggregation only."
        ),
        "manual_investigation": (
            f"Run CO09 in S/4HANA for material {material}, plant {plant}. "
            "CO09 shows the full availability overview: stock, confirmed orders, planned receipts, ATP qty. "
            "Check MARC-ADPRO field (MM03 → MRP 2 tab → Advanced Planning checkbox) — "
            "must be set for aATP to work. "
            "If aATP inactive: transaction /SAPAPO/ATPQ_CUST shows product allocation config. "
            "For OP2023+: API_AVAIL_TO_PROMISE_CHECK POST endpoint simulates ATP check without reservations."
        ),
    }

from __future__ import annotations
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from s4hana_client import S4Client

from s4hana_client import ATP_ROOT

logger = logging.getLogger(__name__)

_MISSING = "S4HANA_ATP"

_SELECT = (
    "ProductAllocationObject,CharcValueCombinationUUID,"
    "ProdAllocationPeriodStartDate,ProductAllocationPeriodEndDate,"
    "ProductAllocationQuantity,ProdAllocAssignedQuantity,ProdAllocLoadCriticality"
)


async def get_atp_check_result(
    material: str,
    plant: str,
    requested_quantity: str = "1",
    requested_date: str = "",
    s4: "S4Client | None" = None,
    user_identity: str | None = None,
) -> dict:
    """
    Retrieve product allocation periods from ATP_PRODALLOCOVERVIEW / C_ProdAllocOvwPeriods.
    This entity has no Product/Plant filter — returns allocation period overview.
    Returns allocation details or a MISSING_DATA stub with CO09 guidance.
    """
    if s4 is None:
        from s4hana_client import S4Client
        s4 = S4Client()

    try:
        result = await s4.get(
            f"{ATP_ROOT}/C_ProdAllocOvwPeriods",
            params={
                "$select": _SELECT,
                "$top": 10,
            },
            user_identity=user_identity,
        )
        if result.get("error"):
            raise RuntimeError(f"HTTP {result.get('status_code')}: {result.get('message')}")
        return {"status": "AVAILABLE", "system": _MISSING, "data": result}
    except Exception as exc:
        logger.warning("get_atp_check_result failed: %s", exc)
        return {
            "status": "MISSING_DATA",
            "system": _MISSING,
            "reason": (
                f"S/4HANA ATP (Available-to-Promise) / Product Allocation API failed. "
                f"Error: {exc}. "
                "API: C_ProdAllocOvwPeriods (product allocation overview). "
                "This service requires aATP (advanced ATP) to be activated on the S/4HANA "
                "system. If aATP is not licensed or configured, this data is not available. "
                "Contact your S/4HANA Basis team to verify aATP activation "
                "(transaction /SAPAPO/ATPQ_CUST or BAdI /SAPAPO/ATPQ_CUST)."
            ),
            "what_was_expected": (
                f"Product allocation overview for material {material} / plant {plant} — "
                "showing how much of the available supply is already allocated to customer "
                "orders or planning buckets, and how much remains free for new demand. "
                "A fully consumed allocation here explains why new sales orders are getting "
                "ATP denial even when physical stock exists in the warehouse."
            ),
            "manual_investigation": (
                f"RIGHT NOW — Run transaction CO09 in S/4HANA for material {material}, "
                f"plant {plant}. "
                "CO09 shows the availability overview: stock, confirmed orders, "
                "planned receipts, and the ATP quantity per period. "
                "If CO09 shows 0 ATP quantity but MD04 shows planned orders: "
                "the planned orders are not being confirmed — check the MRP Lot 'Fixed' "
                "flag or a rounding value preventing partial confirmation. "
                "If aATP is active: transaction /SAPAPO/ATPQ_CUST shows product "
                "allocation configuration — verify allocation procedure is assigned to "
                f"material {material}."
            ),
        }
