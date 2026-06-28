"""
SAP IBP Supply Data tool wrapper — direct OData via IBPClient.
Replaces the urllib-based implementation; same external interface.
"""
from __future__ import annotations
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ibp_client import IBPClient

from ibp_client import SUPPLY_PLANNING_ROOT

logger = logging.getLogger(__name__)

_MISSING = "IBP_SUPPLY"

_GUIDANCE = (
    "Check IBP supply plan in IBP Monitor. "
    "Verify planning run completed for version {version}. "
    "Check EXTERNID assignment for material {material} location {plant}. "
    "Navigate to IBP Monitor > Supply Planning > check job status and output key figures."
)


async def get_ibp_supply_data(
    material: str,
    plant: str,
    planning_version: str,
    date_from: str,
    date_to: str,
    ibp: "IBPClient | None" = None,
    user_identity: str | None = None,
) -> dict:
    """
    Retrieve IBP supply planning data for a material/location/version.
    Credentials resolved from BTP destination 'IBP' (OAuth2ClientCredentials)
    or fallback env vars. Returns supply objects or MISSING_DATA.
    """
    if ibp is None:
        from ibp_client import IBPClient
        ibp = IBPClient()

    try:
        result = await ibp.get(
            f"{SUPPLY_PLANNING_ROOT}/SupplyOrders",
            params={
                "$filter": (
                    f"Material eq '{material}' and Location eq '{plant}' "
                    f"and PlanningVersion eq '{planning_version}'"
                ),
                "$top": 100,
            },
            user_identity=user_identity,
        )
        if result.get("error"):
            raise RuntimeError(f"HTTP {result.get('status_code')}: {result.get('message')}")
        return {"status": "AVAILABLE", "system": _MISSING, "data": result}
    except Exception as exc:
        logger.warning("get_ibp_supply_data failed: %s", exc)
        return {
            "status": "MISSING_DATA",
            "system": _MISSING,
            "reason": (
                f"SAP IBP (Integrated Business Planning) Supply API failed for material "
                f"{material} / plant {plant}. "
                f"Error: {exc}. "
                "API: SupplyChain_SupplyKeyFigure (IBP OData). The IBP system may be "
                "unreachable, the IBP BTP Destination may be misconfigured, or the API "
                "user lacks IBP supply planning authorisations."
            ),
            "what_was_expected": (
                f"IBP supply planning key figures for material {material} / plant {plant}, "
                f"planning version {planning_version} — including planned supply quantities, "
                "planned order proposals from IBP heuristics, supply pegging to demand, "
                "and EXTERNID mapping for RTI transfer to S/4HANA. "
                "Zero supply here means IBP produced no plan, which explains why "
                "no planned orders were transferred to S/4HANA via RTI."
            ),
            "manual_investigation": (
                f"RIGHT NOW — Log into SAP IBP. "
                f"Go to IBP Monitor → Supply Planning → Job Monitor. "
                f"Check: (1) Was a supply planning run completed for version {planning_version} "
                f"in the relevant time period? Status should be 'Completed'. "
                f"(2) Go to Supply Planning → Supply Review for material {material}, "
                f"location {plant} — does IBP show supply quantities? "
                f"(3) Check EXTERNID assignment: material {material} must have an EXTERNID "
                f"mapped to an S/4HANA product/location for RTI transfer to work. "
                "If the supply plan exists in IBP but S/4HANA has no planned orders: "
                "the RTI transfer failed — check CPI / SXMB_MONI for the IBP_RTI_TO_S4HANA "
                "integration flow."
            ),
        }
