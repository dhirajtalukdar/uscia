"""
Remediation action ranker.
Queries EffectivenessScore from HANA Cloud and sorts actions by resolution_rate.
All actions have requires_approval=True — never overridable in the current build.
"""
from __future__ import annotations
import logging
from evidence.models import Classification, RemediationAction
from db import hana_client

logger = logging.getLogger(__name__)


def rank_remediation_actions(classification: Classification) -> list[RemediationAction]:
    """
    Re-rank remediation actions by historical effectiveness score.
    Falls back to alphabetical by action_type when no history exists.
    requires_approval=True is enforced on all actions; cannot be overridden.
    """
    actions = classification.remediation_actions
    if not actions:
        return actions

    root_cause = classification.root_cause
    try:
        rows = hana_client.fetchall(
            "SELECT action_type, resolution_rate FROM EffectivenessScore "
            "WHERE root_cause = ? ORDER BY resolution_rate DESC",
            (root_cause,),
        )
        score_map = {row[0]: float(row[1]) for row in rows} if rows else {}
    except Exception as exc:
        logger.warning("EffectivenessScore query failed: %s", exc)
        score_map = {}

    def sort_key(a: RemediationAction) -> tuple:
        score = score_map.get(a.action_type, 0.0)
        return (-score, a.action_type)  # highest score first; alpha fallback

    ranked = sorted(actions, key=sort_key)
    for i, action in enumerate(ranked, start=1):
        action.rank = i
        action.requires_approval = True  # always enforced

    return ranked
