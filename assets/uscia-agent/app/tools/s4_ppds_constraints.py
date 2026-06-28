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
            "guidance": (
                f"Check flexible constraints in PP/DS via /SAPAPO/CDPS0 or constraint editor "
                f"for plant {plant}. Verify capacity limits and validity periods are correctly maintained."
            ),
        }
