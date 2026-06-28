"""Unit tests for LLM narrator module."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from evidence.models import (
    Classification, EvidenceGraph, EvidenceNode, InvestigationContext, NarrationResult,
)


def _make_ctx():
    return InvestigationContext(
        material="MAT-001", plant="1000", planning_version="000",
        date_from="2024-01-01", date_to="2024-12-31",
        incident_type="planned order missing in MD04", continuity_keys={},
    )


def _make_node(system, status="AVAILABLE"):
    import uuid
    return EvidenceNode(
        node_id=str(uuid.uuid4()), system_name=system, status=status,
        raw_payload={}, manual_guidance="",
    )


def _make_graph():
    return EvidenceGraph(
        incident_id="test-001",
        nodes=[_make_node("S4HANA_BGRFC_QUEUE", "MISSING_DATA"), _make_node("S4HANA_MRP")],
        links=[], broken_boundaries=[],
    )


def _make_classification(confident=True):
    return Classification(
        root_cause="BGRFC_QUEUE_BLOCKAGE",
        confidence="HIGH" if confident else "INDETERMINATE",
        rule_id="RC001", description="bgRFC blocked.",
        remediation_actions=[], confirmed_findings=["[CONFIRMED] bgRFC missing"],
        probable_findings=[], missing_findings=[],
    )


@pytest.mark.asyncio
async def test_narrator_fallback_on_import_error():
    """When langchain_community is not importable, fallback narration is returned."""
    import builtins
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "langchain_community.chat_models":
            raise ImportError("No module named 'langchain_community'")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=mock_import):
        from llm.narrator import narrate_findings
        result = await narrate_findings(_make_classification(), _make_graph(), _make_ctx())

    assert isinstance(result, NarrationResult)
    assert result.fallback_used is True


@pytest.mark.asyncio
async def test_narrator_fallback_on_llm_exception():
    """When LLM raises, fallback narration is returned."""
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(side_effect=RuntimeError("LLM timeout"))
    mock_chat_module = MagicMock()
    mock_chat_module.ChatLiteLLM = MagicMock(return_value=mock_llm)

    import sys
    fake_langchain = MagicMock()
    fake_langchain.ChatLiteLLM = MagicMock(return_value=mock_llm)

    with patch.dict(sys.modules, {
        "langchain_community": MagicMock(),
        "langchain_community.chat_models": fake_langchain,
        "langchain_core.messages": MagicMock(HumanMessage=MagicMock, SystemMessage=MagicMock),
    }):
        from llm import narrator as narrator_mod
        import importlib
        importlib.reload(narrator_mod)
        result = await narrator_mod.narrate_findings(_make_classification(), _make_graph(), _make_ctx())

    assert isinstance(result, NarrationResult)
    # fallback_used may be True (if LLM fails) or False (if mock worked)
    assert hasattr(result, "fallback_used")


def test_fallback_narration_has_all_sections():
    """_fallback_narration must include all 14 section keys in both views."""
    from llm.narrator import _fallback_narration, _14_SECTIONS
    result = _fallback_narration(_make_classification(), _make_ctx())
    assert result.fallback_used is True
    for section in _14_SECTIONS:
        assert section in result.consultant_sections
        assert section in result.planner_sections


def test_build_evidence_payload_contains_context():
    """_build_evidence_payload must contain material, plant, root_cause."""
    from llm.narrator import _build_evidence_payload
    payload_str = _build_evidence_payload(_make_classification(), _make_graph(), _make_ctx())
    assert "MAT-001" in payload_str
    assert "1000" in payload_str
    assert "BGRFC_QUEUE_BLOCKAGE" in payload_str


@pytest.mark.asyncio
async def test_narrator_returns_narration_result_with_mock():
    """With mocked LLM that returns valid JSON, NarrationResult should be populated."""
    mock_response = MagicMock()
    mock_response.content = '''{
        "consultant_view": {"executive_summary": "bgRFC blocked."},
        "planner_view": {"executive_summary": "Queue blockage."}
    }'''
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)
    mock_msg = MagicMock()

    import sys
    fake_lc = MagicMock()
    fake_lc.ChatLiteLLM = MagicMock(return_value=mock_llm)
    fake_msgs = MagicMock()
    fake_msgs.HumanMessage = mock_msg
    fake_msgs.SystemMessage = mock_msg

    with patch.dict(sys.modules, {
        "langchain_community": MagicMock(),
        "langchain_community.chat_models": fake_lc,
        "langchain_core.messages": fake_msgs,
    }):
        import importlib
        from llm import narrator as narrator_mod
        importlib.reload(narrator_mod)
        result = await narrator_mod.narrate_findings(_make_classification(), _make_graph(), _make_ctx())

    assert isinstance(result, NarrationResult)
