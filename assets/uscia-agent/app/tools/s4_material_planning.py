"""
S/4HANA Material Planning Data tool — direct OData v2 via BTP destination.
API: PP_MRP_MATERIAL_COVERAGE_SRV (confirmed on QL8 — replaces API_MRP_MATERIALS_SRV_01 which is not available)
Entity: MRPMaterialCoverage
"""
from __future__ import annotations
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from s4hana_client import S4Client

from s4hana_client import MRP_MATERIALS_ROOT

logger = logging.getLogger(__name__)

_MISSING = "S4HANA_MATERIAL_PLANNING"

# Field set aligned to PP_MRP_MATERIAL_COVERAGE_SRV / MRPMaterialCoverage entity
_SELECT = (
    "Material,MRPPlant,MRPController,MRPType,MRPTypeName,"
    "LotSizingProcedure,ReorderThresholdQuantity,SafetyStockQuantity,"
    "MinimumLotSizeQuantity,MaximumLotSizeQuantity,FixedLotSizeQuantity,"
    "MaterialPlannedDeliveryDurn,MRPSafetyDuration,PlanningTimeFenceInDays"
)


async def get_material_planning_data(
    material: str,
    plant: str,
    s4: "S4Client | None" = None,
    user_identity: str | None = None,
) -> dict:
    """
    Retrieve MRP material planning configuration (MRP type, lot size, reorder point).
    Returns planning data dict or a MISSING_DATA stub.
    """
    if s4 is None:
        from s4hana_client import S4Client
        s4 = S4Client()

    try:
        result = await s4.get(
            f"{MRP_MATERIALS_ROOT}/A_MRPMaterial",
            params={
                "$filter": f"Material eq '{material}' and MRPPlant eq '{plant}'",
                "$select": _SELECT,
                "$top": 1,
            },
            user_identity=user_identity,
        )
        if result.get("error"):
            raise RuntimeError(f"HTTP {result.get('status_code')}: {result.get('message')}")
        return {"status": "AVAILABLE", "system": _MISSING, "data": result}
    except Exception as exc:
        logger.warning("get_material_planning_data failed: %s", exc)
        return {
            "status": "MISSING_DATA",
            "system": _MISSING,
            "guidance": (
                f"Check material master MRP views (transaction MM03) for material {material} "
                f"plant {plant}. Verify MRP type is set (PD, VB, etc.) and planning horizon is maintained."
            ),
        }
