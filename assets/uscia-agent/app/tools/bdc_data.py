"""
SAP Business Data Cloud (BDC) evidence tool.

Queries the SAP Datasphere REST SQL API for historical supply chain analytics
data that enriches the transactional picture from S/4HANA and IBP.

BDC adds three types of historical context that transactional APIs cannot provide:
  1. Demand history        — Are demand spikes driving the planning gap?
  2. Planned order history — Has production regularly run for this material/plant before?
  3. Master data changes   — Did recent MRP type / planning horizon changes precede the issue?

Connection:
  Uses the BTP Destination named "SAP_BDC" (override with BDC_DESTINATION_NAME env var).

  The destination must be of type HTTP with OAuth2ClientCredentials authentication,
  pointing to a SAP Datasphere (formerly Data Warehouse Cloud) tenant.

  SAP Datasphere REST SQL API path:
      POST <tenant-url>/api/v1/dwc/catalog/assets:executeSQL
  Request body:  {"sql": "<statement>"}
  Response body: {"rows": [[...], ...], "columns": [{"name": "..."}, ...]}

  If the destination is not configured the tool returns MISSING_DATA with manual
  guidance — never raises an exception.

BTP Destination configuration (Connectivity → Destinations):
  Name:           SAP_BDC
  Type:           HTTP
  URL:            https://<your-tenant>.us10.hcs.cloud.sap
  Authentication: OAuth2ClientCredentials
  Client ID:      <from Datasphere service key>
  Client Secret:  <from Datasphere service key>
  Token URL:      <from Datasphere service key OAuth2 token endpoint>

Called by evidence/collector.py as the 14th parallel gather task.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_BDC_DESTINATION = os.environ.get("BDC_DESTINATION_NAME", "SAP_BDC")

# Datasphere REST SQL API path (confirmed endpoint for SAP Datasphere tenant)
_DWC_SQL_PATH = "/api/v1/dwc/catalog/assets:executeSQL"


# ---------------------------------------------------------------------------
# CF-native destination resolver  (same pattern as s4hana_client.py)
# ---------------------------------------------------------------------------

def _get_resolver() -> Any:
    """Lazily import _DestinationResolver — path works in both CF (--chdir app) and test envs."""
    try:
        from s4hana_client import _DestinationResolver  # noqa: PLC0415  (CF path)
    except ImportError:
        from app.s4hana_client import _DestinationResolver  # noqa: PLC0415  (test/dev path)
    return _DestinationResolver()


# ---------------------------------------------------------------------------
# DPQuery accessor  (thin wrapper — monkey-patched in tests via IBD_TESTING=1)
# ---------------------------------------------------------------------------

async def _call_dpquery(sql: str) -> dict:
    """
    Execute a SQL string against the SAP Datasphere REST SQL API via BTP Destination.

    Uses the CF-native _DestinationResolver from s4hana_client.py — no Joule/Kyma SDK
    dependency.  The destination must be OAuth2ClientCredentials type pointing to the
    SAP Datasphere tenant URL.

    Returns the parsed JSON response dict, or raises on error.

    In test environments (IBD_TESTING=1) this function is monkey-patched by
    the test suite — do NOT add retry logic that would swallow patched errors.

    SAP Datasphere REST SQL API:
      POST <tenant-url>/api/v1/dwc/catalog/assets:executeSQL
      Body: {"sql": "<statement>"}
      Response: {"rows": [[col1, col2, ...], ...], "columns": [{"name": "..."}, ...]}
    """
    resolver = _get_resolver()
    dest = await resolver.resolve(_BDC_DESTINATION)

    # For OAuth2ClientCredentials destinations, the BTP Destination service
    # automatically injects the token — accessible via the destination's
    # additional properties or by exchanging credentials directly.
    # We use the client credentials from dest.additional (populated by
    # _DestinationResolver from destinationConfiguration).
    token_url: str | None = dest.additional.get("tokenServiceURL")
    client_id: str | None = dest.additional.get("clientId") or dest.user
    client_secret: str | None = dest.additional.get("clientSecret") or dest.pw

    if not token_url or not client_id or not client_secret:
        raise RuntimeError(
            f"Destination '{_BDC_DESTINATION}' is missing OAuth2 credentials. "
            "Ensure tokenServiceURL, clientId, and clientSecret are configured."
        )

    _cc = (client_id, client_secret)
    async with httpx.AsyncClient(timeout=20.0) as http:
        # Step 1: Fetch OAuth2 bearer token
        token_resp = await http.post(
            token_url,
            data={"grant_type": "client_credentials"},
            auth=_cc,
            headers={"Accept": "application/json"},
        )
        token_resp.raise_for_status()
        access_token: str = token_resp.json()["access_token"]

        # Step 2: Execute SQL via Datasphere REST SQL API
        sql_url = dest.url.rstrip("/") + _DWC_SQL_PATH
        sql_resp = await http.post(
            sql_url,
            json={"sql": sql},
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        sql_resp.raise_for_status()
        return sql_resp.json()


def _rows_to_dicts(result: dict) -> list[dict]:
    """
    Convert Datasphere REST SQL response format to a list of dicts.

    Datasphere returns:
      {"rows": [[v1, v2, ...], ...], "columns": [{"name": "col1"}, {"name": "col2"}, ...]}

    We normalise to:
      [{"col1": v1, "col2": v2, ...}, ...]

    Also handles legacy OData-style {"value": [...]} for forward compatibility.
    """
    # Datasphere REST SQL format
    if "rows" in result and "columns" in result:
        cols = [c["name"] for c in result["columns"]]
        return [dict(zip(cols, row)) for row in result.get("rows", [])]
    # OData-style fallback (legacy / future endpoint variants)
    return result.get("value") or result.get("results") or []


# ---------------------------------------------------------------------------
# Three targeted queries
# ---------------------------------------------------------------------------

async def _query_demand_history(material: str, plant: str, date_from: str, date_to: str) -> list[dict]:
    """
    Fetch monthly planned independent requirement (demand) history from BDC analytics.
    Data product: sap.bdc.s4.analytics:dataProduct:PIRHistory:v1
    """
    sql = (
        f'SELECT "CalYear", "CalMonth", "Material", "Plant", '
        f'"PlannedQuantity", "BaseUnit" '
        f'FROM "sap.bdc.s4.analytics:dataProduct:PIRHistory:v1"."PIRHistoryMonthly" '
        f'WHERE "Material" = \'{material}\' '
        f'AND "Plant" = \'{plant}\' '
        f'AND "CalendarDate" BETWEEN \'{date_from}\' AND \'{date_to}\' '
        f'ORDER BY "CalYear" DESC, "CalMonth" DESC '
        f'LIMIT 24'
    )
    result = await _call_dpquery(sql)
    return _rows_to_dicts(result)


async def _query_production_order_history(material: str, plant: str, date_from: str, date_to: str) -> list[dict]:
    """
    Fetch historical planned order creation/deletion events from BDC analytics.
    Data product: sap.bdc.s4.analytics:dataProduct:ProductionOrderHistory:v1
    """
    sql = (
        f'SELECT "OrderID", "Material", "Plant", "OrderType", '
        f'"TotalQuantity", "ScheduledStartDate", "SystemStatus" '
        f'FROM "sap.bdc.s4.analytics:dataProduct:ProductionOrderHistory:v1"."ProductionOrderFact" '
        f'WHERE "Material" = \'{material}\' '
        f'AND "Plant" = \'{plant}\' '
        f'AND "ScheduledStartDate" BETWEEN \'{date_from}\' AND \'{date_to}\' '
        f'ORDER BY "ScheduledStartDate" DESC '
        f'LIMIT 50'
    )
    result = await _call_dpquery(sql)
    return _rows_to_dicts(result)


async def _query_material_master_change_log(material: str, plant: str) -> list[dict]:
    """
    Fetch recent MRP-relevant master data changes (MRP type, lot size, horizon).
    Data product: sap.bdc.s4.analytics:dataProduct:MaterialMasterChanges:v1
    """
    sql = (
        f'SELECT "Material", "Plant", "FieldName", '
        f'"OldValue", "NewValue", "ChangedAt", "ChangedBy" '
        f'FROM "sap.bdc.s4.analytics:dataProduct:MaterialMasterChanges:v1"."MRPParameterChanges" '
        f'WHERE "Material" = \'{material}\' '
        f'AND "Plant" = \'{plant}\' '
        f'ORDER BY "ChangedAt" DESC '
        f'LIMIT 20'
    )
    result = await _call_dpquery(sql)
    return _rows_to_dicts(result)


# ---------------------------------------------------------------------------
# Public interface — called from evidence/collector.py
# ---------------------------------------------------------------------------

async def get_bdc_supply_chain_analytics(
    material: str,
    plant: str,
    date_from: str,
    date_to: str,
) -> dict:
    """
    Fetch BDC historical analytics for a material/plant pair.

    Returns::

        {"status": "AVAILABLE", "data": {
            "demand_history": [...],
            "production_order_history": [...],
            "material_master_changes": [...],
            "summary": {
                "demand_months_available": int,
                "historical_orders_count": int,
                "recent_mrp_changes": int,
            }
        }}

    or::

        {"status": "MISSING_DATA", "guidance": "<manual investigation text>"}

    when BDC is unreachable or not configured.
    """
    is_testing = os.environ.get("IBD_TESTING") == "1"

    try:
        demand, prod_orders, changes = [], [], []

        try:
            demand = await _query_demand_history(material, plant, date_from, date_to)
        except Exception as exc:
            logger.debug("BDC demand history query failed: %s", exc)

        try:
            prod_orders = await _query_production_order_history(material, plant, date_from, date_to)
        except Exception as exc:
            logger.debug("BDC production order history query failed: %s", exc)

        try:
            changes = await _query_material_master_change_log(material, plant)
        except Exception as exc:
            logger.debug("BDC material master change log query failed: %s", exc)

        # If every sub-query failed, treat as unavailable
        if not demand and not prod_orders and not changes:
            return {
                "status": "MISSING_DATA",
                "reason": (
                    f"SAP Business Data Cloud (BDC) / Datasphere is not connected to USCIA. "
                    f"BTP Destination '{_BDC_DESTINATION}' is either not configured on this "
                    "subaccount, or the SAP Datasphere tenant has not been provisioned. "
                    "BDC historical analytics are a Phase 2 integration item — "
                    "the BTP Destination and Datasphere tenant must be set up by your "
                    "SAP Basis / BTP Admin team before this data becomes available."
                ),
                "what_was_expected": (
                    f"Three types of historical analytics for material {material} / plant {plant}: "
                    "(1) Demand history — month-by-month planned independent requirements (PIR) "
                    "trends to detect demand spikes driving the planning gap. "
                    "(2) Production order history — has this material/plant run production before, "
                    "and how regularly? Detects 'never been produced' scenarios. "
                    "(3) Material master change log — did MRP type, planning horizon, or lot sizing "
                    f"procedure change recently (within last 90 days)? This is HIGH diagnostic value "
                    "— MRP type changes directly explain why planning suddenly stopped working."
                ),
                "manual_investigation": (
                    "RIGHT NOW in S/4HANA: "
                    f"(1) Demand: Run MD04 or MD07 for material {material}, plant {plant} — "
                    "look at the PIR (PlIndRqmt) lines and check if quantities changed recently. "
                    f"(2) Production history: Run CO26 (Order Information System) for material "
                    f"{material}, plant {plant} — check if production orders exist at all. "
                    f"(3) MRP type changes: Run MM03 → change documents, or use transaction "
                    f"RMMDDIBE / SE16 on table CDHDR/CDPOS filtering on MARA/MARC for "
                    f"material {material} — look for DISGR (MRP type) field changes in last 90 days."
                ),
            }

        return {
            "status": "AVAILABLE",
            "data": {
                "demand_history": demand,
                "production_order_history": prod_orders,
                "material_master_changes": changes,
                "summary": {
                    "demand_months_available": len(demand),
                    "historical_orders_count": len(prod_orders),
                    "recent_mrp_changes": len(changes),
                },
            },
        }

    except Exception as exc:
        logger.warning(
            "BDC analytics unavailable — material=%s, plant=%s, error=%s",
            material, plant, exc,
        )
        if is_testing:
            logger.debug("BDC: IBD_TESTING mode — returning MISSING_DATA without retry")
        return {
            "status": "MISSING_DATA",
            "reason": (
                f"SAP Business Data Cloud (BDC) / Datasphere connection failed. "
                f"Error: {exc}. "
                f"BTP Destination '{_BDC_DESTINATION}' must be configured as "
                "OAuth2ClientCredentials pointing to your SAP Datasphere tenant URL. "
                "This is a Phase 2 integration item — contact your SAP Basis / BTP Admin team."
            ),
            "what_was_expected": (
                f"Historical analytics for material {material} / plant {plant}: "
                "demand history trends (PIR month-by-month), production order history "
                "(has this ever been produced?), and material master change log "
                "(MRP type / planning parameter changes in last 90 days — HIGH diagnostic value)."
            ),
            "manual_investigation": (
                "RIGHT NOW in S/4HANA: "
                f"(1) Demand trends: MD04 / MD07 for {material} / {plant} — check PIR lines. "
                f"(2) Production history: CO26 for {material} / {plant}. "
                f"(3) MRP type changes: MM03 change documents, or SE16 on CDHDR/CDPOS "
                f"filtering on MARC for material {material} — field DISGR (MRP type) "
                "changed in last 90 days is the key diagnostic signal."
            ),
        }
