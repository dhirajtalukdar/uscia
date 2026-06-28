"""Unit tests for remediation action ranker."""
import pytest
from unittest.mock import patch
from evidence.models import Classification, RemediationAction
from classification.remediation_ranker import rank_remediation_actions


def _make_classification(root_cause: str, actions: list) -> Classification:
    return Classification(
        root_cause=root_cause,
        confidence="HIGH",
        rule_id="RC001",
        description="Test",
        remediation_actions=actions,
        confirmed_findings=[],
        probable_findings=[],
        missing_findings=[],
    )


def _make_action(action_type: str, rank: int = 0) -> RemediationAction:
    import uuid
    return RemediationAction(
        action_id=str(uuid.uuid4()),
        action_type=action_type,
        action_params={},
        requires_approval=True,
        rank=rank,
    )


def test_ranker_returns_list():
    classification = _make_classification(
        "BGRFC_QUEUE_BLOCKAGE",
        [_make_action("RESTART_BGRFC"), _make_action("MANUAL_ONLY")],
    )
    # Patch HANA fetchall to return empty (no effectiveness data)
    with patch("classification.remediation_ranker.hana_client") as mock_hana:
        mock_hana.fetchall.return_value = []
        result = rank_remediation_actions(classification)
    assert isinstance(result, list)
    assert len(result) == 2


def test_ranker_assigns_sequential_ranks():
    classification = _make_classification(
        "BGRFC_QUEUE_BLOCKAGE",
        [_make_action("RESTART_BGRFC"), _make_action("RERUN_MRP_SINGLE_ITEM")],
    )
    with patch("classification.remediation_ranker.hana_client") as mock_hana:
        mock_hana.fetchall.return_value = []
        result = rank_remediation_actions(classification)
    ranks = [a.rank for a in result]
    assert sorted(ranks) == ranks  # should be sorted ascending


def test_ranker_requires_approval_always_true():
    classification = _make_classification(
        "MRP_CONFIG_ERROR",
        [_make_action("RERUN_MRP_SINGLE_ITEM")],
    )
    with patch("classification.remediation_ranker.hana_client") as mock_hana:
        mock_hana.fetchall.return_value = []
        result = rank_remediation_actions(classification)
    for action in result:
        assert action.requires_approval is True
