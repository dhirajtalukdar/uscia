"""Phase 4 execution dispatcher.

Maps approved RemediationAction objects to MCP tools registered on the SAP
Agent Gateway and invokes them.  This is the single wiring point between the
USCIA orchestrator and the specialist execution agents.

Lifecycle
---------
1. _resolve_approval() in agent.py calls dispatch_approved_actions() with the
   list of approved RemediationAction objects.
2. For each action, _find_tool() searches the live MCP tool list for a tool
   whose name ends with the canonical suffix defined in _ACTION_TO_MCP_TOOL.
3. If found, _invoke_tool() calls the tool and returns the response string.
4. Each action produces one DispatchResult capturing status + outcome.

Graceful degradation
--------------------
* If no tool is registered for an action_type (TOOL_NOT_REGISTERED), the
  dispatcher returns the fallback manual guidance without raising.
* If the tool call fails (DISPATCH_FAILED), the error is logged and captured
  in DispatchResult.error; the caller receives a degraded-but-complete summary.
* All exceptions are caught here – this module never propagates to the user.

Tool name matching
------------------
enhance_tool_name() in util.py produces names like:
    "<resource>_<version>__<tool_name>"
e.g. "bgrfc-agent_v1__restart_bgrfc_queue"

We match by suffix so the Agent Gateway server name is irrelevant to the
dispatcher.  Example: _ACTION_TO_MCP_TOOL["RESTART_BGRFC"] = "restart_bgrfc_queue"
matches any tool whose enhanced name ends with "__restart_bgrfc_queue".
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_core.tools import StructuredTool
    from evidence.models import RemediationAction

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Action-type → MCP tool name suffix
# ---------------------------------------------------------------------------
# The values are the *bare* tool names as they will be registered on the
# Agent Gateway.  enhance_tool_name() prefixes them with the server slug, so
# we match by suffix (endswith).
_ACTION_TO_MCP_TOOL: dict[str, str] = {
    "RESTART_BGRFC":         "restart_bgrfc_queue",
    "REPROCESS_CPI_MESSAGE": "reprocess_cpi_message",
    "RERUN_PPDS_HEURISTIC":  "rerun_ppds_heuristic",
    "RERUN_MRP_SINGLE_ITEM": "rerun_mrp_single_item",
    "RERUN_IBP_JOB":         "rerun_ibp_planning_job",
}

# Fallback manual guidance shown when the tool is not yet registered.
_ACTION_FALLBACK_GUIDANCE: dict[str, str] = {
    "RESTART_BGRFC":
        "Restart the blocked bgRFC queue entry manually via SM58 or the bgRFC Monitor (SBGRFCMON).",
    "REPROCESS_CPI_MESSAGE":
        "Reprocess the failed CPI/RTI message manually via SXMB_MONI or the Integration Suite "
        "message monitor.",
    "RERUN_PPDS_HEURISTIC":
        "Rerun the PP/DS scheduling heuristic manually via /SAPAPO/RRP3 or the Production "
        "Planning interactive screen.",
    "RERUN_MRP_SINGLE_ITEM":
        "Run single-item MRP for this material/plant manually via MD01N or MD03.",
    "RERUN_IBP_JOB":
        "Trigger the IBP supply planning job manually via the IBP Monitor or Supply Chain "
        "Planning job management.",
}

# Dispatch status codes
DISPATCHED          = "DISPATCHED"
TOOL_NOT_REGISTERED = "TOOL_NOT_REGISTERED"
DISPATCH_FAILED     = "DISPATCH_FAILED"


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class DispatchResult:
    """Outcome of dispatching a single approved action."""
    action_id: str
    action_type: str
    status: str                        # DISPATCHED | TOOL_NOT_REGISTERED | DISPATCH_FAILED
    tool_name: str = ""                # full enhanced tool name (empty if not found)
    tool_response: str = ""            # raw string response from the execution tool
    fallback_guidance: str = ""        # shown to user when tool not registered / failed
    error: str = ""                    # exception message on DISPATCH_FAILED


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_tool(
    action_type: str,
    tools: list["StructuredTool"],
) -> "StructuredTool | None":
    """Return the first tool whose name matches the expected suffix for action_type."""
    suffix = _ACTION_TO_MCP_TOOL.get(action_type)
    if not suffix:
        return None
    # Tools loaded via get_mcp_tools() have enhanced names like "resource_v1__bare_name"
    # Mock tools (mcp-mock.json / IBD_TESTING=1) use the bare name directly.
    for t in tools:
        if t.name == suffix or t.name.endswith(f"__{suffix}"):
            return t
    return None


def _build_tool_kwargs(
    action: "RemediationAction",
) -> dict:
    """Extract relevant parameters from action_params for the tool call.

    We pass the full action_params dict (minus None values) to keep the
    dispatcher decoupled from each tool's exact schema.  The StructuredTool
    will raise a validation error if required fields are missing, which is
    captured in DISPATCH_FAILED.
    """
    params = action.action_params or {}
    return {k: v for k, v in params.items() if v is not None}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def dispatch_approved_actions(
    actions: list["RemediationAction"],
    tools: list["StructuredTool"],
) -> list[DispatchResult]:
    """Dispatch each approved action to its registered MCP tool.

    Args:
        actions: Non-MANUAL_ONLY RemediationAction objects approved by the user.
        tools: Live tool list from get_mcp_tools() (may be empty in pre-Phase-4 builds).

    Returns:
        One DispatchResult per action, in the same order as ``actions``.
    """
    results: list[DispatchResult] = []

    for action in actions:
        action_type = action.action_type
        tool = _find_tool(action_type, tools)

        if tool is None:
            guidance = _ACTION_FALLBACK_GUIDANCE.get(
                action_type,
                f"No automation available for {action_type}. Please action manually.",
            )
            logger.info(
                "dispatcher: tool not registered for action_type=%s action_id=%s",
                action_type, action.action_id,
            )
            results.append(DispatchResult(
                action_id=action.action_id,
                action_type=action_type,
                status=TOOL_NOT_REGISTERED,
                fallback_guidance=guidance,
            ))
            continue

        kwargs = _build_tool_kwargs(action)
        logger.info(
            "dispatcher: invoking tool=%s for action_type=%s action_id=%s kwargs_keys=%s",
            tool.name, action_type, action.action_id, list(kwargs.keys()),
        )
        try:
            response = await tool.arun(kwargs)
            logger.info(
                "dispatcher: tool=%s returned successfully for action_id=%s",
                tool.name, action.action_id,
            )
            results.append(DispatchResult(
                action_id=action.action_id,
                action_type=action_type,
                status=DISPATCHED,
                tool_name=tool.name,
                tool_response=str(response),
            ))
        except Exception as exc:
            logger.exception(
                "dispatcher: tool=%s failed for action_id=%s: %s",
                tool.name, action.action_id, exc,
            )
            guidance = _ACTION_FALLBACK_GUIDANCE.get(
                action_type,
                f"Automated execution failed for {action_type}. Please action manually.",
            )
            results.append(DispatchResult(
                action_id=action.action_id,
                action_type=action_type,
                status=DISPATCH_FAILED,
                tool_name=tool.name,
                fallback_guidance=guidance,
                error=str(exc),
            ))

    return results



def _is_mock_response(tool_response: str) -> bool:
    """Return True when the tool response originates from a mock agent (mcp-mock.json)."""
    try:
        import json as _json
        payload = _json.loads(tool_response)
        return payload.get("mode") == "MOCK_AGENT"
    except Exception:
        return False


def format_dispatch_summary(results: list[DispatchResult]) -> str:
    """Render a human-readable dispatch summary for inclusion in the response."""
    if not results:
        return ""

    lines = ["### Execution Dispatch Summary\n"]
    has_mock = False

    for r in results:
        if r.status == DISPATCHED:
            is_mock = _is_mock_response(r.tool_response)
            if is_mock:
                has_mock = True
            mock_tag = " *(Mock Agent)*" if is_mock else ""
            lines.append(
                f"- \u2705 **`{r.action_type}`** \u2192 dispatched via `{r.tool_name}`{mock_tag}\n"
                f"  Response: {r.tool_response[:300] if r.tool_response else '(empty)'}"
            )
        elif r.status == TOOL_NOT_REGISTERED:
            lines.append(
                f"- \u23f3 **`{r.action_type}`** \u2192 execution agent not yet deployed\n"
                f"  Manual guidance: {r.fallback_guidance}"
            )
        else:  # DISPATCH_FAILED
            lines.append(
                f"- \u274c **`{r.action_type}`** \u2192 dispatch failed (`{r.error}`)\n"
                f"  Manual guidance: {r.fallback_guidance}"
            )

    if has_mock:
        lines.append(
            "\n---\n"
            "> \U0001f504 **Mock Agent Mode** \u2014 Actions above were executed by simulated agents "
            "loaded from `mcp-mock.json`. "
            "Live specialist execution agents will be registered on the SAP Agent Gateway "
            "and activated in **Phase 4**."
        )

    return "\n".join(lines)
