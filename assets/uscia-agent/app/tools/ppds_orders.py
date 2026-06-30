"""
PP/DS Order Evidence tool — PPDS_RES_SCHEDULE via s4-mcp-server (DSC).

J4C verification (2026-07-01) — RETIRED for stateless programmatic use:

  QL8 probe: HTTP 500 "System alias 'UXRCLNT200_T' does not exist"
    → PPDS_RES_SCHEDULE is registered against a different system alias on QL8.
      Not available on the S4HANA destination.

  DSC probe: HTTP 400 "Simulation does not exist. Please reload the app, then try again."
    → J4C confirmed: PPDS_RES_SCHEDULE is a UI-backing service for the PP/DS
      planning board Fiori app. It requires an active Fiori/LiveCache simulation
      session context. Stateless MCP tool calls cannot provide this.
      The error "Simulation does not exist" is the service requiring a session
      that a stateless HTTP call cannot establish.

  J4C recommendation:
    → RETIRE PPDS_RES_SCHEDULE for programmatic forensic use
    → Replace with API_PLANNED_ORDERS/A_PlannedOrder for material-level PP/DS
      order data (now covered by S4HANA_PPDS_STOCK after its correction)

This tool now returns MISSING_DATA with correct guidance.
System 16 (PPDS_RES_SCHEDULE) is kept in the evidence collector to
surface the structural gap explicitly in the forensic report.
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
    PPDS_RES_SCHEDULE retired — requires Fiori session context (J4C verified 2026-07-01).

    QL8: HTTP 500 - system alias not found.
    DSC: HTTP 400 - "Simulation does not exist" — LiveCache session required.

    PP/DS material-level order data now covered by S4HANA_PPDS_STOCK (system 4)
    which queries API_PLANNED_ORDERS/A_PlannedOrder after J4C correction.

    A custom SEGW service (ZIBP_PPDS_SRV on /SAPAPO/PORDER) is the correct
    path for stateless PP/DS order forensics — requires ABAPer + embedded PP/DS
    activation confirmation (J4C Phase 1, Step 1.5).
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
            "Verified on DSC (2026-07-01). This is a UI-backing service, not an API service. "
            "PP/DS material-level order data is available via S4HANA_PPDS_STOCK "
            "(API_PLANNED_ORDERS/A_PlannedOrder) from system 4."
        ),
        "what_was_expected": (
            f"PP/DS scheduled orders and alerts for material {material} / plant {plant}. "
            "For full PP/DS scheduling forensics a custom SEGW service on /SAPAPO/PORDER "
            "is required (J4C ZIBP_PPDS_SRV). "
            "This requires: embedded PP/DS activation confirmed + ABAPer to build service."
        ),
        "manual_investigation": (
            f"Run /SAPAPO/RRP3 for material {material}, plant {plant} in S/4HANA. "
            "If empty: PP/DS has no orders — check CIF integration model (CURTO_SIMU). "
            "If orders present: check transfer status back to S/4HANA (SM58 / bgRFC)."
        ),
    }

  - ComponentAvailability: component shortage / lateness data

This tool is the authoritative OData source for incident type:
  "planned order not reaching PP/DS RRP3"

All queries go through the s4-mcp-server (cc3-708) via MCP — no direct OData call.
"""
from __future__ import annotations
import logging

from tools.mcp_s4_client import execute_odata_query_json as mcp_query

logger = logging.getLogger(__name__)

_MISSING = "PPDS_RES_SCHEDULE"


async def get_ppds_orders_and_alerts(
    material: str,
    plant: str,
    date_from: str,
    date_to: str,
) -> dict:
    """
    Query PPDS_RES_SCHEDULE for PP/DS orders and alerts for a material/plant.

    Returns:
      status=AVAILABLE with:
        - ppds_orders: list of PP/DS orders (OrderSet)
        - ppds_alerts: list of scheduling alerts (AlertsSet)
        - component_issues: list of component availability problems
    """
    import asyncio

    try:
        # OrderSet — PP/DS orders for this product/location
        orders_task = mcp_query(
            f"PPDS_RES_SCHEDULE/OrderSet"
            f"?$filter=ProductNumber eq '{material}' and Location eq '{plant}'"
            f" and OrderStartTime ge datetime'{date_from}T00:00:00'"
            f" and OrderEndTime le datetime'{date_to}T23:59:59'"
            f"&$select=OrderNumber,OrderType,OrderStatus,ProductNumber,Location,"
            f"OrderStartTime,OrderEndTime,AtpOrderStatus,ConversionIndicator,"
            f"IsReleasedStatus,OltpSystemOrderNumber,ParentOrderId"
            f"&$top=50"
        )
        # AlertsSet — PP/DS alerts (capacity overloads, constraint violations)
        alerts_task = mcp_query(
            f"PPDS_RES_SCHEDULE/AlertsSet"
            f"?$filter=Product eq '{material}' and Location eq '{plant}'"
            f"&$select=AlertType,AlertTypeDescription,AlertObjectType,"
            f"AlertObjectTypeDescription,AlertTypeCount,Product,Location"
            f"&$top=20"
        )

        orders_result, alerts_result = await asyncio.gather(
            orders_task, alerts_task, return_exceptions=True
        )

        # Parse orders
        ppds_orders = []
        if not isinstance(orders_result, Exception) and orders_result.get("status") == "AVAILABLE":
            inner = orders_result.get("data", {})
            items = inner.get("value") or inner.get("results") or []
            ppds_orders = items if isinstance(items, list) else []

        # Parse alerts
        ppds_alerts = []
        if not isinstance(alerts_result, Exception) and alerts_result.get("status") == "AVAILABLE":
            inner = alerts_result.get("data", {})
            items = inner.get("value") or inner.get("results") or []
            ppds_alerts = items if isinstance(items, list) else []

        order_count = len(ppds_orders)
        alert_count = len(ppds_alerts)

        # Build finding
        if order_count > 0:
            order_statuses = list({o.get("OrderStatus", "") for o in ppds_orders if o.get("OrderStatus")})
            order_finding = (
                f"[CONFIRMED] {order_count} PP/DS order(s) found in PPDS_RES_SCHEDULE "
                f"for {material}/{plant}. Statuses: {order_statuses}. "
                f"Orders ARE reaching PP/DS scheduling layer."
            )
        else:
            order_finding = (
                f"[CONFIRMED] 0 PP/DS orders found in PPDS_RES_SCHEDULE for {material}/{plant} "
                f"in date range {date_from} to {date_to}. "
                f"Material/plant is NOT scheduled in PP/DS — planned orders are not reaching RRP3."
            )

        if alert_count > 0:
            alert_types = list({a.get("AlertTypeDescription", a.get("AlertType", "")) for a in ppds_alerts})
            alert_finding = (
                f"[CONFIRMED] {alert_count} PP/DS alert(s) detected: {alert_types[:5]}. "
                "Scheduling alerts indicate capacity overload or constraint violations."
            )
        else:
            alert_finding = f"[CONFIRMED] No PP/DS scheduling alerts for {material}/{plant}."

        logger.info(
            "PPDS_RES_SCHEDULE: material=%s plant=%s orders=%d alerts=%d",
            material, plant, order_count, alert_count,
        )

        return {
            "status": "AVAILABLE",
            "system": _MISSING,
            "data": {
                "material": material,
                "plant": plant,
                "ppds_order_count": order_count,
                "ppds_orders": ppds_orders[:10],
                "ppds_alert_count": alert_count,
                "ppds_alerts": ppds_alerts[:10],
                "order_finding": order_finding,
                "alert_finding": alert_finding,
                "source": "PPDS_RES_SCHEDULE via s4-mcp-server (DSC)",
            },
        }

    except Exception as exc:
        logger.warning("get_ppds_orders_and_alerts failed: %s", exc)
        return {
            "status": "MISSING_DATA",
            "system": _MISSING,
            "reason": (
                f"PPDS_RES_SCHEDULE query failed for {material}/{plant}. Error: {exc}. "
                "This service provides live PP/DS order and alert data from the DSC system."
            ),
            "what_was_expected": (
                f"PP/DS orders from PPDS_RES_SCHEDULE (RRP3 equivalent) for {material}/{plant}: "
                "whether planned orders are reaching PP/DS scheduling, order statuses, "
                "and any capacity/constraint alerts blocking scheduling."
            ),
            "manual_investigation": (
                f"Transaction /SAPAPO/RRP3 → search for product {material}, location {plant}. "
                "If orders appear in RRP3 but not in S/4HANA MD04, check SM58 for bgRFC reverse transfer. "
                "If no orders in RRP3, check CIF integration model (CURTO_SIMU) and PPSKZ in MM02."
            ),
        }
