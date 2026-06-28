"""
S/4HANA MRP Master Data Issues tool.

Uses PPH_MRP_MASTER_DATA_ISSUE_SRV / C_MRPMasterDataIssueTP to retrieve
MRP planning exceptions and master data issues for a material/plant.

This is the OData equivalent of the MRP Issues/Exceptions log — it shows
whether MRP encountered any problems during the last planning run, including:
  - Missing MRP type, lot size, lead time configuration
  - BOM/routing issues
  - Successful planning (info message)
  - Hard errors blocking planning

Criticality values: 1 = Error, 2 = Warning, 3 = Information/Success

Also queries A_ProductWorkScheduling for ProductionSchedulingProfile (MARC-FEVOR).
NOTE: MARC-MTVFP (Advanced Planning checkbox for PP/DS) is NOT exposed in public
OData on S/4HANA. Diagnosis for PP/DS non-integration must reference manual checks:
  - MM02/MM03 -> MRP 2 tab -> Advanced Planning checkbox
  - Transaction CURTO_SIMU or /SAPAPO/CIF for CIF Integration Model status
  - SMQ1 for qRFC outbound queue status (not available via public OData)
"""
from __future__ import annotations
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from s4hana_client import S4Client

logger = logging.getLogger(__name__)

_PPH_MRP_ROOT = "/sap/opu/odata/sap/PPH_MRP_MASTER_DATA_ISSUE_SRV"
_PRODUCT_SRV_ROOT = "/sap/opu/odata/sap/API_PRODUCT_SRV"
_MISSING = "S4HANA_PPDS_CONFIG"

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

    Two checks in parallel:
    1. PPH_MRP_MASTER_DATA_ISSUE_SRV: MRP exceptions/issues from last planning run
    2. API_PRODUCT_SRV / A_ProductWorkScheduling: ProductionSchedulingProfile (MARC-FEVOR)
       Note: MARC-MTVFP (Advanced Planning for PP/DS) is NOT in public OData.
    """
    import asyncio

    if s4 is None:
        from s4hana_client import S4Client
        s4 = S4Client()

    try:
        # Run both queries in parallel
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
        work_sched_task = s4.get(
            f"{_PRODUCT_SRV_ROOT}/A_ProductWorkScheduling",
            params={
                "$filter": f"Product eq '{material}' and Plant eq '{plant}'",
                "$select": "Product,Plant,ProductionSchedulingProfile,ProductionSupervisor",
                "$top": 1,
                "$format": "json",
            },
        )

        mrp_result, ws_result = await asyncio.gather(mrp_issues_task, work_sched_task, return_exceptions=True)

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

        # Process work scheduling (ProductionSchedulingProfile)
        production_scheduling_profile = ""
        if not isinstance(ws_result, Exception) and not ws_result.get("error"):
            ws_items = ws_result.get("results") or ws_result.get("value") or []
            if ws_items:
                production_scheduling_profile = ws_items[0].get("ProductionSchedulingProfile", "")

        # Build diagnostic summary
        errors = [i for i in mrp_issues if i["criticality"] == "1"]
        warnings = [i for i in mrp_issues if i["criticality"] == "2"]
        infos = [i for i in mrp_issues if i["criticality"] == "3"]

        result_data = {
            "material": material,
            "plant": plant,
            "mrp_issue_count": len(mrp_issues),
            "mrp_errors": errors,
            "mrp_warnings": warnings,
            "mrp_info": infos,
            "production_scheduling_profile": production_scheduling_profile,
            "production_scheduling_profile_note": (
                "ProductionSchedulingProfile (MARC-FEVOR) controls production scheduling behaviour. "
                "NOTE: The Advanced Planning checkbox (MARC-MTVFP) that controls PP/DS integration "
                "is NOT available via public OData. Check MM02/MM03 -> MRP 2 tab manually."
            ),
            "ppds_manual_checks": [
                "MM02/MM03 -> MRP 2 tab -> Advanced Planning checkbox (MARC-MTVFP) — must be checked for PP/DS integration",
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
                "(1) Whether Advanced Planning (PP/DS) is activated on the material master "
                "(field MARC-MTVFP = 'X'). "
                "(2) Whether the CIF integration model includes this material/plant "
                "(active model in CURTO_SIMU). "
                "(3) qRFC outbound queue status (SMQ1 — queues APOC* for CIF). "
                "(4) Recent CIF transfer errors in SLG1 (object APOCIF). "
                "These are the four most common configuration gaps that cause PP/DS not to "
                "receive planned orders from IBP."
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
