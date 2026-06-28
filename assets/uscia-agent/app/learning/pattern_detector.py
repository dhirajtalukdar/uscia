"""
L4 — Recurring pattern detection.
Queries HANA Cloud incident history for same material/plant/root_cause within 90 days.
"""
from __future__ import annotations
import logging
from evidence.models import PatternResult
from db import hana_client

logger = logging.getLogger(__name__)

PATTERN_THRESHOLD = 3    # occurrences to flag as recurring
SYSTEMIC_THRESHOLD = 5   # occurrences to flag as systemic


async def detect_patterns(
    material: str,
    plant: str,
    root_cause: str,
    incident_id: str,
) -> PatternResult:
    """
    Query incident history for recurring pattern detection.
    Returns PatternResult with occurrence_count, pattern_flagged, systemic.
    """
    try:
        rows = hana_client.fetchall(
            "SELECT COUNT(*) FROM IncidentRecord "
            "WHERE material = ? AND plant = ? AND root_cause = ? "
            "AND created_at > ADD_DAYS(CURRENT_TIMESTAMP, -90)",
            (material, plant, root_cause),
        )
        count = int(rows[0][0]) if rows else 0
        pattern_flagged = count >= PATTERN_THRESHOLD
        systemic = count >= SYSTEMIC_THRESHOLD

        logger.info(
            "L4.achieved: pattern detection complete — material=%s, plant=%s, occurrences=%d, "
            "pattern_flagged=%s, systemic=%s",
            material, plant, count, pattern_flagged, systemic,
        )
        return PatternResult(
            occurrence_count=count,
            pattern_flagged=pattern_flagged,
            systemic=systemic,
        )
    except Exception as exc:
        logger.error(
            "L4.missed: pattern detection failed — material=%s, plant=%s, error=%s",
            material, plant, exc,
        )
        return PatternResult(occurrence_count=0, pattern_flagged=False, systemic=False)
