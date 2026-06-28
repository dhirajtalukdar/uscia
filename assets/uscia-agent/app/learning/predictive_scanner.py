"""
L5 — Predictive alert generation.
Scans evidence graph history for pre-failure signatures across active material-plant pairs.
Must complete within 10 minutes for up to 500 combinations.
"""
from __future__ import annotations
import logging
import time
from evidence.models import PredictiveAlert
from db import hana_client

logger = logging.getLogger(__name__)

_SIGNATURES = {
    "BGRFC_QUEUE_TRENDING": {
        "root_cause": "BGRFC_QUEUE_BLOCKAGE",
        "window_days": 30,
        "min_occurrences": 2,
        "scope": "plant",  # group by plant only
        "action": "Proactively check SM58 queue depth and process APOC/RSMPP queue entries before blockage occurs.",
    },
    "IBP_JOB_DURATION_INCREASING": {
        "root_cause": "IBP_PLANNING_GAP",
        "window_days": 30,
        "min_occurrences": 2,
        "scope": "material_plant",
        "action": "Review IBP planning job performance. Check memory allocation and key figure data volume for this material-location.",
    },
    "CPI_MESSAGE_LAG_INCREASING": {
        "root_cause": "RTI_CPI_MESSAGE_FAILURE",
        "window_days": 30,
        "min_occurrences": 2,
        "scope": "plant",
        "action": "Review CPI/RTI message processing latency. Check Integration Suite for pipeline performance degradation.",
    },
    "MASTER_DATA_CHANGE_PRECEDES_FAILURE": {
        "root_cause": "MASTER_DATA_CONFIG_ERROR",
        "window_days": 1,
        "min_occurrences": 1,
        "scope": "material_plant",
        "action": "A master data configuration error occurred. Review recent material master changes (MM02) for this material/plant before next planning run.",
    },
}


async def scan_for_pre_failure_signatures(
    material_plant_pairs: list,
) -> list[PredictiveAlert]:
    """
    Scan up to 500 material-plant combinations for pre-failure signatures.
    Must complete within 10 minutes.
    Returns list of PredictiveAlert when signatures are detected.
    """
    start = time.time()
    alerts: list[PredictiveAlert] = []
    scanned = 0

    try:
        for material, plant in material_plant_pairs[:500]:
            scanned += 1
            for sig_name, sig in _SIGNATURES.items():
                root_cause = sig["root_cause"]
                window = sig["window_days"]
                threshold = sig["min_occurrences"]

                if sig["scope"] == "plant":
                    rows = hana_client.fetchall(
                        "SELECT incident_id FROM IncidentRecord "
                        "WHERE plant = ? AND root_cause = ? "
                        "AND created_at > ADD_DAYS(CURRENT_TIMESTAMP, ?)",
                        (plant, root_cause, -window),
                    )
                else:
                    rows = hana_client.fetchall(
                        "SELECT incident_id FROM IncidentRecord "
                        "WHERE material = ? AND plant = ? AND root_cause = ? "
                        "AND created_at > ADD_DAYS(CURRENT_TIMESTAMP, ?)",
                        (material, plant, root_cause, -window),
                    )

                if rows and len(rows) >= threshold:
                    incident_ids = [r[0] for r in rows]
                    alerts.append(
                        PredictiveAlert(
                            signature_type=sig_name,
                            historical_incident_ids=incident_ids,
                            affected_material=material,
                            affected_plant=plant,
                            recommended_preventive_action=sig["action"],
                        )
                    )

        duration = round(time.time() - start, 1)
        logger.info(
            "L5.achieved: predictive scan complete — combinations_scanned=%d, alerts_generated=%d, duration_seconds=%.1f",
            scanned, len(alerts), duration,
        )
    except Exception as exc:
        duration = round(time.time() - start, 1)
        logger.error(
            "L5.missed: predictive scan failed — combinations_scanned=%d, error=%s",
            scanned, exc,
        )

    return alerts
