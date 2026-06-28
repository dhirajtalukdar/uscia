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
            "reason": (
                f"S/4HANA Planned Independent Requirements (PIR) API failed for material "
                f"{material} / plant {plant}. "
                f"Error: {exc}. "
                "API: A_PlannedIndepRqmt_2. The service may not be activated on this "
                "S/4HANA system, or the API user lacks authorisation for PIR data."
            ),
            "what_was_expected": (
                f"Planned Independent Requirements (demand plan) for material {material} / "
                f"plant {plant}, planning version {planning_version}. "
                "PIRs are the demand signal that drives MRP and PP/DS planning — "
                "zero PIRs means no demand was transferred from IBP, which directly "
                "explains why no planned orders were generated."
            ),
            "manual_investigation": (
                f"RIGHT NOW — Run transaction MD62 (Display Planned Independent Requirements) "
                f"for material {material}, plant {plant}, planning version {planning_version}. "
                "If no rows appear: demand was never created or transferred from IBP. "
                "To check IBP → S/4HANA transfer: open IBP Supply Planning → check RTI "
                "(Real-Time Integration) transfer log for this material/plant — look for "
                "transfer status FAILED or PENDING. "
                "To manually create PIR for testing: MD61 (Create Independent Requirements). "
                "NOTE: IBP uses planning version 00 in S/4HANA by default."
            ),
        }
