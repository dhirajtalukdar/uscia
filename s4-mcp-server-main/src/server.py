import json
import logging
import os
import threading
import time

import requests
from fastmcp import FastMCP
from clients.s4_odata_client import s4_odata_client
from utils import convert_to_csv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("s4-mcp-server")

# SQL client: enabled via direct connection (S4_SQL_HOST/PORT) or BTP destination
_has_sql_direct = all([os.getenv("S4_SQL_HOST"), os.getenv("S4_SQL_PORT")])
_has_sql_dest = bool(os.getenv("S4_SQL_DESTINATION"))
_has_sql = (_has_sql_direct or _has_sql_dest) and all([
    os.getenv("S4_SQL_USER"),
    os.getenv("S4_SQL_PASSWORD"),
])

s4_sql_client = None
if _has_sql:
    try:
        from clients.s4_sql_client import s4_sql_client
    except ImportError:
        _has_sql = False
        print("Warning: hdbcli not installed, SQL tools disabled")

mcp = FastMCP(
    name="S4 MCP Server",
    instructions="""SAP S/4HANA system access via OData and SQL.

Workflow:
1. Use get_entity_metadata to discover entities and fields of an OData service.
2. Use get_field_values to get dropdown/value list values for fields.
3. Use execute_odata_query for CRUD operations.
4. Use execute_sql_query for direct HANA SQL queries (if enabled).

OData conventions:
- Use specific OData services like SD_, FI_, MM_ before general API like API_ or custom Z_ services.
- Use only field values where you have proof (e.g. via ValueHelper) for your assumptions.
- For write operations, always fetch CSRF token first (handled automatically).
- Customer/vendor numbers are 10-digit with leading zeros (e.g. "0000001000").
""",
)


@mcp.tool
def execute_odata_query(query_string: str, data: str = "", method: str = "GET", version: str = "v2"):
    """
    Executes an OData query against the SAP S/4HANA system with full CRUD support.
    There is NO allowlist or path restriction -- any OData service path is accepted.

    Returns CSV format for successful GET operations, structured format for write operations and errors.

    Args:
        query_string: The OData path + query parameters. This is appended to the base URL.
            v2 base: /sap/opu/odata/sap/{query_string}
            v4 base: /sap/opu/odata4/sap/{query_string}
        data: JSON string for write operations (POST/PUT/PATCH). Empty for GET/DELETE.
        method: HTTP method ("GET", "POST", "PUT", "PATCH", "DELETE"). Default: "GET"
        version: "v2" (default) or "v4". Controls the base URL path.

    URL construction:
        v2: {host}/sap/opu/odata/sap/{query_string}
        v4: {host}/sap/opu/odata4/sap/{query_string}
        The query_string is everything after /sap/opu/odata/sap/ (v2) or /sap/opu/odata4/sap/ (v4).

    v2 query_string format:
        "SERVICE_NAME/EntitySet?$select=Field1,Field2&$filter=Field eq 'Value'&$top=10"

    v4 query_string format (longer paths with service descriptor):
        "api_measuringpoint/srvd_a2x/sap/measuringpoint/0001/MeasuringPoint?$top=50"
        "api_business_partner/srvd_a2x/sap/businesspartner/0001/A_BusinessPartner?$top=10"

    Returns:
        GET: CSV format with count header. Write operations: JSON response.

    Examples:
        # v2 read
        execute_odata_query("API_PURCHASEORDER_PROCESS_SRV/A_PurchaseOrder?$top=10")

        # v4 read (note the longer service descriptor path)
        execute_odata_query("api_measuringpoint/srvd_a2x/sap/measuringpoint/0001/MeasuringPoint?$top=50", version="v4")
        execute_odata_query("api_salesorder/srvd_a2x/sap/salesorder/0001/SalesOrder?$top=10", version="v4")

        # v2 write
        execute_odata_query("API_SALES_ORDER_SRV/A_SalesOrder", '{"SalesOrderType": "OR", "SoldToParty": "17100003"}', "POST")
    """
    if method.upper() == "GET":
        if "$inlinecount" not in query_string and version == "v2":
            query_string += "&$inlinecount=allpages" if "?" in query_string else "?$inlinecount=allpages"
        elif "$count" not in query_string and version == "v4":
            query_string += "&$count=true" if "?" in query_string else "?$count=true"

        response = s4_odata_client.execute_raw_query(query_string, version=version)

        if isinstance(response, dict) and "error" in response:
            return response

        csv_result = convert_to_csv(response)
        return csv_result

    else:
        try:
            if isinstance(data, dict):
                parsed_data = data
            elif data:
                parsed_data = json.loads(data)
            else:
                parsed_data = {}
            response = s4_odata_client.execute_raw_post_query(
                query_string, parsed_data, method, version
            )
            return response
        except (json.JSONDecodeError, TypeError) as e:
            return {"error": f"Invalid JSON data: {str(e)}"}


@mcp.tool
def get_entity_metadata(service_name: str, query: str = "", version: str = "v2"):
    """
    Fetches and summarizes OData service metadata optimized for LLM consumption.

    Auto-fallback: if query yields no matching entities, returns ALL entities instead.

    Args:
        service_name: The OData service name or path.
            v2: "API_SALES_ORDER_SRV"
            v4: "api_measuringpoint/srvd_a2x/sap/measuringpoint/0001"
                "api_salesorder/srvd_a2x/sap/salesorder/0001"
        query: Optional filter for entity/field names (case-insensitive). Use simple business terms.
               Good: "SalesOrder", "Customer", "Material"
               Avoid: "A_SalesOrder", "API_" (technical prefixes miss relevant entities)
        version: "v2" (default) or "v4"

    Returns:
        Simplified metadata with entities, keys, fields, labels, value lists, navigation.

    Examples:
        get_entity_metadata('API_SALES_ORDER_SRV', 'customer')
        get_entity_metadata('api_measuringpoint/srvd_a2x/sap/measuringpoint/0001', version='v4')
    """
    return s4_odata_client.get_service_metadata(service_name, query, version)


@mcp.tool
def get_field_values(
    service_name: str,
    entity_name: str,
    key_field: str = "",
    text_field: str = "",
    max_values: int = 50,
    version: str = "v2",
):
    """
    Fetches actual dropdown/value list values from SAP OData entities.

    This tool complements get_entity_metadata by providing the actual values for fields that have
    value lists (dropdowns). When metadata shows a field has "values_from": "SomeEntity",
    use this tool to get the actual key-value pairs.

    IMPORTANT - External F4 Value Helpers (OData v4):
        For external F4 value helpers, the metadata parser automatically constructs the complete
        service path including matrix parameters (ps and va) required by SAP Gateway.

        The service_path in the metadata already includes:
        - Parent service base (first segment of parent service)
        - F4 service path with version
        - Matrix parameters for parent service context (;ps='...')
        - Matrix parameters for value annotation (;va='...')

        Example from metadata:
        {
            "vh": {
                "type": "external",
                "service_path": "ui_subscrpnmassprocg_manage/srvd_f4/sap/i_service/0001;ps='srvd-ui_subscrpnmassprocg_manage-0001';va='...'",
                "entity": "I_ServiceVH"
            }
        }

        Simply use the service_path directly - no manual path construction needed!

    Args:
        service_name: The name of the OData service (e.g., 'MM_PUR_PO_MAINT_V2_SRV')
                     For external F4 in v4: Use service_path from metadata (includes matrix params)
        entity_name: The entity containing the value list (e.g., 'I_GranteeMgmtFundType')
        key_field: The key field name (auto-detected if not provided)
        text_field: The text/description field name (auto-detected if not provided)
        max_values: Maximum number of values to return (default: 50, max: 100)
        version: OData version to use ("v2" or "v4"). Defaults to "v2" for backward compatibility.

    Returns:
        Dictionary containing the actual dropdown values with keys and descriptions:
        {
            "entity_name": "I_GranteeMgmtFundType",
            "key_field": "GranteeMgmtFundType",
            "text_field": "GranteeMgmtFundType_Text",
            "total_values": 15,
            "values": [
                {"key": "01", "text": "Research Grant Fund"},
                {"key": "02", "text": "Education Grant Fund"},
                {"key": "03", "text": "Community Grant Fund"}
            ],
            "truncated": false
        }

    Usage Examples:
        # Internal value helper (v2 or v4)
        get_field_values('MM_PUR_PO_MAINT_V2_SRV', 'I_GranteeMgmtFundType')

        # Internal value helper (v4 with full path)
        get_field_values('ui_subscrpnmassprocg_manage/srvd/sap/ui_subscrpnmassprocg_manage/0001', 'ProductVH', version='v4')

        # External F4 value helper (v4) - use service_path from metadata
        get_field_values("ui_subscrpnmassprocg_manage/srvd_f4/sap/c_sbsmssprocgcontractaccountvh/0001;ps='srvd-ui_subscrpnmassprocg_manage-0001';va='...'", 'C_SbsmssProcgContractAccountVH', version='v4')

        # Specify exact field names if auto-detection fails
        get_field_values('MM_PUR_PO_MAINT_V2_SRV', 'I_CompanyCode', 'CompanyCode', 'CompanyCodeName')

        # Limit results for large value lists
        get_field_values('MM_PUR_PO_MAINT_V2_SRV', 'I_Material', max_values=20)

    Common Use Cases:
        - Get valid values for dropdown fields
        - Validate user input against allowed values
        - Provide suggestions for field values
        - Understand what codes mean (code -> description mapping)
    """
    key_field_param = key_field if key_field else None
    text_field_param = text_field if text_field else None
    max_values = min(max_values, 100)

    return s4_odata_client.get_field_values(
        service_name, entity_name, key_field_param, text_field_param, max_values, version
    )


@mcp.tool
def discover_sap_services(search: str = ""):
    """
    Discover available SAP business services in the S/4HANA system that are exposed via OData.
    This finds SAP-specific services like Purchase Orders, Sales Orders, Materials Management,
    Financial services, etc.

    Alway select services with priority="HIGH" first, then "MEDIUM", then "LOW".

    When multiple services are returned, you MUST choose the service with priority="HIGH" first,
    then "MEDIUM", then "LOW". Services with HIGH priority are the primary business services
    for their respective modules and provide the most comprehensive functionality.

    Note: This does NOT include standard OData APIs or generic web services - only SAP business
    application services registered in the Gateway Service Catalog.

    Args:
        search: Search term for SAP service names/descriptions (case-insensitive)
                Examples: 'purchase', 'sales', 'material', 'financial', 'api'

    Returns:
        Dictionary with discovered SAP services information:
        {
            "found": 12,
            "sap_services": [
                {
                    "name": "MM_PUR_PO_MAINT_V2_SRV",
                    "description": "Purchase Order Maintenance Service",
                    "service_type": "UI",
                    "is_sap_service": true,
                    "version": "2",
                    "service_url": "https://.../sap/opu/odata/sap/MM_PUR_PO_MAINT_V2_SRV",
                    "metadata_url": "https://.../sap/opu/odata/sap/MM_PUR_PO_MAINT_V2_SRV/$metadata",
                    "last_updated": "2023-01-15T10:30:00",
                    "priority": "HIGH",
                    "author": "SAP"
                }
            ],
            "search_term": "purchase"
        }

    Usage Examples:
        discover_sap_services()  # Get all available SAP services
        discover_sap_services("purchase")  # Find purchase-related services
        discover_sap_services("sales")  # Find sales & distribution services
        discover_sap_services("API_")  # Find SAP standard API services
        discover_sap_services("material")  # Find material services

    Common Search Terms:
        - "purchase" - Purchase Order, Procurement services
        - "sales" - Sales Order, Customer services
        - "material" - Material Management, Inventory services
        - "financial" - Finance, Accounting services
        - "API_" - Standard SAP API services
        - "ZC_" - Custom CDS-based services
        - "MM_" - Materials Management module
        - "SD_" - Sales & Distribution module
        - "FI_" - Financial Accounting module
    """
    search_param = search if search else None
    return s4_odata_client.discover_sap_services(search_param)


if _has_sql:
    @mcp.tool
    def execute_sql_query(sql: str):
        """
        Executes a SQL query against the SAP HANA database.

        Args:
            sql: The SQL query string to execute.

        Returns:
            A list of dictionaries, where each dictionary represents a row from the result set.

            Returns an error dictionary if the query fails.
        """
        result = s4_sql_client.execute_query(sql)

        if isinstance(result, dict) and "error" in result:
            return result

        return result


def _check_odata():
    """Startup health check for OData connectivity."""
    def _test():
        try:
            print(f"[STARTUP] OData base_url: {s4_odata_client.base_url}")
            if s4_odata_client._destination_mode:
                print(f"[STARTUP] OData proxy: {s4_odata_client._proxy_url}")

            t0 = time.time()
            url = f"{s4_odata_client.base_url}/API_SALES_ORDER_SRV/"
            response = s4_odata_client.session.get(
                url, headers={"Accept": "application/json"}, timeout=30,
            )
            elapsed = time.time() - t0
            status = response.status_code
            body = response.text[:500].lower()

            if status == 200:
                print(f"[STARTUP] OData OK ({elapsed:.1f}s)")
            elif status == 401 or "anmeldung fehlgeschlagen" in body or "logon failed" in body:
                print(f"[STARTUP] OData FAILED ({elapsed:.1f}s): Authentication failed (401)")
                print(f"  -> Check user/password in BTP destination or S4_ODATA_USER/PASSWORD env vars")
            elif status == 403 and "access denied" in body:
                print(f"[STARTUP] OData FAILED ({elapsed:.1f}s): Access denied by Cloud Connector (403)")
                from urllib.parse import urlparse
                parsed = urlparse(s4_odata_client.base_url or "")
                port = parsed.port or (443 if parsed.scheme == "https" else 80)
                print(f"  -> CC system mapping must match virtual host '{parsed.hostname}' port '{port}'")
            elif status == 403:
                print(f"[STARTUP] OData FAILED ({elapsed:.1f}s): Forbidden (403)")
                print(f"  -> User has no authorization for test service. Check SAP role assignments.")
            elif status == 404:
                print(f"[STARTUP] OData REACHABLE ({elapsed:.1f}s): Test service not found (404)")
                print(f"  -> Connection works but API_SALES_ORDER_SRV is not available on this system")
            elif status == 407:
                print(f"[STARTUP] OData FAILED ({elapsed:.1f}s): Proxy auth required (407)")
                print(f"  -> Check connectivity service binding and token")
            elif status == 503 or "no scc connected" in body:
                print(f"[STARTUP] OData FAILED ({elapsed:.1f}s): Cloud Connector not reachable (503)")
                print(f"  -> Check CC is running and Location ID matches")
            else:
                print(f"[STARTUP] OData FAILED ({elapsed:.1f}s): HTTP {status}")
                print(f"  -> {response.text[:200]}")
        except requests.exceptions.ProxyError:
            print(f"[STARTUP] OData FAILED: Connectivity proxy not reachable")
            print(f"  -> Check connectivity service binding (VCAP_SERVICES)")
        except requests.exceptions.ConnectionError as e:
            msg = str(e).lower()
            if "nodename nor servname" in msg or "name or service not known" in msg:
                print(f"[STARTUP] OData FAILED: Host not resolvable")
                print(f"  -> Check S4_ODATA_HOST or BTP destination URL")
            else:
                print(f"[STARTUP] OData FAILED: Connection error: {e}")
        except requests.exceptions.Timeout:
            print(f"[STARTUP] OData FAILED: Connection timed out (30s)")
            print(f"  -> Check host/port and Cloud Connector reachability")
        except Exception as e:
            print(f"[STARTUP] OData FAILED: {type(e).__name__}: {e}")

    threading.Thread(target=_test, daemon=True).start()


def _check_sql():
    """Startup health check for SQL connectivity."""
    if not _has_sql or not s4_sql_client:
        return

    def _test():
        try:
            t0 = time.time()
            result = s4_sql_client.execute_query("SELECT 1 FROM DUMMY")
            elapsed = time.time() - t0
            if isinstance(result, dict) and "error" in result:
                _diagnose_sql_error(result, elapsed)
            else:
                print(f"[STARTUP] SQL OK ({elapsed:.1f}s)")
        except Exception as e:
            _diagnose_sql_exception(e)

    threading.Thread(target=_test, daemon=True).start()


def _diagnose_sql_error(result, elapsed):
    error_msg = str(result.get("error", ""))
    combined = error_msg.lower()

    if "authentication failed" in combined or "invalid username or password" in combined:
        print(f"[STARTUP] SQL FAILED ({elapsed:.1f}s): Authentication failed")
        print(f"  -> Check S4_SQL_USER/S4_SQL_PASSWORD")
    elif "connection refused" in combined or "timed out" in combined:
        print(f"[STARTUP] SQL FAILED ({elapsed:.1f}s): Connection refused or timed out")
        print(f"  -> Check S4_SQL_HOST/S4_SQL_PORT or BTP destination host:port")
    else:
        print(f"[STARTUP] SQL FAILED ({elapsed:.1f}s): {error_msg[:200]}")


def _diagnose_sql_exception(e):
    msg = str(e).lower()
    if "network_unreachable" in msg or "0x03" in msg:
        print(f"[STARTUP] SQL FAILED: Cloud Connector not reachable")
        print(f"  -> Check CloudConnectorLocationId in BTP destination")
    elif "forbidden" in msg or "0x02" in msg:
        print(f"[STARTUP] SQL FAILED: Access denied by Cloud Connector")
        print(f"  -> Check CC system mapping for host:port")
    elif "authentication failed" in msg or "invalid username or password" in msg:
        print(f"[STARTUP] SQL FAILED: Authentication failed")
        print(f"  -> Check S4_SQL_USER/S4_SQL_PASSWORD")
    elif "connection refused" in msg or "timed out" in msg:
        print(f"[STARTUP] SQL FAILED: Connection refused or timed out")
        print(f"  -> Check S4_SQL_HOST/S4_SQL_PORT or BTP destination")
    elif "nodename nor servname" in msg or "name or service not known" in msg:
        print(f"[STARTUP] SQL FAILED: Host not resolvable")
        print(f"  -> Check S4_SQL_HOST or BTP destination")
    else:
        print(f"[STARTUP] SQL FAILED: {type(e).__name__}: {e}")


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    sql_mode = "destination" if _has_sql_dest else "direct" if _has_sql_direct else "disabled"
    odata_mode = "destination" if os.getenv("S4_ODATA_DESTINATION") else "direct" if os.getenv("S4_ODATA_HOST") else "disabled"
    print(f"OData: {odata_mode}")
    print(f"SQL tools: {sql_mode if _has_sql else 'disabled'} (S4_SQL_USER/PASSWORD {'set' if _has_sql else 'not set'})")
    _check_odata()
    _check_sql()
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
