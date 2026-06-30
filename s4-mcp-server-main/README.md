# S4 MCP Server

MCP Server for SAP S/4HANA OData and SQL access via Streamable HTTP. Built on [FastMCP](https://github.com/jlowin/fastmcp).

## Tools

| Tool | Description |
|------|------------|
| `execute_odata_query` | Executes OData CRUD operations (GET returns CSV, write operations return JSON) |
| `get_entity_metadata` | Fetches and summarizes OData service metadata optimized for LLM consumption |
| `get_field_values` | Fetches dropdown/value list values from SAP OData entities |
| `discover_sap_services` | Discovers available SAP services from the Gateway Service Catalog |
| `execute_sql_query` | Executes SQL queries against SAP HANA (optional, requires hdbcli) |

## Prerequisites

- Python >= 3.13
- [uv](https://docs.astral.sh/uv/)

## Local Setup

```bash
# Create .env from template and fill in credentials
cp .env.example .env

# Install dependencies
uv sync

# Start server
uv run src/server.py
```

Server runs on `http://localhost:8080/mcp` (Streamable HTTP).

## Environment Variables

Copy `.env.example` to `.env` and fill in the values:

```bash
cp .env.example .env
```

### OData Connection (required)

Two modes are supported: direct connection or via BTP Destination (Cloud Connector).

**Option A: Direct Connection**

| Variable | Description | Example |
|----------|------------|---------|
| `S4_ODATA_HOST` | SAP S/4HANA host incl. port | `my-s4.sap:44301` |
| `S4_ODATA_USER` | SAP user for OData access | `ODATA_USER` |
| `S4_ODATA_PASSWORD` | Password for OData user | |
| `S4_ODATA_CLIENT` | SAP client number | `100` |

**Option B: BTP Destination (Cloud Connector)**

| Variable | Description | Example |
|----------|------------|---------|
| `S4_ODATA_DESTINATION` | BTP Destination name (HTTP, OnPremise) | `my-s4-odata` |
| `S4_ODATA_USER` | Fallback SAP user (if destination has NoAuthentication) | `ODATA_USER` |
| `S4_ODATA_PASSWORD` | Fallback password | |
| `S4_ODATA_CLIENT` | Fallback client (if destination has no sap-client property) | `100` |

Destination mode requires `connectivity` and `destination` service instances bound to the app (see `manifest.yml`). The BTP destination must be Type=HTTP, ProxyType=OnPremise. Auth credentials and sap-client can be configured in the destination itself (BasicAuthentication) or via env vars as fallback. Requests are routed through the Connectivity Service HTTP proxy to the Cloud Connector.

Either Option A (`S4_ODATA_HOST`) or Option B (`S4_ODATA_DESTINATION`) must be set. Without these the server starts but all OData tools return errors.

### HANA SQL Connection (optional)

Two modes are supported: direct connection or via BTP Destination (Cloud Connector).

**Option A: Direct Connection**

| Variable | Description | Example |
|----------|------------|---------|
| `S4_SQL_HOST` | HANA database host | `hanadb.sap` |
| `S4_SQL_PORT` | HANA SQL port | `30641` |
| `S4_SQL_USER` | HANA database user | `DBADMIN` |
| `S4_SQL_PASSWORD` | Password for HANA user | |

**Option B: BTP Destination (Cloud Connector)**

| Variable | Description | Example |
|----------|------------|---------|
| `S4_SQL_DESTINATION` | BTP Destination name (TCP, OnPremise) | `vhryvhb4db01` |
| `S4_SQL_USER` | HANA database user | `DBADMIN` |
| `S4_SQL_PASSWORD` | Password for HANA user | |

Destination mode requires `connectivity` and `destination` service instances bound to the app (see `manifest.yml`). Host, port, and Cloud Connector Location ID are resolved automatically from the destination config. The server starts a local TCP tunnel subprocess that routes hdbcli traffic through the Cloud Connector SOCKS5 proxy.

Either Option A (`S4_SQL_HOST` + `S4_SQL_PORT`) or Option B (`S4_SQL_DESTINATION`) plus `S4_SQL_USER` + `S4_SQL_PASSWORD` must be set. If none are configured, the `execute_sql_query` tool is not registered.

### Debug Logging

| Variable | Description | Default |
|----------|------------|---------|
| `S4_DEBUG` | Enable debug logs for BTP services, Cloud Connector, SQL tunnel | `false` |

### Server

| Variable | Description | Default |
|----------|------------|---------|
| `PORT` | HTTP server port | `8080` |

## Cloud Foundry Deployment

```bash
cf login -a https://api.cf.<landscape>.hana.ondemand.com
cf push
```

### BTP Destination + Cloud Connector Setup (OData)

To connect to an on-premise S/4HANA system via Cloud Connector, you need three things configured correctly:

**1. Cloud Connector: System Mapping**

In the Cloud Connector admin UI (Access Control > Cloud To On-Premise):

| Field | Value | Example |
|-------|-------|---------|
| Back-end Type | ABAP System | |
| Protocol | HTTPS | |
| Internal Host | Real hostname of the SAP system | `cc3-708.devsys.net.sap` |
| Internal Port | HTTPS port of the SAP system | `443` |
| Virtual Host | Same as internal host (or custom) | `cc3-708.devsys.net.sap` |
| Virtual Port | Same as internal port | `443` |
| Principal Type | None | |
| Host in Request Header | Use Virtual Host | |

Add a resource under the system mapping:

| Field | Value |
|-------|-------|
| URL Path | `/` |
| Access Policy | Path and All Sub-Paths |

**2. BTP Destination**

In the BTP Cockpit (Connectivity > Destinations):

| Field | Value | Notes |
|-------|-------|-------|
| Name | e.g. `cc3-708` | Referenced by `S4_ODATA_DESTINATION` env var |
| Type | HTTP | |
| URL | `http://cc3-708.devsys.net.sap:443` | Must use `http://` (BTP enforces this for OnPremise). Port must match CC virtual port. |
| Proxy Type | OnPremise | |
| Authentication | BasicAuthentication | |
| User | SAP API user | e.g. `API_COM_NR_0395` |
| Password | SAP API password | |
| Location ID | *(empty or matching CC Location ID)* | Only needed if multiple Cloud Connectors |

Additional Properties:

| Key | Value |
|-----|-------|
| `sap-client` | SAP client number, e.g. `708` |

**Key rule**: BTP enforces `http://` for OnPremise destinations. The Cloud Connector handles the protocol translation to HTTPS for the backend. The port in the destination URL must match the virtual port in the CC system mapping (e.g. `http://host:443` maps to CC virtual host on port 443 with HTTPS protocol).

**3. manifest.yml**

```yaml
applications:
  - name: my-mcp-server
    memory: 256MB
    disk_quota: 1G
    instances: 1
    buildpacks:
      - python_buildpack
    stack: cflinuxfs4
    health-check-type: process
    command: python src/server.py
    services:
      - my-connectivity-service    # connectivity service instance
      - my-destination-service     # destination service instance
    env:
      PYTHONUNBUFFERED: true
      S4_ODATA_DESTINATION: cc3-708  # must match destination name
```

### BTP Destination + Cloud Connector Setup (HANA SQL)

To connect to an on-premise HANA database via Cloud Connector, you need three things configured correctly:

**1. Cloud Connector: System Mapping**

In the Cloud Connector admin UI (Access Control > Cloud To On-Premise):

| Field | Value | Example |
|-------|-------|---------|
| Back-end Type | SAP HANA | |
| Protocol | TCP | |
| Internal Host | Real hostname of the HANA database | `vhryvhb4db01` |
| Internal Port | HANA SQL port | `30641` |
| Virtual Host | Same as internal host (or custom) | `vhryvhb4db01` |
| Virtual Port | Same as internal port | `30641` |

No resource/path mapping needed for TCP connections.

**2. BTP Destination**

In the BTP Cockpit (Connectivity > Destinations):

| Field | Value | Notes |
|-------|-------|-------|
| Name | e.g. `vhryvhb4db01` | Referenced by `S4_SQL_DESTINATION` env var |
| Type | TCP | |
| Address | `vhryvhb4db01:30641` | host:port matching CC virtual host/port |
| Proxy Type | OnPremise | |
| Authentication | NoAuthentication | DB credentials via env vars, not destination |
| Location ID | *(empty or matching CC Location ID)* | e.g. `QMAgent` if multiple Cloud Connectors |

**Key difference from OData**: SQL destinations use Type=TCP (not HTTP). Authentication is NoAuthentication because HANA credentials are passed directly by hdbcli via `S4_SQL_USER`/`S4_SQL_PASSWORD` env vars. The server starts a local TCP tunnel that routes hdbcli traffic through the Connectivity Service SOCKS5 proxy to the Cloud Connector.

**3. manifest.yml**

```yaml
applications:
  - name: my-mcp-server
    # ...
    services:
      - my-connectivity-service    # connectivity service instance
      - my-destination-service     # destination service instance
    env:
      PYTHONUNBUFFERED: true
      S4_ODATA_DESTINATION: my-odata-dest
      S4_SQL_DESTINATION: vhryvhb4db01  # must match destination name
      S4_SQL_USER: DBADMIN
      S4_SQL_PASSWORD: my-password
```

## MCP Client Configuration

### Cline (VS Code)

Add to Cline MCP settings (`cline_mcp_settings.json`):

```json
{
  "mcpServers": {
    "s4-mcp-server": {
      "url": "http://localhost:8080/mcp",
      "transportType": "streamable-http"
    }
  }
}
```

### Claude Code

```bash
claude mcp add s4-mcp-server --transport http http://localhost:8080/mcp
```

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "s4-mcp-server": {
      "url": "http://localhost:8080/mcp"
    }
  }
}
```

## Project Structure

```
src/
  server.py                    # FastMCP server (Streamable HTTP), tool definitions
  utils.py                     # ODataMetadataParser, convert_to_csv
  clients/
    s4_odata_client.py         # SAP S/4HANA OData client (basic auth)
    s4_sql_client.py           # SAP HANA SQL client (direct or via BTP Destination)
    btp_service.py             # BTP Destination + Connectivity Service integration
    sql_tunnel.py              # TCP tunnel subprocess for Cloud Connector
    cloud_connector_socket.py  # SOCKS5 socket with SAP custom auth (0x80)
```
