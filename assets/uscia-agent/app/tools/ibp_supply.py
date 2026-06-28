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
            "guidance": _GUIDANCE.format(
                version=planning_version, material=material, plant=plant
            ),
        }
