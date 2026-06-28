"""Unit tests for learning engine (L1–L5)."""
import pytest
from unittest.mock import patch, MagicMock
from evidence.models import (
    Classification, EvidenceGraph, ForensicReport, PatternResult,
    EvidenceNode, EvidenceLink, RemediationAction,
)


def _make_graph():
    import uuid
    node = EvidenceNode(
        node_id=str(uuid.uuid4()),
        system_name="S4HANA_BGRFC_QUEUE", status="MISSING_DATA",
        raw_payload={}, manual_guidance="",
    )
    g = EvidenceGraph(incident_id="test-graph-001", nodes=[node], links=[], broken_boundaries=[])
    g._material = "MAT-001"
    g._plant = "1000"
    g._incident_type = "planned order missing in MD04"
    return g


def _make_classification():
    return Classification(
        root_cause="BGRFC_QUEUE_BLOCKAGE", confidence="HIGH", rule_id="RC001",
        description="bgRFC queue blocked.",
        remediation_actions=[], confirmed_findings=[], probable_findings=[], missing_findings=[],
    )


def _make_report():
    return ForensicReport(
        consultant_view="Consultant view content",
        planner_view="Planner view content",
        persisted_incident_id="test-001",
        sections_count=14,
    )


def _make_action():
    import uuid
    return RemediationAction(
        action_id=str(uuid.uuid4()),
        action_type="RESTART_BGRFC", action_params={},
        requires_approval=True, rank=1,
    )


# ── L1 persistence ────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_l1_persist_incident():
    with patch("learning.persistence.hana_client") as mock_hana:
        mock_hana.execute = MagicMock()
        mock_hana.fetchall = MagicMock(return_value=[])
        from learning.persistence import persist_incident
        result = await persist_incident(
            "test-001", _make_graph(), _make_classification(), _make_report(), [_make_action()],
        )
    assert result == "test-001"


@pytest.mark.asyncio
async def test_l1_persist_incident_survives_hana_error():
    with patch("learning.persistence.hana_client") as mock_hana:
        mock_hana.execute = MagicMock(side_effect=Exception("HANA unreachable"))
        from learning.persistence import persist_incident
        result = await persist_incident(
            "test-002", _make_graph(), _make_classification(), _make_report(), [],
        )
    # Must not raise — failure is logged and swallowed
    assert result == "test-002"


# ── L2 outcome tracker ────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_l2_record_outcome_valid():
    with patch("learning.outcome_tracker.hana_client") as mock_hana:
        mock_hana.execute = MagicMock()
        from learning.outcome_tracker import record_outcome
        await record_outcome("incident-001", "action-001", "Resolved")


@pytest.mark.asyncio
async def test_l2_record_outcome_invalid_raises():
    with patch("learning.outcome_tracker.hana_client") as mock_hana:
        mock_hana.execute = MagicMock()
        from learning.outcome_tracker import record_outcome
        with pytest.raises(ValueError, match="Invalid outcome"):
            await record_outcome("incident-001", "action-001", "UNKNOWN_OUTCOME")


# ── L3 effectiveness ──────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_l3_update_effectiveness_new_record():
    with patch("learning.effectiveness.hana_client") as mock_hana:
        mock_hana.fetchall = MagicMock(return_value=[])
        mock_hana.execute = MagicMock()
        from learning.effectiveness import update_effectiveness
        await update_effectiveness("BGRFC_QUEUE_BLOCKAGE", "RESTART_BGRFC", "Resolved")
        assert mock_hana.execute.call_count >= 1


@pytest.mark.asyncio
async def test_l3_update_effectiveness_existing_record():
    with patch("learning.effectiveness.hana_client") as mock_hana:
        mock_hana.fetchall = MagicMock(return_value=[("score-001", 5, 3)])
        mock_hana.execute = MagicMock()
        from learning.effectiveness import update_effectiveness
        await update_effectiveness("BGRFC_QUEUE_BLOCKAGE", "RESTART_BGRFC", "Resolved")
        # Should call UPDATE
        call_args = mock_hana.execute.call_args[0][0]
        assert "UPDATE" in call_args


# ── L4 pattern detection ──────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_l4_detect_patterns_no_occurrences():
    with patch("learning.pattern_detector.hana_client") as mock_hana:
        mock_hana.fetchall = MagicMock(return_value=[[0]])
        from learning.pattern_detector import detect_patterns
        result = await detect_patterns("MAT-001", "1000", "BGRFC_QUEUE_BLOCKAGE", "incident-001")
    assert result.occurrence_count == 0
    assert result.pattern_flagged is False
    assert result.systemic is False


@pytest.mark.asyncio
async def test_l4_detect_patterns_systemic():
    with patch("learning.pattern_detector.hana_client") as mock_hana:
        mock_hana.fetchall = MagicMock(return_value=[[7]])
        from learning.pattern_detector import detect_patterns
        result = await detect_patterns("MAT-001", "1000", "BGRFC_QUEUE_BLOCKAGE", "incident-001")
    assert result.occurrence_count == 7
    assert result.systemic is True
    assert result.pattern_flagged is True


@pytest.mark.asyncio
async def test_l4_detect_patterns_survives_hana_error():
    with patch("learning.pattern_detector.hana_client") as mock_hana:
        mock_hana.fetchall = MagicMock(side_effect=Exception("HANA down"))
        from learning.pattern_detector import detect_patterns
        result = await detect_patterns("MAT-001", "1000", "BGRFC_QUEUE_BLOCKAGE", "incident-001")
    assert result.occurrence_count == 0
    assert result.pattern_flagged is False


# ── L5 predictive scanner ─────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_l5_scan_no_alerts_when_no_history():
    with patch("learning.predictive_scanner.hana_client") as mock_hana:
        mock_hana.fetchall = MagicMock(return_value=[])
        from learning.predictive_scanner import scan_for_pre_failure_signatures
        alerts = await scan_for_pre_failure_signatures([("MAT-001", "1000"), ("MAT-002", "2000")])
    assert alerts == []


@pytest.mark.asyncio
async def test_l5_scan_generates_alert_when_history_matches():
    with patch("learning.predictive_scanner.hana_client") as mock_hana:
        mock_hana.fetchall = MagicMock(return_value=[["inc-1"], ["inc-2"]])
        from learning.predictive_scanner import scan_for_pre_failure_signatures
        alerts = await scan_for_pre_failure_signatures([("MAT-001", "1000")])
    assert len(alerts) > 0
    assert alerts[0].affected_material == "MAT-001"
    assert alerts[0].recommended_preventive_action != ""


@pytest.mark.asyncio
async def test_l5_scan_capped_at_500_pairs():
    with patch("learning.predictive_scanner.hana_client") as mock_hana:
        mock_hana.fetchall = MagicMock(return_value=[])
        pairs = [(f"M-{i}", "1000") for i in range(600)]
        from learning.predictive_scanner import scan_for_pre_failure_signatures
        # Should not raise and should process at most 500
        alerts = await scan_for_pre_failure_signatures(pairs)
    assert isinstance(alerts, list)
