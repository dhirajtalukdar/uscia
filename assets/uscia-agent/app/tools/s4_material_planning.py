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
            "reason": (
                f"S/4HANA Material Planning Data API failed for material {material} / plant {plant}. "
                f"Error: {exc}. "
                "API: I_MaterialPlanning (OData v2). The service may not be activated, "
                "or the API user lacks authorisation for material master MRP view data."
            ),
            "what_was_expected": (
                f"MRP configuration from material master for material {material} / plant {plant}: "
                "MRP type (PD=MRP, X0/X1=PP/DS, ND=no planning), MRP controller, "
                "lot sizing procedure, planning horizon, safety stock, and reorder point. "
                "Wrong MRP type is the single most common root cause of planning failures — "
                "if MRP type was recently changed from PD to ND, all planning stops immediately."
            ),
            "manual_investigation": (
                f"RIGHT NOW — Run transaction MM03 for material {material}, plant {plant}. "
                "Views to check: MRP 1 (MRP type, MRP controller, lot size), "
                "MRP 2 (planning time fence, safety time, Advanced Planning flag), "
                "MRP 3 (planning strategy, consumption mode). "
                "Key checks: "
                "(1) MRP type = 'PD' for standard MRP, or 'X0'/'X1' for PP/DS. "
                "If 'ND' — planning is OFF. "
                "(2) Planning horizon must be > 0 for PP/DS to schedule. "
                "(3) 'Advanced Planning' checkbox (MRP 2) must be ON for PP/DS visibility. "
                "To see change history: MM04 (display changes) or SE16 on CDHDR filtering MARC."
            ),
        }
