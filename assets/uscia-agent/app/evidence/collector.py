"""
Parallel evidence collector — queries all 15 systems simultaneously via asyncio.gather.
NEVER uses sequential fallback; a failing system returns MISSING_DATA, not an abort.

KG system prioritisation:
  When ctx.kg_relevant_systems is non-empty (populated by KG grounding at M1),
  nodes for those systems are tagged kg_priority=True and floated to the front of
  the payload.nodes list. All 15 systems are always queried — priority is ordering
  + tagging only, never filtering.

BDC integration (system 14):
  SAP Business Data Cloud historical analytics (demand history, production order
  history, material master changes) are queried in the same asyncio.gather call.
  The BDC tool degrades gracefully when the SAP_BDC BTP Destination is absent.

IBP Monitor System Tasks (system 15):
  IBP planning job run status — tells the agent whether the IBP heuristic ran,
  when it ran, and whether it failed. Degrades gracefully when IBP not configured.
"""
from __future__ import annotations
import asyncio
import logging
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from s4hana_client import S4Client
    from ibp_client import IBPClient

from evidence.models import EvidenceNode, EvidencePayload, InvestigationContext
from tools.s4_planned_order import get_planned_orders
from tools.s4_material_planning import get_material_planning_data
from tools.s4_pir import get_planned_independent_requirements
from tools.s4_ppds_stock import get_ppds_stock_level
from tools.s4_ppds_constraints import get_ppds_flexible_constraints
from tools.s4_atp import get_atp_check_result
from tools.s4_app_logs import get_application_logs
from tools.s4_bgrfc import get_bgrfc_queue_status
from tools.s4_ppds_config import get_ppds_config_and_mrp_issues
from tools.ibp_supply import get_ibp_supply_data
from tools.cpi_messages import get_cpi_message_status
from tools.pipo_messages import get_pipo_message_status
from tools.cloud_alm import get_cloud_alm_health_events
from tools.bdc_data import get_bdc_supply_chain_analytics
from tools.ibp_job_monitor import get_ibp_job_status

logger = logging.getLogger(__name__)

# Canonical system name order — positional index matches asyncio.gather result list.
_SYSTEM_NAMES = [
    "S4HANA_PLANNED_ORDER",
    "S4HANA_MATERIAL_PLANNING",
    "S4HANA_PIR",
    "S4HANA_PPDS_STOCK",
    "S4HANA_PPDS_CONSTRAINTS",
    "S4HANA_ATP",
    "S4HANA_APPLICATION_LOGS",
    "S4HANA_BGRFC_QUEUE",
    "S4HANA_PPDS_CONFIG",
    "IBP_SUPPLY",
    "SAP_CPI",
    "SAP_PIPO",
    "CLOUD_ALM",
    "SAP_BDC",
    "IBP_JOB_MONITOR",
]


def _apply_kg_priority(nodes: list[EvidenceNode], priority_systems: list[str]) -> list[EvidenceNode]:
    """
    Tag nodes whose system_name appears in priority_systems with kg_priority=True,
    then reorder the list so priority nodes come first (preserving internal order
    within each group).  Non-priority nodes follow in their original order.

    This is purely cosmetic for the narrator/report layer — no system is skipped.
    """
    if not priority_systems:
        return nodes

    priority_set = {s.upper() for s in priority_systems}
    for node in nodes:
        if node.system_name.upper() in priority_set:
            node.kg_priority = True

    priority_nodes = [n for n in nodes if n.kg_priority]
    other_nodes = [n for n in nodes if not n.kg_priority]
    return priority_nodes + other_nodes


async def collect_evidence(
    ctx: InvestigationContext,
    s4: "S4Client | None" = None,
    ibp: "IBPClient | None" = None,
) -> EvidencePayload:
    """
    Issue all 15 system queries in parallel via asyncio.gather(return_exceptions=True).
    Never aborts on a single failure — each system returns AVAILABLE or MISSING_DATA.
    Warns if fewer than 3 systems return AVAILABLE evidence.

    KG prioritisation: when ctx.kg_relevant_systems is non-empty, nodes for those
    systems are tagged kg_priority=True and sorted to the front of the node list.
    SAP BDC is queried as the 14th system for historical analytics context.
    IBP Monitor System Tasks is queried as the 15th system for job run status.
    """
    externid = ctx.continuity_keys.get("externid", "")

    # All 14 coroutines launched simultaneously — no sequential fallback permitted
    results = await asyncio.gather(
        get_planned_orders(ctx.material, ctx.plant, ctx.date_from, ctx.date_to, s4=s4),
        get_material_planning_data(ctx.material, ctx.plant, s4=s4),
        get_planned_independent_requirements(ctx.material, ctx.plant, ctx.planning_version, ctx.date_from, ctx.date_to, s4=s4),
        get_ppds_stock_level(ctx.material, ctx.plant, ctx.date_from, ctx.date_to, s4=s4),
        get_ppds_flexible_constraints(ctx.material, ctx.plant, s4=s4),
        get_atp_check_result(ctx.material, ctx.plant, "1", ctx.date_from, s4=s4),
        get_application_logs(ctx.date_from, ctx.date_to, ctx.material, ctx.plant, s4=s4),
        get_bgrfc_queue_status(ctx.date_from, ctx.date_to, ctx.plant, externid),
        get_ppds_config_and_mrp_issues(ctx.material, ctx.plant, s4=s4),
        get_ibp_supply_data(ctx.material, ctx.plant, ctx.planning_version, ctx.date_from, ctx.date_to, ibp=ibp),
        get_cpi_message_status(ctx.date_from, ctx.date_to, externid, ctx.plant),
        get_pipo_message_status(ctx.date_from, ctx.date_to, ctx.plant),
        get_cloud_alm_health_events(ctx.date_from, ctx.date_to, ctx.plant),
        get_bdc_supply_chain_analytics(ctx.material, ctx.plant, ctx.date_from, ctx.date_to),
        get_ibp_job_status(ctx.date_from, ctx.date_to, ctx.planning_version, ibp=ibp),
        return_exceptions=True,
    )

    nodes: list[EvidenceNode] = []
    available = 0
    unavailable = 0

    for sys_name, result in zip(_SYSTEM_NAMES, results):
        if isinstance(result, Exception):
            node = EvidenceNode(
                node_id=str(uuid.uuid4()),
                system_name=sys_name,
                status="MISSING_DATA",
                raw_payload=None,
                manual_guidance=f"Unexpected error: {result}",
            )
            unavailable += 1
        elif isinstance(result, dict) and result.get("status") == "AVAILABLE":
            node = EvidenceNode(
                node_id=str(uuid.uuid4()),
                system_name=sys_name,
                status="AVAILABLE",
                raw_payload=result.get("data"),
                manual_guidance="",
            )
            available += 1
        else:
            guidance = result.get("guidance", "") if isinstance(result, dict) else str(result)
            node = EvidenceNode(
                node_id=str(uuid.uuid4()),
                system_name=sys_name,
                status="MISSING_DATA",
                raw_payload=None,
                manual_guidance=guidance,
            )
            unavailable += 1
        nodes.append(node)

    insufficient_warning = available < 3
    if insufficient_warning:
        logger.warning(
            "M2: insufficient evidence coverage — only %d of %d systems available",
            available,
            len(_SYSTEM_NAMES),
        )

    # ── KG prioritisation: tag + reorder nodes ────────────────────────────────
    priority_systems = getattr(ctx, "kg_relevant_systems", []) or []
    if priority_systems:
        nodes = _apply_kg_priority(nodes, priority_systems)
        logger.info(
            "M2.kg_priority: reordered evidence nodes — priority_systems=%s",
            priority_systems,
        )

    logger.info(
        "M2.achieved: evidence collected — systems_queried=%d, available=%d, unavailable=%d, "
        "evidence_nodes=%d, bdc_integrated=True, ibp_job_monitor=True, kg_priority_applied=%s",
        len(_SYSTEM_NAMES), available, unavailable, len(nodes),
        bool(priority_systems),
    )

    return EvidencePayload(
        nodes=nodes,
        available_count=available,
        unavailable_count=unavailable,
        insufficient_coverage_warning=insufficient_warning,
        priority_systems=list(priority_systems),
    )
