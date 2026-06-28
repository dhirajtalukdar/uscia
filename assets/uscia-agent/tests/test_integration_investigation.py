"""
Integration test: end-to-end investigation with all tools stubbed to MISSING_DATA.
Verifies that _run_agent() returns a report string containing all 14 section headers.
"""
import pytest
import asyncio
import os
from unittest.mock import AsyncMock, patch, MagicMock

# Ensure test mode
os.environ.setdefault("IBD_TESTING", "true")


def _missing(system: str) -> dict:
    return {"status": "MISSING_DATA", "system": system, "guidance": f"Check {system}."}


@pytest.mark.asyncio
async def test_full_investigation_returns_14_sections():
    """
    Full pipeline: context extraction -> collect_evidence -> graph -> classify ->
    narrate -> generate_report. All evidence tools mocked MISSING_DATA.
    LLM narration mocked via aicore.init_llm_from_destination stub.
    """
    from evidence.models import NarrationResult
    from report.generator import _SECTIONS

    mock_narration = NarrationResult(
        consultant_sections={"executive_summary": "All data unavailable."},
        planner_sections={},
        fallback_used=True,
    )

    # Stub LLM init — prevents network call to destination service
    mock_llm = MagicMock()
    mock_llm_coro = AsyncMock(return_value=mock_llm)

    with patch("evidence.collector.get_planned_orders", AsyncMock(return_value=_missing("S4HANA_PLANNED_ORDER"))), \
         patch("evidence.collector.get_material_planning_data", AsyncMock(return_value=_missing("S4HANA_MRP"))), \
         patch("evidence.collector.get_planned_independent_requirements", AsyncMock(return_value=_missing("S4HANA_PIR"))), \
         patch("evidence.collector.get_ppds_stock_level", AsyncMock(return_value=_missing("S4HANA_PPDS_STOCK"))), \
         patch("evidence.collector.get_ppds_flexible_constraints", AsyncMock(return_value=_missing("S4HANA_PPDS_CONSTRAINTS"))), \
         patch("evidence.collector.get_atp_check_result", AsyncMock(return_value=_missing("S4HANA_ATP"))), \
         patch("evidence.collector.get_application_logs", AsyncMock(return_value=_missing("S4HANA_APPLICATION_LOGS"))), \
         patch("evidence.collector.get_bgrfc_queue_status", AsyncMock(return_value=_missing("S4HANA_BGRFC_QUEUE"))), \
         patch("evidence.collector.get_ppds_config_and_mrp_issues", AsyncMock(return_value=_missing("S4HANA_PPDS_CONFIG"))), \
         patch("evidence.collector.get_ibp_supply_data", AsyncMock(return_value=_missing("IBP_SUPPLY"))), \
         patch("evidence.collector.get_cpi_message_status", AsyncMock(return_value=_missing("CPI_RTI"))), \
         patch("evidence.collector.get_pipo_message_status", AsyncMock(return_value=_missing("PIPO"))), \
         patch("evidence.collector.get_cloud_alm_health_events", AsyncMock(return_value=_missing("CLOUD_ALM"))), \
         patch("evidence.collector.get_bdc_supply_chain_analytics", AsyncMock(return_value=_missing("SAP_BDC"))), \
         patch("llm.narrator.narrate_findings", AsyncMock(return_value=mock_narration)), \
         patch("aicore.init_llm_from_destination", mock_llm_coro), \
         patch("agent.init_llm_from_destination", mock_llm_coro), \
         patch("learning.persistence.hana_client") as mock_hana_persist, \
         patch("learning.pattern_detector.hana_client") as mock_hana_pattern:

        mock_hana_persist.execute = MagicMock()
        mock_hana_persist.fetchall = MagicMock(return_value=[])
        mock_hana_pattern.fetchall = MagicMock(return_value=[[0]])

        with patch("classification.remediation_ranker.hana_client") as mock_hana_rank:
            mock_hana_rank.fetchall = MagicMock(return_value=[])

            from agent import SampleAgent
            from helpers import make_fake
            agent = SampleAgent(
                s4_client=make_fake(),
                ibp_client=make_fake(),
            )
            result = await agent._run_agent(
                "Investigate why planned order for material MAT-001 plant 1000 is missing in MD04",
                "test-context-001",
            )

    # _run_agent now returns AgentResult; unwrap content for assertions
    report_text = result.content if hasattr(result, "content") else result
    assert isinstance(report_text, str)
    assert len(report_text) > 100
    for _, header in _SECTIONS:
        assert header in report_text, f"Missing section in integration test output: {header}"
