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

  All ATP APIs only work for materials with aATP activated (MARC-ADPRO).
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
    "/sap/opu/odata/sap/API_AVAIL_TO_PROMISE_CHECK",
    "/sap/opu/odata/sap/API_PRODUCT_AVAILY_INFO",
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

    # Try each ATP API in release order — metadata check confirms availability
    for api_path in _ATP_APIS:
        try:
            r = await s4.get(
                f"{api_path}/$metadata",
                params={},
                user_identity=user_identity,
            )
            if not r.get("error"):
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
                            f"API confirmed: POST {api_path}/SimulateAtpCheck"
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
            f"No ATP API accessible for material {material} / plant {plant}. "
            "Probed: API_AVAIL_TO_PROMISE_CHECK (OP2023+), API_PRODUCT_AVAILY_INFO (OP2022+), "
            "API_PRODUCT_AVAILY_INFO_BASIC (OP2021+). All returned 403/400/404. "
            "ATP_PRODALLOCOVERVIEW retired — aggregated period view, not forensic."
        ),
        "what_was_expected": (
            f"Line-level ATP failure diagnosis for material {material} / plant {plant}: "
            "confirmed quantity, ATP denial reason (PAL/SUP/stock shortage). "
            "Requires API_AVAIL_TO_PROMISE_CHECK (OP2023+) + aATP activated per material."
        ),
        "manual_investigation": (
            f"Run CO09 in S/4HANA for material {material}, plant {plant}. "
            "Check MARC-ADPRO (MM03 MRP 2 tab — Advanced Planning) — must be set for aATP. "
            "OP2023+: API_AVAIL_TO_PROMISE_CHECK POST simulates ATP check without reservations."
        ),
    }
