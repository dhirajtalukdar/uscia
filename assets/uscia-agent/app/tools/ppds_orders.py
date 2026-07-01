"""
PP/DS Order Evidence tool — PPDS_RES_SCHEDULE.

J4C verification (2026-07-01) — RETIRED for stateless programmatic use:

  QL8 probe: HTTP 500 "System alias 'UXRCLNT200_T' does not exist"
  DSC probe: HTTP 400 "Simulation does not exist. Please reload the app."

  J4C confirmed: PPDS_RES_SCHEDULE is a UI-backing service for the PP/DS
  planning board Fiori app. It requires an active Fiori/LiveCache simulation
  session context. Stateless MCP tool calls cannot provide this.

  Replacement: API_PLANNED_ORDERS/A_PlannedOrder (covered by S4HANA_PPDS_STOCK
  after its J4C correction).

  Custom SEGW on /SAPAPO/PORDER is the correct path for full PP/DS order
  forensics — requires ABAPer + embedded PP/DS activation confirmed (J4C Phase 1).
"""
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)

_MISSING = "PPDS_RES_SCHEDULE"


async def get_ppds_orders_and_alerts(
    material: str,
    plant: str,
    date_from: str,
    date_to: str,
) -> dict:
    """
    PPDS_RES_SCHEDULE retired — requires Fiori/LiveCache session (J4C verified 2026-07-01).

    PP/DS material-level order data is covered by S4HANA_PPDS_STOCK (system 4)
    which now queries API_PLANNED_ORDERS/A_PlannedOrder after J4C correction.
    """
    logger.info(
        "PPDS_RES_SCHEDULE: RETIRED — requires Fiori session. material=%s plant=%s",
        material, plant,
    )
    return {
        "status": "MISSING_DATA",
        "system": _MISSING,
        "reason": (
            "PPDS_RES_SCHEDULE requires an active Fiori/LiveCache simulation session — "
            "stateless programmatic access returns HTTP 400 'Simulation does not exist'. "
            "Verified on DSC (2026-07-01). This is a UI-backing service, not an API. "
            "PP/DS material-level order data is available via S4HANA_PPDS_STOCK "
            "(API_PLANNED_ORDERS/A_PlannedOrder, system 4)."
        ),
        "what_was_expected": (
            f"PP/DS scheduled orders and alerts for material {material} / plant {plant}. "
            "Full PP/DS scheduling forensics requires custom SEGW on /SAPAPO/PORDER "
            "(J4C ZIBP_PPDS_SRV) — needs embedded PP/DS activation confirmed + ABAPer."
        ),
        "manual_investigation": (
            f"Run /SAPAPO/RRP3 for material {material}, plant {plant} in S/4HANA. "
            "Empty board = CIF transfer failed or material not in active integration model. "
            "Check SMQ1 queues APOC* and SLG1 object APOCIF for errors."
        ),
    }
