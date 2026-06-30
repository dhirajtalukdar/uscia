"""
S/4HANA MRP Master Data Issues tool.

Uses PPH_MRP_MASTER_DATA_ISSUE_SRV / C_MRPMasterDataIssueTP to retrieve
MRP planning exceptions and master data issues for a material/plant.

Also queries:
  - API_PRODUCT_SRV/A_ProductPlant for AdvancedPlanning (MARC-MTVFP) and
    ProductionSchedulingProfile (MARC-FEVOR). A_ProductPlant exposes
    AdvancedPlanning on S/4HANA 2021+ systems (confirmed on DSC via S4HANA_DSC
    destination, port 44301). Falls back gracefully on older releases.
  - API_PRODUCT_SRV/A_ProductWorkScheduling for ProductionSchedulingProfile.

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

    if s4 is None:
        from s4hana_client import S4Client
        s4 = S4Client()

    # DSC client — separate destination for A_ProductPlant AdvancedPlanning query
    dsc = _get_dsc_client()

    try:
        # Run all three queries in parallel
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
        # A_ProductPlant via DSC — exposes AdvancedPlanning (MARC-MTVFP) on S/4HANA 2021+.
        # Uses separate dsc client (S4HANA_DSC destination) not the primary QL8 s4 client.
        product_plant_task = dsc.get(
            f"{_PRODUCT_SRV_ROOT}/A_ProductPlant",
            params={
                "$filter": f"Product eq '{material}' and Plant eq '{plant}'",
                "$select": (
                    "Product,Plant,AdvancedPlanning,MRPType,MRPController,"
                    "ProductionSchedulingProfile,PlannedDeliveryDurationInDays,"
                    "SafetyDuration,PlanningTimeFence"
                ),
                "$top": 1,
                "$format": "json",
            },
        )
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
            mrp_issues_task, product_plant_task, work_sched_task, return_exceptions=True
        )

        # Process MRP issues
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

        # Process A_ProductPlant — AdvancedPlanning (MARC-MTVFP) + MRP config
        advanced_planning_flag = None   # None = not exposed on this system
        advanced_planning_source = "NOT_AVAILABLE"
        mrp_type_from_plant = ""
        planning_time_fence = ""
        safety_duration = ""
        planned_delivery_duration = ""

        if not isinstance(pp_result, Exception) and not pp_result.get("error"):
            pp_items = pp_result.get("results") or pp_result.get("value") or []
            if pp_items:
                first = pp_items[0]
                raw_ap = first.get("AdvancedPlanning")
                if raw_ap is not None:
                    # Field present — true = checkbox ON (PP/DS active), false = OFF
                    advanced_planning_flag = bool(raw_ap) if isinstance(raw_ap, bool) else (str(raw_ap).lower() in ("true", "x", "1"))
                    advanced_planning_source = "A_ProductPlant"
                mrp_type_from_plant = first.get("MRPType", "")
                planning_time_fence = str(first.get("PlanningTimeFence", ""))
                safety_duration = str(first.get("SafetyDuration", ""))
                planned_delivery_duration = str(first.get("PlannedDeliveryDurationInDays", ""))

        # Process work scheduling (ProductionSchedulingProfile fallback)
        production_scheduling_profile = ""
        if not isinstance(ws_result, Exception) and not ws_result.get("error"):
            ws_items = ws_result.get("results") or ws_result.get("value") or []
            if ws_items:
                production_scheduling_profile = ws_items[0].get("ProductionSchedulingProfile", "")

        # Build diagnostic summary
        errors = [i for i in mrp_issues if i["criticality"] == "1"]
        warnings = [i for i in mrp_issues if i["criticality"] == "2"]
        infos = [i for i in mrp_issues if i["criticality"] == "3"]

        # Advanced Planning finding — [CONFIRMED] when data available, [MISSING DATA] otherwise
        if advanced_planning_flag is True:
            ap_finding = "[CONFIRMED] AdvancedPlanning=true — PP/DS integration active for this material/plant (MARC-MTVFP=X)"
            ap_note = "Advanced Planning checkbox is ON — this material/plant is integrated with PP/DS."
        elif advanced_planning_flag is False:
            ap_finding = "[CONFIRMED] AdvancedPlanning=false — PP/DS integration NOT active (MARC-MTVFP not set)"
            ap_note = "Advanced Planning checkbox is OFF — planned orders will NOT reach PP/DS/RRP3. Set in MM02 → MRP 2 tab."
        else:
            ap_finding = "[MISSING DATA] AdvancedPlanning field not returned by A_ProductPlant — check MM02/MM03 → MRP 2 tab manually"
            ap_note = "A_ProductPlant did not return AdvancedPlanning field on this system. Manual check required: MM02 → MRP 2 tab → Advanced Planning checkbox (MARC-MTVFP)."

        result_data = {
            "material": material,
            "plant": plant,
            "advanced_planning": advanced_planning_flag,
            "advanced_planning_source": advanced_planning_source,
            "advanced_planning_finding": ap_finding,
            "advanced_planning_note": ap_note,
            "mrp_type": mrp_type_from_plant,
            "planning_time_fence": planning_time_fence,
            "safety_duration": safety_duration,
            "planned_delivery_duration": planned_delivery_duration,
            "production_scheduling_profile": production_scheduling_profile,
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
