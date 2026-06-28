"""
Tests for the human-approval gate in SampleAgent.

Scenarios covered:
  1. Executable action → gate fires, stream yields require_user_input=True
  2. MANUAL_ONLY action → gate skipped, report delivered immediately
  3. "Yes, proceed" resolves pending approval → approved header + full report
  4. "No, skip" resolves pending approval → declined header + full report
  5. Pending approval expired (TTL) → treated as new query, not as approval
  6. _is_approval_response / _is_positive_approval helpers
  7. _get_pending_approval returns None after expiry
  8. approval_id matches context_id in AgentResult
  9. Approval gate message contains material, plant, root cause, action names
 10. invoke() returns status="input_required" when gate fires
"""
from __future__ import annotations

import asyncio
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from agent import (
    AgentResult,
    PendingApproval,
    SampleAgent,
    _EXECUTABLE_ACTION_TYPES,
    _format_approval_request,
    _is_approval_response,
    _is_positive_approval,
)
from evidence.models import RemediationAction


# ── helpers ────────────────────────────────────────────────────────────────────

def _make_action(action_type: str, rank: int = 1) -> RemediationAction:
    return RemediationAction(
        action_id=f"act-{rank}",
        action_type=action_type,
        action_params={"queue": "APOC_TEST"} if action_type == "RESTART_BGRFC" else {},
        requires_approval=True,
        rank=rank,
    )


def _pending_approval(context_id: str = "ctx-1") -> PendingApproval:
    return PendingApproval(
        context_id=context_id,
        incident_id="inc-001",
        material="FG-1234",
        plant="1000",
        root_cause="BGRFC_QUEUE_BLOCKAGE",
        confidence="HIGH",
        executable_actions=[_make_action("RESTART_BGRFC")],
        full_report="## Full Report\nLine 1.",
        outcome_hint="\n\n---\n*outcome hint*",
    )


# ── unit tests: pure helpers ───────────────────────────────────────────────────

class TestApprovalHelpers(unittest.TestCase):

    def test_is_approval_response_positive_words(self):
        for phrase in ["yes", "yes please", "proceed", "go ahead", "confirm", "ok", "approve"]:
            self.assertTrue(_is_approval_response(phrase), phrase)

    def test_is_approval_response_negative_words(self):
        for phrase in ["no", "no thanks", "skip", "reject", "cancel", "hold", "abort"]:
            self.assertTrue(_is_approval_response(phrase), phrase)

    def test_is_approval_response_unrelated_query(self):
        # A new investigation query should NOT trigger the gate
        self.assertFalse(_is_approval_response("Why is planned order for FG-5678 missing?"))

    def test_is_positive_approval_true(self):
        for phrase in ["yes", "proceed", "ok", "go ahead", "confirm", "approve"]:
            self.assertTrue(_is_positive_approval(phrase), phrase)

    def test_is_positive_approval_false(self):
        for phrase in ["no", "skip", "reject", "cancel", "hold"]:
            self.assertFalse(_is_positive_approval(phrase), phrase)


class TestFormatApprovalRequest(unittest.TestCase):

    def _msg(self):
        return _format_approval_request(
            material="FG-1234",
            plant="1000",
            root_cause="BGRFC_QUEUE_BLOCKAGE",
            confidence="HIGH",
            executable_actions=[_make_action("RESTART_BGRFC")],
        )

    def test_contains_material_and_plant(self):
        msg = self._msg()
        self.assertIn("FG-1234", msg)
        self.assertIn("1000", msg)

    def test_contains_root_cause(self):
        msg = self._msg()
        self.assertIn("BGRFC_QUEUE_BLOCKAGE", msg)

    def test_contains_action_type(self):
        msg = self._msg()
        self.assertIn("RESTART_BGRFC", msg)

    def test_contains_yes_no_options(self):
        msg = self._msg()
        self.assertIn("Yes, proceed", msg)
        self.assertIn("No, skip", msg)

    def test_phase4_notice_present(self):
        msg = self._msg()
        self.assertIn("Phase 4", msg)


# ── SampleAgent unit tests: _get_pending_approval TTL ─────────────────────────

class TestGetPendingApproval(unittest.TestCase):

    def _agent(self):
        with (
            patch("agent.S4Client"),
            patch("agent.IBPClient"),
            patch("agent.InMemorySaver"),
        ):
            return SampleAgent()

    def test_returns_pending_approval_within_ttl(self):
        agent = self._agent()
        pa = _pending_approval("ctx-ttl")
        agent._pending_approvals["ctx-ttl"] = pa
        result = agent._get_pending_approval("ctx-ttl")
        self.assertIs(result, pa)

    def test_returns_none_when_no_approval(self):
        agent = self._agent()
        self.assertIsNone(agent._get_pending_approval("no-such-ctx"))

    def test_returns_none_after_expiry(self):
        agent = self._agent()
        pa = _pending_approval("ctx-expired")
        pa.created_at = time.monotonic() - 3700  # beyond 1800 s TTL
        agent._pending_approvals["ctx-expired"] = pa
        self.assertIsNone(agent._get_pending_approval("ctx-expired"))
        # Must also be purged from dict
        self.assertNotIn("ctx-expired", agent._pending_approvals)


# ── SampleAgent integration: approval gate flow ────────────────────────────────

def _patch_all(executable_action_type: str = "RESTART_BGRFC"):
    """Return a list of context managers that mock the full M1-M5 pipeline."""
    action = _make_action(executable_action_type, rank=1)
    from evidence.models import Classification, ForensicReport, NarrationResult
    classification = Classification(
        root_cause="BGRFC_QUEUE_BLOCKAGE",
        confidence="HIGH",
        remediation_actions=[action],
    )
    report = ForensicReport(
        consultant_view="## Report\nAll good.",
        planner_view="## Planner View",
        persisted_incident_id="inc-001",
    )

    return [
        patch("agent.ground_investigation_context", new=AsyncMock(return_value=MagicMock(
            incident_type="bgRFC queue blockage",
            confidence="HIGH",
            process_context="PP/DS → bgRFC → S4",
            relevant_systems=["S4HANA", "PP_DS"],
            disambiguated_terms={},
            kg_bp_ids=["BPS-100"],
            fallback_used=False,
        ))),
        patch("agent.collect_evidence", new=AsyncMock(return_value=MagicMock(
            insufficient_coverage_warning=False,
        ))),
        patch("agent.build_evidence_graph", return_value=MagicMock(
            _material="FG-1234", _plant="1000", _incident_type="bgRFC queue blockage"
        )),
        patch("agent.classify", return_value=classification),
        patch("agent.rank_remediation_actions", return_value=[action]),
        patch("agent.narrate_findings", new=AsyncMock(return_value=MagicMock(
            consultant_sections={}, planner_sections={}, fallback_used=False
        ))),
        patch("agent.detect_patterns", new=AsyncMock(return_value=None)),
        patch("agent.generate_report", return_value=report),
        patch("agent.persist_incident", new=AsyncMock()),
        patch("agent.SampleAgent._get_llm", new=AsyncMock(return_value=MagicMock())),
        patch("agent.S4Client"),
        patch("agent.IBPClient"),
        patch("agent.InMemorySaver"),
    ]


class TestApprovalGateFlow(unittest.IsolatedAsyncioTestCase):

    async def _run_stream(self, agent, query, ctx="ctx-a"):
        chunks = []
        async for chunk in agent.stream(query, ctx):
            chunks.append(chunk)
        return chunks

    # ── Test 1: executable action → gate fires ─────────────────────────────
    async def test_executable_action_triggers_gate(self):
        patches = _patch_all("RESTART_BGRFC")
        with patches[0], patches[1], patches[2], patches[3], patches[4], \
             patches[5], patches[6], patches[7], patches[8], patches[9], \
             patches[10], patches[11], patches[12]:
            agent = SampleAgent()
            chunks = await self._run_stream(
                agent, "Why is planned order for FG-1234 plant 1000 missing?", "ctx-gate"
            )
        last = chunks[-1]
        self.assertFalse(last["is_task_complete"])
        self.assertTrue(last["require_user_input"])
        self.assertIn("Action Approval Required", last["content"])
        self.assertIn("RESTART_BGRFC", last["content"])

    # ── Test 2: MANUAL_ONLY action → no gate ──────────────────────────────
    async def test_manual_only_skips_gate(self):
        from evidence.models import Classification, ForensicReport
        manual_action = _make_action("MANUAL_ONLY", rank=1)
        classification = Classification(
            root_cause="MASTER_DATA_ISSUE",
            confidence="MEDIUM",
            remediation_actions=[manual_action],
        )
        report = ForensicReport(
            consultant_view="## Report\nManual fix needed.",
            planner_view="",
            persisted_incident_id="inc-manual",
        )
        patches = [
            patch("agent.ground_investigation_context", new=AsyncMock(return_value=MagicMock(
                incident_type="PIR exists but no planned order created",
                confidence="MEDIUM",
                process_context="",
                relevant_systems=[],
                disambiguated_terms={},
                kg_bp_ids=[],
                fallback_used=True,
            ))),
            patch("agent.collect_evidence", new=AsyncMock(return_value=MagicMock(insufficient_coverage_warning=False))),
            patch("agent.build_evidence_graph", return_value=MagicMock()),
            patch("agent.classify", return_value=classification),
            patch("agent.rank_remediation_actions", return_value=[manual_action]),
            patch("agent.narrate_findings", new=AsyncMock(return_value=MagicMock(
                consultant_sections={}, planner_sections={}, fallback_used=False
            ))),
            patch("agent.detect_patterns", new=AsyncMock(return_value=None)),
            patch("agent.generate_report", return_value=report),
            patch("agent.persist_incident", new=AsyncMock()),
            patch("agent.SampleAgent._get_llm", new=AsyncMock(return_value=MagicMock())),
            patch("agent.S4Client"),
            patch("agent.IBPClient"),
            patch("agent.InMemorySaver"),
        ]
        with patches[0], patches[1], patches[2], patches[3], patches[4], \
             patches[5], patches[6], patches[7], patches[8], patches[9], \
             patches[10], patches[11], patches[12]:
            agent = SampleAgent()
            chunks = await self._run_stream(
                agent, "Why is planned order for MAT-999 plant 2000 missing?", "ctx-manual"
            )
        last = chunks[-1]
        self.assertTrue(last["is_task_complete"])
        self.assertFalse(last["require_user_input"])
        self.assertIn("Manual fix needed", last["content"])

    # ── Test 3: "Yes, proceed" resolves approval ───────────────────────────
    async def test_yes_resolves_approval(self):
        patches = _patch_all("RESTART_BGRFC")
        with patches[0], patches[1], patches[2], patches[3], patches[4], \
             patches[5], patches[6], patches[7], patches[8], patches[9], \
             patches[10], patches[11], patches[12]:
            agent = SampleAgent()
            # First turn: get the approval gate
            await self._run_stream(agent, "Why is FG-1234 plant 1000 missing?", "ctx-yes")
            # Second turn: approve
            chunks = await self._run_stream(agent, "Yes, proceed", "ctx-yes")
        last = chunks[-1]
        self.assertTrue(last["is_task_complete"])
        self.assertFalse(last["require_user_input"])
        self.assertIn("Actions Approved", last["content"])
        self.assertIn("RESTART_BGRFC", last["content"])
        self.assertIn("Report", last["content"])  # full report appended

    # ── Test 4: "No, skip" rejects approval ───────────────────────────────
    async def test_no_rejects_approval(self):
        patches = _patch_all("RESTART_BGRFC")
        with patches[0], patches[1], patches[2], patches[3], patches[4], \
             patches[5], patches[6], patches[7], patches[8], patches[9], \
             patches[10], patches[11], patches[12]:
            agent = SampleAgent()
            await self._run_stream(agent, "Why is FG-1234 plant 1000 missing?", "ctx-no")
            chunks = await self._run_stream(agent, "No, skip", "ctx-no")
        last = chunks[-1]
        self.assertTrue(last["is_task_complete"])
        self.assertFalse(last["require_user_input"])
        self.assertIn("Actions Declined", last["content"])
        self.assertIn("Report", last["content"])

    # ── Test 5: expired approval not resolved ─────────────────────────────
    async def test_expired_approval_not_resolved(self):
        patches = _patch_all("RESTART_BGRFC")
        with patches[0], patches[1], patches[2], patches[3], patches[4], \
             patches[5], patches[6], patches[7], patches[8], patches[9], \
             patches[10], patches[11], patches[12]:
            agent = SampleAgent()
            await self._run_stream(agent, "Why is FG-1234 plant 1000 missing?", "ctx-exp")
            # Manually expire the pending approval
            if "ctx-exp" in agent._pending_approvals:
                agent._pending_approvals["ctx-exp"].created_at = time.monotonic() - 3700

            # "yes, proceed" now arrives but approval is expired — gets treated as new query
            # The second investigation will also fire the gate (same pipeline mock)
            chunks = await self._run_stream(agent, "Why is FG-1234 plant 1000 missing again?", "ctx-exp")

        last = chunks[-1]
        # Should NOT see "Actions Approved" — it's a fresh investigation
        self.assertNotIn("Actions Approved", last["content"])

    # ── Test 6: approval_id matches context_id ────────────────────────────
    async def test_approval_id_matches_context_id(self):
        patches = _patch_all("RESTART_BGRFC")
        with patches[0], patches[1], patches[2], patches[3], patches[4], \
             patches[5], patches[6], patches[7], patches[8], patches[9], \
             patches[10], patches[11], patches[12]:
            agent = SampleAgent()
            result = await agent._run_agent(
                "Why is FG-1234 plant 1000 missing?", "ctx-id-check"
            )
        self.assertTrue(result.requires_input)
        self.assertEqual(result.approval_id, "ctx-id-check")

    # ── Test 7: invoke returns input_required when gate fires ─────────────
    async def test_invoke_returns_input_required(self):
        patches = _patch_all("RESTART_BGRFC")
        with patches[0], patches[1], patches[2], patches[3], patches[4], \
             patches[5], patches[6], patches[7], patches[8], patches[9], \
             patches[10], patches[11], patches[12]:
            agent = SampleAgent()
            response = await agent.invoke(
                "Why is FG-1234 plant 1000 missing?", "ctx-invoke"
            )
        self.assertEqual(response.status, "input_required")
        self.assertIn("Action Approval Required", response.message)

    # ── Test 8: pending approval cleared after resolution ─────────────────
    async def test_pending_approval_cleared_after_resolution(self):
        patches = _patch_all("RESTART_BGRFC")
        with patches[0], patches[1], patches[2], patches[3], patches[4], \
             patches[5], patches[6], patches[7], patches[8], patches[9], \
             patches[10], patches[11], patches[12]:
            agent = SampleAgent()
            await self._run_stream(agent, "Why is FG-1234 plant 1000 missing?", "ctx-clear")
            self.assertIn("ctx-clear", agent._pending_approvals)
            await self._run_stream(agent, "yes proceed", "ctx-clear")
            self.assertNotIn("ctx-clear", agent._pending_approvals)

    # ── Test 9: M1 clarification still returns require_user_input ─────────
    async def test_m1_clarification_returns_require_user_input(self):
        patches = [
            patch("agent.ground_investigation_context", new=AsyncMock(return_value=MagicMock(
                incident_type="planned order missing in MD04",
                confidence="LOW",
                process_context="",
                relevant_systems=[],
                disambiguated_terms={},
                kg_bp_ids=[],
                fallback_used=True,
            ))),
            patch("agent.S4Client"),
            patch("agent.IBPClient"),
            patch("agent.InMemorySaver"),
        ]
        with patches[0], patches[1], patches[2], patches[3]:
            agent = SampleAgent()
            chunks = await self._run_stream(agent, "Something is broken", "ctx-m1")
        last = chunks[-1]
        self.assertFalse(last["is_task_complete"])
        self.assertTrue(last["require_user_input"])
        self.assertIn("material number", last["content"])


# ── Phase 4 dispatcher unit tests ────────────────────────────────────────────

class TestDispatcher(unittest.IsolatedAsyncioTestCase):
    """Tests for execution.dispatcher — action → MCP tool dispatch."""

    def _make_tool(self, name: str, response: str = '{"status": "ok"}'):
        """Build a minimal StructuredTool mock."""
        tool = MagicMock()
        tool.name = name
        tool.arun = AsyncMock(return_value=response)
        return tool

    def _make_action(self, action_type: str, params: dict | None = None) -> "RemediationAction":
        return RemediationAction(
            action_id=f"act-{action_type}",
            action_type=action_type,
            action_params=params or {"queue": "Q1"},
            requires_approval=True,
            rank=1,
        )

    # ── Test 11: tool found by exact name (mock mode) ─────────────────────────
    async def test_dispatch_exact_name_match(self):
        from execution.dispatcher import dispatch_approved_actions, DISPATCHED
        action = self._make_action("RESTART_BGRFC")
        tool = self._make_tool("restart_bgrfc_queue", '{"restarted": true}')
        results = await dispatch_approved_actions([action], [tool])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, DISPATCHED)
        self.assertEqual(results[0].tool_name, "restart_bgrfc_queue")
        self.assertIn("restarted", results[0].tool_response)

    # ── Test 12: tool found by enhanced-name suffix ───────────────────────────
    async def test_dispatch_suffix_name_match(self):
        from execution.dispatcher import dispatch_approved_actions, DISPATCHED
        action = self._make_action("REPROCESS_CPI_MESSAGE", {"message_id": "MSG-001"})
        tool = self._make_tool("bgrfc-agent_v1__reprocess_cpi_message", '{"queued": true}')
        results = await dispatch_approved_actions([action], [tool])
        self.assertEqual(results[0].status, DISPATCHED)
        self.assertEqual(results[0].tool_name, "bgrfc-agent_v1__reprocess_cpi_message")

    # ── Test 13: no tool registered → TOOL_NOT_REGISTERED + guidance ─────────
    async def test_dispatch_no_tool_registered(self):
        from execution.dispatcher import dispatch_approved_actions, TOOL_NOT_REGISTERED
        action = self._make_action("RESTART_BGRFC")
        results = await dispatch_approved_actions([action], [])  # empty tool list
        self.assertEqual(results[0].status, TOOL_NOT_REGISTERED)
        self.assertIn("SM58", results[0].fallback_guidance)
        self.assertEqual(results[0].tool_name, "")

    # ── Test 14: tool call raises → DISPATCH_FAILED + guidance ───────────────
    async def test_dispatch_tool_call_fails(self):
        from execution.dispatcher import dispatch_approved_actions, DISPATCH_FAILED
        action = self._make_action("RERUN_PPDS_HEURISTIC")
        tool = self._make_tool("rerun_ppds_heuristic")
        tool.arun = AsyncMock(side_effect=RuntimeError("gateway timeout"))
        results = await dispatch_approved_actions([action], [tool])
        self.assertEqual(results[0].status, DISPATCH_FAILED)
        self.assertIn("gateway timeout", results[0].error)
        self.assertIn("/SAPAPO/RRP3", results[0].fallback_guidance)

    # ── Test 15: multiple actions dispatched independently ────────────────────
    async def test_dispatch_multiple_actions(self):
        from execution.dispatcher import dispatch_approved_actions, DISPATCHED, TOOL_NOT_REGISTERED
        a1 = self._make_action("RESTART_BGRFC")
        a2 = self._make_action("RERUN_MRP_SINGLE_ITEM", {"material": "FG-1234", "plant": "1000"})
        tool1 = self._make_tool("restart_bgrfc_queue")
        # no tool registered for RERUN_MRP_SINGLE_ITEM
        results = await dispatch_approved_actions([a1, a2], [tool1])
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].status, DISPATCHED)
        self.assertEqual(results[1].status, TOOL_NOT_REGISTERED)

    # ── Test 16: format_dispatch_summary contains dispatched tool name ────────
    def test_format_dispatch_summary_dispatched(self):
        from execution.dispatcher import DispatchResult, format_dispatch_summary, DISPATCHED
        result = DispatchResult(
            action_id="a1", action_type="RESTART_BGRFC",
            status=DISPATCHED, tool_name="restart_bgrfc_queue",
            tool_response='{"ok": true}',
        )
        summary = format_dispatch_summary([result])
        self.assertIn("RESTART_BGRFC", summary)
        self.assertIn("restart_bgrfc_queue", summary)
        self.assertIn("✅", summary)

    # ── Test 17: format_dispatch_summary shows guidance for not-registered ─────
    def test_format_dispatch_summary_not_registered(self):
        from execution.dispatcher import DispatchResult, format_dispatch_summary, TOOL_NOT_REGISTERED
        result = DispatchResult(
            action_id="a2", action_type="RERUN_IBP_JOB",
            status=TOOL_NOT_REGISTERED,
            fallback_guidance="Trigger IBP job manually via IBP Monitor.",
        )
        summary = format_dispatch_summary([result])
        self.assertIn("⏳", summary)
        self.assertIn("IBP Monitor", summary)

    # ── Test 18: format_dispatch_summary shows error on DISPATCH_FAILED ───────
    def test_format_dispatch_summary_failed(self):
        from execution.dispatcher import DispatchResult, format_dispatch_summary, DISPATCH_FAILED
        result = DispatchResult(
            action_id="a3", action_type="REPROCESS_CPI_MESSAGE",
            status=DISPATCH_FAILED, tool_name="reprocess_cpi_message",
            error="connection refused", fallback_guidance="Use SXMB_MONI.",
        )
        summary = format_dispatch_summary([result])
        self.assertIn("❌", summary)
        self.assertIn("connection refused", summary)

    # ── Test 19: empty results → empty summary ────────────────────────────────
    def test_format_dispatch_summary_empty(self):
        from execution.dispatcher import format_dispatch_summary
        self.assertEqual(format_dispatch_summary([]), "")


# ── Phase 4 end-to-end: approve → dispatch wired through agent ───────────────

class TestApprovalDispatchIntegration(unittest.IsolatedAsyncioTestCase):
    """Verify _resolve_approval calls the dispatcher and includes the summary."""

    async def _run_stream(self, agent, query, ctx):
        chunks = []
        async for chunk in agent.stream(query, ctx):
            chunks.append(chunk)
        return chunks

    # ── Test 20: approval + dispatch summary appears in "yes" response ────────
    async def test_approved_response_includes_dispatch_summary(self):
        from execution.dispatcher import DISPATCHED
        mock_tool = MagicMock()
        mock_tool.name = "restart_bgrfc_queue"
        mock_tool.arun = AsyncMock(return_value='{"restarted": true}')

        patches = _patch_all("RESTART_BGRFC")
        with patches[0], patches[1], patches[2], patches[3], patches[4], \
             patches[5], patches[6], patches[7], patches[8], patches[9], \
             patches[10], patches[11], patches[12], \
             patch("agent.get_mcp_tools", new=AsyncMock(return_value=[mock_tool])):
            agent = SampleAgent()
            await self._run_stream(agent, "Why is FG-1234 plant 1000 missing?", "ctx-disp-yes")
            chunks = await self._run_stream(agent, "Yes, proceed", "ctx-disp-yes")

        last = chunks[-1]
        self.assertTrue(last["is_task_complete"])
        self.assertIn("Actions Approved", last["content"])
        self.assertIn("Execution Dispatch Summary", last["content"])
        self.assertIn("restart_bgrfc_queue", last["content"])

    # ── Test 21: tool not registered → summary shows ⏳ guidance ─────────────
    async def test_approved_no_tool_shows_not_registered_guidance(self):
        patches = _patch_all("RESTART_BGRFC")
        with patches[0], patches[1], patches[2], patches[3], patches[4], \
             patches[5], patches[6], patches[7], patches[8], patches[9], \
             patches[10], patches[11], patches[12], \
             patch("agent.get_mcp_tools", new=AsyncMock(return_value=[])):
            agent = SampleAgent()
            await self._run_stream(agent, "Why is FG-1234 plant 1000 missing?", "ctx-disp-notool")
            chunks = await self._run_stream(agent, "Yes, proceed", "ctx-disp-notool")

        last = chunks[-1]
        self.assertIn("Actions Approved", last["content"])
        self.assertIn("Execution Dispatch Summary", last["content"])
        self.assertIn("SM58", last["content"])          # fallback guidance for RESTART_BGRFC

    # ── Test 22: get_mcp_tools raises → dispatch skipped, approval still works ─
    async def test_mcp_tools_error_does_not_break_approval(self):
        patches = _patch_all("RESTART_BGRFC")
        with patches[0], patches[1], patches[2], patches[3], patches[4], \
             patches[5], patches[6], patches[7], patches[8], patches[9], \
             patches[10], patches[11], patches[12], \
             patch("agent.get_mcp_tools", new=AsyncMock(side_effect=RuntimeError("AGW down"))):
            agent = SampleAgent()
            await self._run_stream(agent, "Why is FG-1234 plant 1000 missing?", "ctx-disp-err")
            chunks = await self._run_stream(agent, "Yes, proceed", "ctx-disp-err")

        last = chunks[-1]
        # Approval still resolves even when tool loading fails
        self.assertTrue(last["is_task_complete"])
        self.assertIn("Actions Approved", last["content"])

    # ── Test 23: rejection still delivers full report (no dispatch) ───────────
    async def test_rejected_no_dispatch_called(self):
        mock_get_tools = AsyncMock(return_value=[])
        patches = _patch_all("RESTART_BGRFC")
        with patches[0], patches[1], patches[2], patches[3], patches[4], \
             patches[5], patches[6], patches[7], patches[8], patches[9], \
             patches[10], patches[11], patches[12], \
             patch("agent.get_mcp_tools", new=mock_get_tools):
            agent = SampleAgent()
            await self._run_stream(agent, "Why is FG-1234 plant 1000 missing?", "ctx-reject-disp")
            await self._run_stream(agent, "No, skip", "ctx-reject-disp")

        # get_mcp_tools must NOT be called on rejection path
        mock_get_tools.assert_not_called()



# ===========================================================================
# Section 3 – mcp-mock.json end-to-end dispatch tests
# ===========================================================================

class TestMockFileDispatch(unittest.IsolatedAsyncioTestCase):
    """Verify that IBD_TESTING=1 loads mcp-mock.json tools and the full
    dispatch path returns DISPATCHED + mock-agent footer."""

    def _mock_file_path(self):
        import pathlib
        # mcp-mock.json lives at the package root (one level above app/)
        return pathlib.Path(__file__).parent.parent / "mcp-mock.json"

    def test_mock_file_exists(self):
        self.assertTrue(self._mock_file_path().exists(), "mcp-mock.json must exist")

    def test_mock_file_parseable(self):
        import json
        data = json.loads(self._mock_file_path().read_text())
        self.assertIn("servers", data)
        servers = data["servers"]
        self.assertTrue(len(servers) >= 1, "At least one server must be defined")

    def test_mock_file_has_all_five_tools(self):
        import json
        data = json.loads(self._mock_file_path().read_text())
        all_tools: set[str] = set()
        for server in data["servers"].values():
            all_tools.update(server.get("tools", {}).keys())
        expected = {
            "restart_bgrfc_queue",
            "reprocess_cpi_message",
            "rerun_ppds_heuristic",
            "rerun_mrp_single_item",
            "rerun_ibp_planning_job",
        }
        self.assertEqual(all_tools, expected)

    def test_each_tool_has_mock_response_with_mode(self):
        import json
        data = json.loads(self._mock_file_path().read_text())
        for server_name, server in data["servers"].items():
            for tool_name, tool_def in server.get("tools", {}).items():
                resp = tool_def.get("mock_response", {})
                self.assertEqual(
                    resp.get("mode"), "MOCK_AGENT",
                    f"{tool_name}: mock_response.mode must be MOCK_AGENT",
                )
                self.assertIn(
                    "phase_notice", resp,
                    f"{tool_name}: mock_response must contain phase_notice",
                )

    def test_build_mock_tools_returns_five_tools(self):
        import os, sys
        sys.path.insert(0, str(self._mock_file_path().parent / "app"))
        os.environ["IBD_TESTING"] = "1"
        try:
            import importlib
            import mcp_tools
            importlib.reload(mcp_tools)
            tools = mcp_tools._build_mock_tools()
            names = {t.name for t in tools}
            expected = {
                "restart_bgrfc_queue",
                "reprocess_cpi_message",
                "rerun_ppds_heuristic",
                "rerun_mrp_single_item",
                "rerun_ibp_planning_job",
            }
            self.assertEqual(names, expected)
        finally:
            del os.environ["IBD_TESTING"]

    async def test_mock_tool_coroutine_returns_mock_response(self):
        import os, sys, json
        sys.path.insert(0, str(self._mock_file_path().parent / "app"))
        os.environ["IBD_TESTING"] = "1"
        try:
            import importlib, mcp_tools
            importlib.reload(mcp_tools)
            tools = mcp_tools._build_mock_tools()
            restart_tool = next(t for t in tools if t.name == "restart_bgrfc_queue")
            result = await restart_tool.arun({"material": "FG-1234", "plant": "1000"})
            payload = json.loads(result)
            self.assertEqual(payload["mode"], "MOCK_AGENT")
            self.assertEqual(payload["status"], "MOCK_EXECUTED")
            self.assertTrue(payload.get("queue_restarted"))
        finally:
            del os.environ["IBD_TESTING"]

    async def test_dispatch_with_mock_tools_returns_dispatched(self):
        import os, sys, json
        sys.path.insert(0, str(self._mock_file_path().parent / "app"))
        os.environ["IBD_TESTING"] = "1"
        try:
            import importlib, mcp_tools
            importlib.reload(mcp_tools)
            tools = mcp_tools._build_mock_tools()

            # Build a minimal action
            sys.path.insert(0, str(self._mock_file_path().parent / "app"))
            from evidence.models import RemediationAction
            action = RemediationAction(
                action_id="test-001",
                action_type="RESTART_BGRFC",
                action_params={"material": "FG-1234", "plant": "1000"},
                requires_approval=True,
                rank=1,
            )

            from execution.dispatcher import dispatch_approved_actions, format_dispatch_summary, DISPATCHED
            results = await dispatch_approved_actions([action], tools)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].status, DISPATCHED)
            self.assertEqual(results[0].tool_name, "restart_bgrfc_queue")

            payload = json.loads(results[0].tool_response)
            self.assertEqual(payload["mode"], "MOCK_AGENT")

            # Summary must include Mock Agent Mode footer
            summary = format_dispatch_summary(results)
            self.assertIn("Mock Agent Mode", summary)
            self.assertIn("Phase 4", summary)
            self.assertIn("*(Mock Agent)*", summary)
        finally:
            del os.environ["IBD_TESTING"]

    async def test_is_mock_response_helper(self):
        import json
        from execution.dispatcher import _is_mock_response
        self.assertTrue(_is_mock_response(json.dumps({"mode": "MOCK_AGENT"})))
        self.assertFalse(_is_mock_response(json.dumps({"mode": "LIVE"})))
        self.assertFalse(_is_mock_response("not-json"))
        self.assertFalse(_is_mock_response(""))


if __name__ == "__main__":
    unittest.main()
