# S4 MCP Server - Claude Code Instructions

## Project Overview

MCP Server for SAP S/4HANA OData and SQL access via Streamable HTTP, built on FastMCP.
Extracted from the monolithic sap-mcp-server. Structure follows ecc-mcp-server as template.

## Running

```bash
uv run src/server.py          # Starts on http://localhost:8080/mcp
PORT=9090 uv run src/server.py # Custom port
```

Credentials are loaded from `.env` (see `.env.example`).

## Project Structure

- `src/server.py` - FastMCP server, tool definitions (5 tools registered via @mcp.tool)
- `src/utils.py` - ODataMetadataParser for $metadata XML parsing, convert_to_csv for response formatting
- `src/clients/s4_odata_client.py` - OData client singleton, basic auth, GET/POST/PUT/PATCH/DELETE, metadata caching, F4 value helpers
- `src/clients/s4_sql_client.py` - HANA SQL client, supports direct connection or BTP Destination (Cloud Connector tunnel)
- `src/clients/btp_service.py` - BTP Destination + Connectivity Service integration, VCAP_SERVICES parsing, token caching
- `src/clients/sql_tunnel.py` - Local TCP tunnel subprocess for routing hdbcli through Cloud Connector SOCKS5
- `src/clients/cloud_connector_socket.py` - SOCKS5 socket with SAP custom auth method 0x80
- `manifest.yml`, `Procfile`, `requirements.txt`, `runtime.txt` - Cloud Foundry deployment

## Architecture Decisions

- **Transport**: Streamable HTTP only (no STDIO). Endpoint: `/mcp`
- **Auth**: Basic auth for OData (direct or from BTP Destination). SQL supports direct or BTP Destination (Cloud Connector).
- **No IDP/SAML**: Stripped from the original sap-mcp-server for simplicity.
- **BTP Destination for OData**: HTTP destinations via Cloud Connector. Uses Connectivity Service HTTP proxy with Bearer token + Location ID headers. Custom HTTPAdapter (`_CCProxyAdapter`) injects proxy auth for both HTTP and HTTPS CONNECT.
- **BTP Destination for SQL**: TCP destinations via Cloud Connector. Uses local TCP tunnel subprocess (like ecc-mcp-server RFC tunnel) because hdbcli has no native SOCKS5 support. Config from VCAP_SERVICES (destination + connectivity service bindings).
- **Direct tool registration**: Tools registered via `@mcp.tool` decorator (no dynamic tool_config system)
- **SQL optional**: If `hdbcli` is not installed, the SQL tool is simply not registered
- **Singleton clients**: `s4_odata_client = S4ODataClient()` and `s4_sql_client = S4SQLClient()` at module level
- **Metadata caching**: $metadata XML cached to `metadata/` directory to avoid repeated HTTP requests
- **No tracking/benchmarking**: Removed the API call tracking system from sap-mcp-server

## Code Conventions

- Python >= 3.13, managed with `uv`
- Logging via `logging` module, logger name: `s4-mcp-server`
- Imports: `from clients.s4_odata_client import s4_odata_client` (relative to `src/`)
- Environment variables prefixed with `S4_ODATA_` for OData, `S4_SQL_` for HANA SQL

## Environment Variables

OData direct: `S4_ODATA_HOST`, `S4_ODATA_USER`, `S4_ODATA_PASSWORD`, `S4_ODATA_CLIENT`
OData destination: `S4_ODATA_DESTINATION` (+ connectivity/destination service bindings, auth from destination or env vars)
Optional (SQL direct): `S4_SQL_HOST`, `S4_SQL_PORT`, `S4_SQL_USER`, `S4_SQL_PASSWORD`
Optional (SQL destination): `S4_SQL_DESTINATION`, `S4_SQL_USER`, `S4_SQL_PASSWORD` (+ connectivity/destination service bindings)
Optional: `PORT` (default 8080), `S4_DEBUG` (verbose logging for BTP/tunnel/CC/OData proxy)

## Testing

No test framework set up. Test manually:
```bash
uv run src/server.py  # Start server, then use MCP client or FastMCP Client to call tools
```

## Deployment

Cloud Foundry: `cf push` (uses `requirements.txt` + `runtime.txt`, not `pyproject.toml`)

## Do NOT

- Add `sys.path.insert()` hacks -- use proper relative imports from `src/`
- Add `.env` to git -- credentials stay local
- Add IDP/SAML code -- this will be handled via BTP Destinations later
