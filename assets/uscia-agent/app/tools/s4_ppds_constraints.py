"""
S/4HANA PP/DS Flexible Constraints tool — direct OData v2 via BTP destination.
API: UI_SCM_FLEX_CONSTR_V2 (confirmed on QL8 — replaces OP_APIFLEXIBLECONSTRAINTS_0001)
"""
from __future__ import annotations
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from s4hana_client import S4Client

from s4hana_client import PPDS_CONSTRAINTS_ROOT

logger = logging.getLogger(__name__)

_MISSING = "S4HANA_PPDS_CONSTRAINTS"

_SELECT = (
    "AdvncdPlngFlxCnsKey,PlanningVersionExternal,AdvncdPlngSimulationVersion,"
    "AdvncdPlngStrtDteTme,AdvncdPlngEndDteTme,"
    "AdvncdPlngFlxCnsMinQty,AdvncdPlngFlxCnsMaxQty,AdvncdPlngFlxCnsTgtQty,"
    "PPDSFlxCnsConfirmedQuantity,AdvncdPlngFlxCnsObslt"
)


async def get_ppds_flexible_constraints(
    material: str,
    plant: str,
    s4: "S4Client | None" = None,
    user_identity: str | None = None,
) -> dict:
    """
    Retrieve PP/DS flexible constraints via UI_SCM_FLEX_CONSTR_V2 / Constraint.
    ConstraintType has no material/plant filter fields — returns top constraints for
    the planning landscape. OP_APIFLEXIBLECONSTRAINTS_0001 is not registered on QL8.
    Returns constraint definitions or a MISSING_DATA stub.
    """
    if s4 is None:
        from s4hana_client import S4Client
        s4 = S4Client()

    try:
        result = await s4.get(
            f"{PPDS_CONSTRAINTS_ROOT}/Constraint",
            params={
                "$select": _SELECT,
                "$top": 100,
            },
            user_identity=user_identity,
        )
        if result.get("error"):
            raise RuntimeError(f"HTTP {result.get('status_code')}: {result.get('message')}")
        return {"status": "AVAILABLE", "system": _MISSING, "data": result}
    except Exception as exc:
        logger.warning("get_ppds_constraints failed: %s", exc)
        return {
            "status": "MISSING_DATA",
            "system": _MISSING,
            "reason": (
                f"S/4HANA PP/DS Constraints API failed for plant {plant}. "
                f"Error: {exc}. "
                "API: /SAPAPO/C_PPDS_CONSTRAINTS (CDS view). This API may not be "
                "available in all S/4HANA releases — it requires PP/DS add-on activation. "
                "The API user may also lack /SAPAPO/* authorisation objects."
            ),
            "what_was_expected": (
                f"PP/DS flexible constraints and capacity limits for plant {plant} — "
                "including constraint definitions, capacity limits, validity periods, "
                "and whether any constraints are currently BINDING (i.e., actively "
                "preventing scheduling). "
                "A binding constraint that has not been reviewed is a common reason why "
                "PP/DS heuristics produce zero or partial planned orders for a plant."
            ),
            "manual_investigation": (
                f"RIGHT NOW — Run transaction /SAPAPO/CDPS0 in S/4HANA (PP/DS Constraint Editor) "
                f"for plant {plant}. "
                "Check: (1) Are any constraints currently active with validity period covering today? "
                "(2) Are capacity limits set to 0 or very low values? "
                "(3) Are constraints BINDING (flagged as hard constraint)? "
                "Also check: /SAPAPO/RRP7 (PP/DS Capacity Evaluation) — shows resource load "
                "vs capacity for all work centres in the plant. "
                "If resources are at 100% load, new planned orders cannot be scheduled — "
                "either extend capacity or adjust the planning horizon."
            ),
        }
