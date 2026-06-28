"""
L2 — Remediation outcome tracking.
Links user-reported outcomes to specific remediation actions in HANA Cloud.
"""
from __future__ import annotations
import logging
from db import hana_client

logger = logging.getLogger(__name__)

VALID_OUTCOMES = {"Resolved", "Partially Resolved", "Not Resolved", "Made Worse"}


async def record_outcome(incident_id: str, action_id: str, outcome: str) -> None:
    """
    Record a user-reported remediation outcome against a specific action.
    Raises ValueError for invalid outcome values.
    """
    if outcome not in VALID_OUTCOMES:
        raise ValueError(f"Invalid outcome '{outcome}'. Must be one of: {VALID_OUTCOMES}")
    try:
        hana_client.execute(
            "UPDATE RemediationRecord SET outcome = ?, outcome_at = CURRENT_TIMESTAMP "
            "WHERE action_id = ? AND incident_id = ?",
            (outcome, action_id, incident_id),
        )
        logger.info(
            "L2.achieved: outcome recorded — incident_id=%s, action_id=%s, outcome=%s",
            incident_id, action_id, outcome,
        )
    except Exception as exc:
        logger.error(
            "L2.missed: outcome recording failed — incident_id=%s, error=%s",
            incident_id, exc,
        )
        raise
