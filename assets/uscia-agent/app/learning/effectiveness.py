"""
L3 — Remediation effectiveness model.
Maintains effectiveness scores per (root_cause, action_type) pair in HANA Cloud.
"""
from __future__ import annotations
import logging
import uuid
from db import hana_client

logger = logging.getLogger(__name__)


async def update_effectiveness(root_cause: str, action_type: str, outcome: str) -> None:
    """
    Upsert EffectivenessScore for a (root_cause, action_type) pair.
    Increments total_attempts; increments total_resolved if outcome is 'Resolved'.
    Recalculates resolution_rate = total_resolved / total_attempts.
    """
    try:
        rows = hana_client.fetchall(
            "SELECT score_id, total_attempts, total_resolved FROM EffectivenessScore "
            "WHERE root_cause = ? AND action_type = ?",
            (root_cause, action_type),
        )
        resolved_increment = 1 if outcome == "Resolved" else 0

        if rows:
            score_id, attempts, resolved = rows[0][0], int(rows[0][1]), int(rows[0][2])
            new_attempts = attempts + 1
            new_resolved = resolved + resolved_increment
            new_rate = round(new_resolved / new_attempts, 4) if new_attempts > 0 else 0.0
            hana_client.execute(
                "UPDATE EffectivenessScore SET total_attempts=?, total_resolved=?, resolution_rate=?, "
                "updated_at=CURRENT_TIMESTAMP WHERE score_id=?",
                (new_attempts, new_resolved, new_rate, score_id),
            )
        else:
            new_attempts = 1
            new_resolved = resolved_increment
            new_rate = float(new_resolved)
            hana_client.execute(
                "INSERT INTO EffectivenessScore (score_id, root_cause, action_type, total_attempts, total_resolved, resolution_rate) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), root_cause, action_type, new_attempts, new_resolved, new_rate),
            )

        logger.info(
            "L3.achieved: effectiveness updated — category=%s, action=%s, resolution_rate=%.4f",
            root_cause, action_type, new_rate,
        )
    except Exception as exc:
        logger.error(
            "L3.missed: effectiveness update failed — category=%s, action=%s, error=%s",
            root_cause, action_type, exc,
        )
        raise
