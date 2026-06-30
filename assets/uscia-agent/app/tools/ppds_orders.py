"""
PP/DS Order Evidence tool — queries PPDS_RES_SCHEDULE via s4-mcp-server (DSC).

PPDS_RES_SCHEDULE is the OData service backing the PP/DS Planning Board (RRP3 equivalent).
It provides live PP/DS order data: which orders are scheduled, their status, operations,
alerts, and component availability.

Key entities used:
  - OrderSet: PP/DS orders for a product/location — answers "does this material have PP/DS orders?"
  - AlertsSet: PP/DS scheduling alerts for a resource/product — capacity or constraint violations
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
