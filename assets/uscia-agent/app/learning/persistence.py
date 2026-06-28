"""
L1 — Incident persistence to HANA Cloud.
Runs as asyncio.create_task() — must never block M5 report delivery.
"""
from __future__ import annotations
import json
import logging
from evidence.models import Classification, EvidenceGraph, ForensicReport, RemediationAction
from db import hana_client

logger = logging.getLogger(__name__)


async def persist_incident(
    incident_id: str,
    graph: EvidenceGraph,
    classification: Classification,
    report: ForensicReport,
    actions: list,
    planning_version: str = "",
    duration_seconds: int = 0,
) -> str:
    """
    Persist full investigation record to HANA Cloud.
    Writes: IncidentRecord, EvidenceNode (all), EvidenceLink (all),
    FailureClassification, RemediationRecord (all actions).
    Returns incident_id.
    """
    try:
        # IncidentRecord — now includes planning_version and duration_seconds
        hana_client.execute(
            "INSERT INTO IncidentRecord "
            "(incident_id, material, plant, planning_version, incident_type, root_cause, "
            "confidence, report_consultant, report_planner, duration_seconds) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                incident_id,
                getattr(graph, "_material", ""),
                getattr(graph, "_plant", ""),
                planning_version,
                getattr(graph, "_incident_type", ""),
                classification.root_cause,
                classification.confidence,
                report.consultant_view[:32000],
                report.planner_view[:32000],
                duration_seconds,
            ),
        )

        # EvidenceNodes
        for node in graph.nodes:
            hana_client.execute(
                "INSERT INTO EvidenceNode (node_id, incident_id, system_name, status, raw_payload, manual_guidance) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    node.node_id,
                    incident_id,
                    node.system_name,
                    node.status,
                    json.dumps(node.raw_payload) if node.raw_payload else None,
                    node.manual_guidance,
                ),
            )

        # EvidenceLinks
        for link in graph.links:
            hana_client.execute(
                "INSERT INTO EvidenceLink (link_id, incident_id, from_node_id, to_node_id, continuity_key, continuity_val, broken_boundary) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    link.link_id, incident_id, link.from_node_id, link.to_node_id,
                    link.continuity_key, link.continuity_val, link.broken_boundary,
                ),
            )

        # FailureClassification
        import uuid
        hana_client.execute(
            "INSERT INTO FailureClassification (classification_id, incident_id, root_cause, confidence, confirmed_count, probable_count, missing_count, findings) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(uuid.uuid4()), incident_id,
                classification.root_cause, classification.confidence,
                len(classification.confirmed_findings),
                len(classification.probable_findings),
                len(classification.missing_findings),
                json.dumps(classification.confirmed_findings + classification.probable_findings),
            ),
        )

        # RemediationRecords
        for action in actions:
            hana_client.execute(
                "INSERT INTO RemediationRecord (action_id, incident_id, action_type, action_params, requires_approval, rank) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    action.action_id, incident_id,
                    action.action_type,
                    json.dumps(action.action_params),
                    action.requires_approval,
                    action.rank,
                ),
            )

        logger.info(
            "L1.achieved: incident persisted — incident_id=%s, nodes=%d, actions=%d",
            incident_id, len(graph.nodes), len(actions),
        )
    except Exception as exc:
        logger.error("L1.missed: incident persistence failed — incident_id=%s, error=%s", incident_id, exc)

    return incident_id
