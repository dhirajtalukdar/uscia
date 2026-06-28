"""
Parallel evidence collector — queries all 12 systems simultaneously via asyncio.gather.
NEVER uses sequential fallback; a failing system returns MISSING_DATA, not an abort.
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

logger = logging.getLogger(__name__)


async def collect_evidence(
    ctx: InvestigationContext,
    s4: "S4Client | None" = None,
    ibp: "IBPClient | None" = None,
) -> EvidencePayload:
    """
    Issue all 12 system queries in parallel via asyncio.gather(return_exceptions=True).
    Never aborts on a single failure — each system returns AVAILABLE or MISSING_DATA.
    Warns if fewer than 3 systems return AVAILABLE evidence.
    """
    externid = ctx.continuity_keys.get("externid", "")

    # All 12 coroutines launched simultaneously — no sequential fallback permitted
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
        return_exceptions=True,
    )

    system_names = [
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
    ]

    nodes: list[EvidenceNode] = []
    available = 0
    unavailable = 0

    for sys_name, result in zip(system_names, results):
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
            len(system_names),
        )

    logger.info(
        "M2.achieved: evidence collected — systems_queried=%d, available=%d, unavailable=%d, evidence_nodes=%d",
        len(system_names), available, unavailable, len(nodes),
    )

    return EvidencePayload(
        nodes=nodes,
        available_count=available,
        unavailable_count=unavailable,
        insufficient_coverage_warning=insufficient_warning,
    )
