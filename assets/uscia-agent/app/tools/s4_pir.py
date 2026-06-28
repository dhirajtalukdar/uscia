"""
S/4HANA Planned Independent Requirements (PIR) tool — direct OData v2 via BTP destination.
API: API_PLND_INDEP_RQMT_SRV (OP_API_PLND_INDEP_RQMT_SRV_0001)
"""
from __future__ import annotations
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from s4hana_client import S4Client

from s4hana_client import PIR_ROOT

logger = logging.getLogger(__name__)

_MISSING = "S4HANA_PIR"

_SELECT = (
    "Product,Plant,PlndIndepRqmtType,PlndIndepRqmtVersion,"
    "PlndIndepRqmtInternalID,PlndIndepRqmtIsActive,PlndIndepRqmtLastChgdDateTime"
)


async def get_planned_independent_requirements(
    material: str,
    plant: str,
    planning_version: str,
    date_from: str,
    date_to: str,
    s4: "S4Client | None" = None,
    user_identity: str | None = None,
) -> dict:
    """
    Retrieve Planned Independent Requirements (PIR/demand basis) for a material/plant.
    Entity: PlannedIndepRqmt — filter fields are Product/Plant (not Material/MRPPlant).
    Returns list of PIR dicts or a MISSING_DATA stub.
    """
    if s4 is None:
        from s4hana_client import S4Client
        s4 = S4Client()

    try:
        result = await s4.get(
            f"{PIR_ROOT}/PlannedIndepRqmt",
            params={
                "$filter": (
                    f"Product eq '{material}' and Plant eq '{plant}'"
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
        logger.warning("get_pir failed: %s", exc)
        return {
            "status": "MISSING_DATA",
            "system": _MISSING,
            "guidance": (
                f"Check independent requirements in MD61/MD62 for material {material} "
                f"plant {plant} version {planning_version}. Verify demand exists for the date range."
            ),
        }
