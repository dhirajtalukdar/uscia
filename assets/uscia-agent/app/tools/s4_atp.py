"""
S/4HANA ATP / Product Allocation Overview tool — direct OData v2 via BTP destination.
API: ATP_PRODALLOCOVERVIEW (confirmed on QL8 — API_AVAILABILITYCHECKING_SRV not available on QL8).
Note: This covers product allocation / ABC strategy checks, NOT a real-time ATP simulation.
Entity set: A_ProdAllocOverview (C_ProdAllocOverview returned 404 — CDS view not activated).
"""
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
            "guidance": (
                f"Basic ATP check service is not available on this system. "
                f"For product allocation overview, check transaction CO09 for material {material} "
                f"plant {plant}. For real-time ATP simulation, contact your S/4HANA basis team "
                f"to activate API_AVAILABILITYCHECKING_SRV or aATP configuration."
            ),
        }
