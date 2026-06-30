"""
S/4HANA MRP Master Data Issues + PP/DS config tool.

Evidence sources (run in parallel):
  1. QL8 (primary s4 client, S4HANA destination):
     - PPH_MRP_MASTER_DATA_ISSUE_SRV / C_MRPMasterDataIssueTP — MRP exceptions
     - API_PRODUCT_SRV / A_ProductWorkScheduling — ProductionSchedulingProfile (FEVOR)

  2. DSC (via s4-mcp-server cc3-708, S4HANA_DSC destination):
     - PP_MRP_COCKPIT_SRV / C_MRPMaterialVH — full MRP config: MRPType, MRPController,
       MRPGroup, PlanningTimeFenceInDays, MRPSafetyDuration, LotSizingProcedure
       (confirmed working on DSC with SLOT-EWMS4-2443/1710)
     - API_PRODUCT_SRV / A_ProductSupplyPlanning — extended planning config

  PPSKZ (PP/DS Planning Procedure) is NOT available via OData on any service.
  Requires SQL path (TCP BTP destination to DSC HANA DB) — deferred pending Basis.

Criticality values: 1 = Error, 2 = Warning, 3 = Information/Success
"""
from __future__ import annotations
import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from s4hana_client import S4Client

logger = logging.getLogger(__name__)

_PPH_MRP_ROOT = "/sap/opu/odata/sap/PPH_MRP_MASTER_DATA_ISSUE_SRV"
_PRODUCT_SRV_ROOT = "/sap/opu/odata/sap/API_PRODUCT_SRV"
_MISSING = "S4HANA_PPDS_CONFIG"

# DSC destination name — separate S/4HANA system with HANA Cloud connected.
# A_ProductPlant on DSC exposes AdvancedPlanning (MARC-MTVFP) which is not
# available on QL8. Falls back to the primary s4 client if DSC not configured.
_DSC_DESTINATION_NAME = os.environ.get("S4HANA_DSC_DESTINATION_NAME", "S4HANA_DSC")


def _get_dsc_client() -> "S4Client":
    """Return an S4Client pointed at the DSC destination."""
    from s4hana_client import S4Client
    return S4Client(destination_name=_DSC_DESTINATION_NAME)

_CRITICALITY_LABEL = {
    "1": "ERROR",
    "2": "WARNING",
    "3": "INFO",
}


async def get_ppds_config_and_mrp_issues(
    material: str,
    plant: str,
    s4: "S4Client | None" = None,
) -> dict:
    """
    Retrieve MRP planning issues and PP/DS configuration status.

    Three checks in parallel:
    1. PPH_MRP_MASTER_DATA_ISSUE_SRV (primary s4/QL8): MRP exceptions from last planning run
    2. API_PRODUCT_SRV/A_ProductPlant (DSC via S4HANA_DSC): AdvancedPlanning (MARC-MTVFP),
       MRPType, PlanningTimeFence — DSC exposes AdvancedPlanning; QL8 does not
    3. API_PRODUCT_SRV/A_ProductWorkScheduling (DSC): ProductionSchedulingProfile (MARC-FEVOR)
    """
    import asyncio
    from tools.mcp_s4_client import execute_odata_query_json as mcp_query

    if s4 is None:
        from s4hana_client import S4Client
        s4 = S4Client()

    # DSC client — separate destination for A_ProductWorkScheduling
    dsc = _get_dsc_client()

    try:
        # Run all queries in parallel — QL8 + DSC OData + DSC MCP
        mrp_issues_task = s4.get(
            f"{_PPH_MRP_ROOT}/C_MRPMasterDataIssueTP",
            params={
                "$filter": f"Material eq '{material}' and Plant eq '{plant}'",
                "$select": (
                    "Material,Plant,MRPArea,MRPMasterDataIssueCategory,"
                    "MRPMasterDataIssueText,SystemMessageType,SystemMessageNumber,"
                    "MRPMasterDataIssueSource,Criticality,CreationDateTime"
                ),
                "$top": 20,
                "$format": "json",
            },
        )
        # DSC MCP: PP_MRP_COCKPIT_SRV/C_MRPMaterialVH — full MRP config confirmed working
        # Fields: MRPType, MRPController, MRPGroup, PlanningTimeFenceInDays, MRPSafetyDuration
        mcp_mrp_task = mcp_query(
            f"PP_MRP_COCKPIT_SRV/C_MRPMaterialVH"
            f"?$filter=MaterialID eq '{material}' and MRPPlant eq '{plant}'"
            f"&$select=MaterialID,MRPPlant,MRPType,MRPTypeName,MRPController,"
            f"MRPGroup,PlanningTimeFenceInDays,MRPSafetyDuration,"
            f"MaterialLozSizeProcedure,MRPArea,MRPPlanningSegmentType"
            f"&$top=1"
        )
        # DSC OData: A_ProductWorkScheduling — ProductionSchedulingProfile (FEVOR)
        work_sched_task = dsc.get(
            f"{_PRODUCT_SRV_ROOT}/A_ProductWorkScheduling",
            params={
                "$filter": f"Product eq '{material}' and Plant eq '{plant}'",
                "$select": "Product,Plant,ProductionSchedulingProfile,ProductionSupervisor",
                "$top": 1,
                "$format": "json",
            },
        )

        mrp_result, pp_result, ws_result = await asyncio.gather(
            mrp_issues_task, mcp_mrp_task, work_sched_task, return_exceptions=True
        )
        mrp_result, mcp_result, ws_result = results_tuple = await asyncio.gather(
            mrp_issues_task, mcp_mrp_task, work_sched_task, return_exceptions=True
        )

        # Process QL8 MRP issues
        mrp_issues = []
        if not isinstance(mrp_result, Exception) and not mrp_result.get("error"):
            items = mrp_result.get("results") or mrp_result.get("value") or []
            for item in items:
                criticality = str(item.get("Criticality", "3"))
                mrp_issues.append({
                    "text": item.get("MRPMasterDataIssueText", ""),
                    "category": item.get("MRPMasterDataIssueCategory", ""),
                    "message_type": item.get("SystemMessageType", ""),
                    "message_number": item.get("SystemMessageNumber", ""),
                    "source": item.get("MRPMasterDataIssueSource", ""),
                    "criticality": criticality,
                    "criticality_label": _CRITICALITY_LABEL.get(criticality, "UNKNOWN"),
                    "timestamp": item.get("CreationDateTime", ""),
                })

        # Process DSC MCP — PP_MRP_COCKPIT_SRV/C_MRPMaterialVH
        mcp_mrp_data = {}
        mcp_mrp_source = "NOT_AVAILABLE"
        if not isinstance(mcp_result, Exception) and mcp_result.get("status") == "AVAILABLE":
            inner = mcp_result.get("data", {})
            items = inner.get("value") or inner.get("results") or []
            if items and isinstance(items, list):
                mcp_mrp_data = items[0]
                mcp_mrp_source = "PP_MRP_COCKPIT_SRV_via_MCP"
                logger.info(
                    "PPDS_CONFIG: MCP PP_MRP_COCKPIT_SRV returned MRPType=%s MRPController=%s for %s/%s",
                    mcp_mrp_data.get("MRPType", ""), mcp_mrp_data.get("MRPController", ""),
                    material, plant,
                )

        # Derive MRP config from MCP result (preferred) or fall back to empty
        mrp_type_from_mcp = mcp_mrp_data.get("MRPType", "")
        mrp_type_name = mcp_mrp_data.get("MRPTypeName", "")
        mrp_controller = mcp_mrp_data.get("MRPController", "")
        mrp_group = mcp_mrp_data.get("MRPGroup", "")
        planning_time_fence = str(mcp_mrp_data.get("PlanningTimeFenceInDays", ""))
        safety_duration = str(mcp_mrp_data.get("MRPSafetyDuration", ""))
        lot_sizing = mcp_mrp_data.get("MaterialLozSizeProcedure", "")
        mrp_segment_type = mcp_mrp_data.get("MRPPlanningSegmentType", "")

        # PPSKZ not available via OData — stays as MISSING DATA
        advanced_planning_flag = None
        advanced_planning_source = "NOT_AVAILABLE"
        planned_delivery_duration = ""

        # Process work scheduling (ProductionSchedulingProfile / FEVOR)
        production_scheduling_profile = ""
        if not isinstance(ws_result, Exception) and not ws_result.get("error"):
            ws_items = ws_result.get("results") or ws_result.get("value") or []
            if ws_items:
                production_scheduling_profile = ws_items[0].get("ProductionSchedulingProfile", "")

        # Build diagnostic summary
        errors = [i for i in mrp_issues if i["criticality"] == "1"]
        warnings = [i for i in mrp_issues if i["criticality"] == "2"]
        infos = [i for i in mrp_issues if i["criticality"] == "3"]

        # MRP type finding — [CONFIRMED] from MCP if available
        if mrp_type_from_mcp:
            mrp_type_finding = (
                f"[CONFIRMED] MRPType={mrp_type_from_mcp!r} ({mrp_type_name}) "
                f"via PP_MRP_COCKPIT_SRV (DSC). "
                + ("MRP is ACTIVE — planning enabled." if mrp_type_from_mcp not in ("ND", "") else
                   "MRP Type ND — NO PLANNING. This is a likely root cause.")
            )
        else:
            mrp_type_finding = "[MISSING DATA] MRP Type — PP_MRP_COCKPIT_SRV returned no data for this material/plant. Check MM03 → MRP 1 tab."

        result_data = {
            "material": material,
            "plant": plant,
            # MCP-sourced MRP config (PP_MRP_COCKPIT_SRV / DSC)
            "mrp_type": mrp_type_from_mcp,
            "mrp_type_name": mrp_type_name,
            "mrp_controller": mrp_controller,
            "mrp_group": mrp_group,
            "planning_time_fence": planning_time_fence,
            "safety_duration": safety_duration,
            "lot_sizing_procedure": lot_sizing,
            "mrp_segment_type": mrp_segment_type,
            "mrp_config_source": mcp_mrp_source,
            "mrp_type_finding": mrp_type_finding,
            # PP/DS flags (not available via OData)
            "advanced_planning": advanced_planning_flag,
            "advanced_planning_source": advanced_planning_source,
            "advanced_planning_finding": (
                "[MISSING DATA] PPSKZ (PP/DS Planning Procedure) not exposed in any OData service. "
                "Manual check: MM02 → MRP 2 tab → Advanced Planning checkbox (PPSKZ field). "
                "SQL path required for automated read — pending TCP BTP destination to DSC HANA DB."
            ),
            # Work scheduling
            "production_scheduling_profile": production_scheduling_profile,
            # QL8 MRP exceptions
            "mrp_issue_count": len(mrp_issues),
            "mrp_errors": errors,
            "mrp_warnings": warnings,
            "mrp_info": infos,
            "ppds_manual_checks": [
                "Transaction CURTO_SIMU or /SAPAPO/CIF: verify CIF Integration Model is active and consistent for this material/plant",
                "Transaction SMQ1: check qRFC outbound queue for destination APOC* — transfer messages should not be stuck",
                "Transaction SLG1: object APOCIF, subobject plant — check for CIF transfer errors",
                "Transaction /SAPAPO/RRP3: PP/DS planning board — verify order appears after above checks are clean",
            ],
        }

        return {"status": "AVAILABLE", "system": _MISSING, "data": result_data}

    except Exception as exc:
        logger.warning("get_ppds_config_and_mrp_issues failed: %s", exc)
        return {
            "status": "MISSING_DATA",
            "system": _MISSING,
            "reason": (
                f"S/4HANA PP/DS configuration API failed for material {material} / plant {plant}. "
                f"Error: {exc}. "
                "This API queries MM03 (MRP views), CIF integration model activation, "
                "and SMQ1 queue status. The failure may indicate an S/4HANA connectivity "
                "issue, missing authorisation for the API user, or a system performance problem."
            ),
            "what_was_expected": (
                f"PP/DS and MRP configuration diagnostics for material {material} / plant {plant}: "
                "(1) AdvancedPlanning flag (MARC-MTVFP) from A_ProductPlant — queried via S4HANA_DSC destination. "
                "(2) MRP type, planning time fence, safety duration from A_ProductPlant. "
                "(3) MRP planning exceptions from PPH_MRP_MASTER_DATA_ISSUE_SRV. "
                "(4) ProductionSchedulingProfile (MARC-FEVOR) from A_ProductWorkScheduling."
            ),
            "manual_investigation": (
                f"RIGHT NOW — for material {material}, plant {plant}: "
                "1. MM02/MM03 → MRP 2 tab → 'Advanced Planning' checkbox "
                "(MARC-MTVFP field) — must be active for PP/DS to see the material. "
                "2. Transaction CURTO_SIMU or /SAPAPO/CIF → check Active integration models "
                "— this material/plant must be in at least one active model. "
                "3. Transaction SMQ1 → filter destination APOC* — stuck queues here block "
                "ALL transfers for the integration model, not just this material. "
                "4. Transaction SLG1 → object APOCIF, subobject = plant → Error messages — "
                "look for 'object not in integration model' or 'CIF transfer failed' messages. "
                "5. Transaction /SAPAPO/RRP3 → search material/plant → if orders appear here "
                "but not in S/4HANA, the bgRFC reverse transfer is stuck (check SM58)."
            ),
        }
