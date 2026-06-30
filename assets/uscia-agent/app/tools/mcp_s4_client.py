"""
MCP client for the s4-mcp-server (cc3-708.cfapps.us10.hana.ondemand.com).

Wraps the execute_odata_query tool exposed by the FastMCP Streamable HTTP server.
Used by DSC-specific tool wrappers as a drop-in replacement for direct s4hana_client calls.

Configuration:
  S4_MCP_SERVER_URL — CF URL of cc3-708 (set in uscia-agent manifest.yml)
  Falls back gracefully to MISSING_DATA if the MCP server is unreachable.
"""
from __future__ import annotations
import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_S4_MCP_URL = os.environ.get(
    "S4_MCP_SERVER_URL",
    "https://cc3-708.cfapps.us10.hana.ondemand.com/mcp",
)

# Singleton client — created lazily on first use
_client = None


async def _get_client():
    global _client
    if _client is not None:
        return _client
    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client
        _client = (ClientSession, streamablehttp_client)
        return _client
    except Exception as exc:
        logger.warning("mcp client import failed: %s", exc)
        return None


async def execute_odata_query(
    query_string: str,
    version: str = "v2",
) -> dict[str, Any]:
    """
    Call execute_odata_query on the s4-mcp-server and return parsed result.

    query_string format:
      v2: "SERVICE_NAME/EntitySet?$filter=...&$select=...&$top=1"
      v4: "api_service/srvd_a2x/sap/service/0001/Entity?$filter=..."

    Returns dict with:
      {"status": "AVAILABLE", "data": <parsed result>}
      {"status": "MISSING_DATA", "reason": "..."}
    """
    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        async with streamablehttp_client(_S4_MCP_URL) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "execute_odata_query",
                    {"query_string": query_string, "version": version},
                )
                # FastMCP returns content as list of TextContent
                if result.content:
                    raw = result.content[0].text if hasattr(result.content[0], 'text') else str(result.content[0])
                    # Result is CSV for GET — parse back to dict structure
                    # The s4-mcp-server returns CSV; we need to detect errors
                    if raw.startswith('{"error"'):
                        err = json.loads(raw)
                        return {"status": "MISSING_DATA", "reason": str(err)}
                    return {"status": "AVAILABLE", "data": raw}
                return {"status": "MISSING_DATA", "reason": "Empty response from MCP server"}

    except Exception as exc:
        logger.warning("s4-mcp-server call failed [%s]: %s", query_string[:80], exc)
        return {"status": "MISSING_DATA", "reason": str(exc)}


async def execute_odata_query_json(
    query_string: str,
    version: str = "v2",
) -> dict[str, Any]:
    """
    Same as execute_odata_query but parses CSV result back into
    {"value": [...]} dict format matching direct OData responses.
    """
    result = await execute_odata_query(query_string, version)
    if result["status"] != "AVAILABLE":
        return result

    raw = result["data"]
    try:
        # Try JSON first (error responses, metadata)
        return {"status": "AVAILABLE", "data": json.loads(raw)}
    except (json.JSONDecodeError, TypeError):
        pass

    # Parse CSV format: first line = headers, rest = rows
    lines = [l for l in raw.strip().split("\n") if l.strip()]
    if not lines:
        return {"status": "AVAILABLE", "data": {"value": []}}

    # Strip count header if present (e.g. "Count: 5")
    if lines[0].startswith("Count:"):
        lines = lines[1:]

    if not lines:
        return {"status": "AVAILABLE", "data": {"value": []}}

    headers = [h.strip() for h in lines[0].split(",")]
    rows = []
    for line in lines[1:]:
        if not line.strip():
            continue
        vals = [v.strip() for v in line.split(",")]
        # Pad if fewer values than headers
        while len(vals) < len(headers):
            vals.append("")
        rows.append(dict(zip(headers, vals)))

    return {"status": "AVAILABLE", "data": {"value": rows}}
