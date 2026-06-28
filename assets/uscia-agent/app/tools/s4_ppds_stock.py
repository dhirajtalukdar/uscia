"""
S/4HANA PP/DS MRP Cockpit tool — direct OData v2 via BTP destination.
API: PPDS_MRP_COCKPIT_SRV (confirmed on QL8 — replaces OP_PPDSPRODTDSTLV_0001)
"""
from __future__ import annotations
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from s4hana_client import S4Client

from s4hana_client import PPDS_STOCK_ROOT

logger = logging.getLogger(__name__)

_MISSING = "S4HANA_PPDS_STOCK"

_SELECT = (
    "Resources,CapacityUtilizationDefinitions,AreaOfResponsibility,"
    "ResourceUtilizations"
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
            "guidance": (
                f"Check PP/DS stock situation via RRP3 (transaction RRP3) for material {material} "
                f"plant {plant}. Verify CIF transfer has populated PP/DS supply board."
            ),
        }
