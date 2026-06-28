"""
SAP Knowledge Graph Grounding — M1 Context Enrichment

Grounds the user's natural language query in SAP's expert business process
knowledge BEFORE regex-based context extraction runs. This is the KG integration
point described in the SAP Knowledge Graph capability framework:

  1. Understanding Complex Problems  — disambiguates SAP terms, maps to BP hierarchy
  2. Decision-Making                 — identifies the relevant system chain for this incident
  3. Reasoning & Sharing Findings   — injects process context into the LLM narration prompt
  4. Executing Resolutions           — enriches remediation actions with BP-level routing (Phase 4)

Two-tier implementation:
  LIVE     — POST to SAP Knowledge Graph BP Mapping API via BTP Destination 'SAP_KG'
  FALLBACK — Curated local SAP supply chain process knowledge map (always available)

The fallback is NOT a stub. It contains production-grade SAP supply chain
process knowledge for all 10 USCIA incident types — it provides meaningful
grounding even when the live KG API is not yet configured.

BTP Destination required for live mode:
  Name:            SAP_KG   (override via KG_DESTINATION_NAME env var)
  Type:            HTTP
  URL:             https://<kg-endpoint>
  Authentication:  OAuth2ClientCredentials
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ── SAP term disambiguation map ───────────────────────────────────────────────
# Maps colloquial SAP terms, transaction codes, and acronyms to their
# functional descriptions. Used to enrich the LLM narration prompt so the
# LLM understands what the user meant — not what they typed.
_SAP_TERM_MAP: dict[str, str] = {
    "rrp3": "PP/DS Planning Board (/SAPAPO/RRP3)",
    "/sapapo/rrp3": "PP/DS Planning Board",
    "md04": "MRP Stock/Requirements List (MD04)",
    "md01": "MRP Total Planning Run (MD01)",
    "md01n": "MRP Single-Item Multi-Level Run (MD01N)",
    "md61": "Create Planned Independent Requirements (MD61)",
    "md62": "Change Planned Independent Requirements (MD62)",
    "sm58": "bgRFC/tRFC Queue Monitor (SM58)",
    "smq1": "qRFC Outbound Queue Monitor (SMQ1)",
    "sxmb_moni": "CPI/XI Integration Engine Monitor (SXMB_MONI)",
    "slg1": "Application Log Display (SLG1)",
    "mm02": "Change Material Master (MM02)",
    "mm03": "Display Material Master (MM03)",
    "co09": "ATP Check and Product Allocation (CO09)",
    "curto_simu": "CIF Integration Model Simulation (CURTO_SIMU)",
    "/sapapo/cif": "CIF Integration Model Management (/SAPAPO/CIF)",
    "bgrfc": "Background Remote Function Call (bgRFC) — SAP async integration queue",
    "cif": "Core Interface (CIF) — transfers planned orders from S/4HANA MRP to PP/DS",
    "rti": "Real-Time Integration (RTI) — transfers IBP supply output to S/4HANA",
    "cpi": "SAP Cloud Platform Integration (CPI) — message routing layer between IBP and S/4HANA",
    "ibp": "SAP Integrated Business Planning — demand/supply planning system",
    "ppds": "Production Planning and Detailed Scheduling (PP/DS) — embedded in S/4HANA",
    "mrp": "Material Requirements Planning — generates planned orders in S/4HANA",
    "pir": "Planned Independent Requirements (PIR) — demand input for MRP",
    "atp": "Advanced Available-to-Promise (aATP) — supply confirmation check",
    "externid": "IBP External ID (EXTERNID) — continuity key linking IBP supply objects to S/4HANA",
    "rfc": "Remote Function Call — SAP integration mechanism",
    "apocif": "APO Core Interface log object — CIF transfer audit trail in SLG1",
}

# ── Incident type detection patterns ─────────────────────────────────────────
# Ordered from most specific to most general. First match wins.
_INCIDENT_PATTERNS: list[tuple[str, list[str]]] = [
    ("bgRFC queue blockage", [
        "bgrfc", "sm58", "queue block", "queue stuck", "smq1", "bgrfc block",
        "bgrfc error", "queue not processing", "stuck in queue",
    ]),
    ("RTI/CPI message failure", [
        "rti", "cpi message", "sxmb_moni", "integration message", "message fail",
        "cpi fail", "message not process", "integration fail", "message error",
    ]),
    ("CIF transfer failure", [
        "cif fail", "cif error", "cif transfer", "not transferred to pp",
        "core interface", "apocif", "/sapapo/cif", "curto_simu",
    ]),
    ("PP/DS scheduling failure", [
        "scheduling fail", "not scheduled", "capacity issue", "constraint fail",
        "scheduling error", "cannot schedule", "failed to schedule",
        "pp/ds scheduling", "scheduling heuristic",
    ]),
    ("planned order not reaching PP/DS RRP3", [
        "rrp3", "pp/ds", "ppds", "not reaching pp", "not in rrp",
        "not transferred to pp", "not visible in pp/ds", "rpp3",
        "not scheduled in pp", "pp/ds empty",
    ]),
    ("aATP confirmation missing or incorrect", [
        "atp", "confirmation missing", "available to promise", "product allocation",
        "confirmation wrong", "atp fail", "aatp", "co09",
    ]),
    ("IBP planning job failure", [
        "ibp job", "planning job fail", "ibp run fail", "planning run fail",
        "ibp fail", "ibp planning fail", "no supply output", "ibp job fail",
        "did not complete", "job did not", "planning job did", "ibp did not",
    ]),
    ("PIR exists but no planned order created", [
        "pir", "planned independent requirement", "demand exists", "pir exists",
        "independent requirement", "no planned order created", "md61", "md62",
    ]),
    ("quantity or date inconsistency between IBP and S/4HANA", [
        "wrong quantity", "wrong date", "inconsistent", "mismatch",
        "different quantity", "different date", "quantity mismatch",
        "date mismatch", "quantity difference", "discrepancy",
    ]),
    ("planned order missing in MD04", [
        "missing in md04", "not in md04", "no planned order", "missing planned order",
        "md04 empty", "not showing in md04", "not appearing in md04",
        "not visible in md04", "planned order not found",
    ]),
]

# ── Priority system chain per incident type ───────────────────────────────────
# Defines which systems are MOST relevant for each incident type.
# All 12 systems are still queried in parallel — this ordering tells the
# LLM narration layer which evidence to focus on in the report.
_INCIDENT_SYSTEMS: dict[str, list[str]] = {
    "planned order missing in MD04": [
        "IBP_SUPPLY", "SAP_CPI", "S4HANA_BGRFC_QUEUE",
        "S4HANA_PLANNED_ORDER", "S4HANA_MATERIAL_PLANNING", "S4HANA_PIR",
    ],
    "planned order not reaching PP/DS RRP3": [
        "S4HANA_PLANNED_ORDER", "S4HANA_PPDS_STOCK", "S4HANA_PPDS_CONFIG",
        "S4HANA_APPLICATION_LOGS", "S4HANA_PPDS_CONSTRAINTS",
    ],
    "quantity or date inconsistency between IBP and S/4HANA": [
        "IBP_SUPPLY", "S4HANA_PLANNED_ORDER", "S4HANA_MATERIAL_PLANNING", "SAP_CPI",
    ],
    "PIR exists but no planned order created": [
        "S4HANA_PIR", "S4HANA_PLANNED_ORDER", "S4HANA_MATERIAL_PLANNING", "IBP_SUPPLY",
    ],
    "PP/DS scheduling failure": [
        "S4HANA_PPDS_STOCK", "S4HANA_PPDS_CONSTRAINTS", "S4HANA_PPDS_CONFIG",
        "S4HANA_PLANNED_ORDER", "S4HANA_APPLICATION_LOGS",
    ],
    "aATP confirmation missing or incorrect": [
        "S4HANA_ATP", "S4HANA_PLANNED_ORDER",
    ],
    "CIF transfer failure": [
        "S4HANA_PLANNED_ORDER", "S4HANA_PPDS_STOCK",
        "S4HANA_APPLICATION_LOGS", "S4HANA_PPDS_CONFIG",
    ],
    "IBP planning job failure": [
        "IBP_SUPPLY", "S4HANA_PIR", "S4HANA_PLANNED_ORDER",
    ],
    "RTI/CPI message failure": [
        "SAP_CPI", "IBP_SUPPLY", "S4HANA_PLANNED_ORDER", "S4HANA_BGRFC_QUEUE",
    ],
    "bgRFC queue blockage": [
        "S4HANA_BGRFC_QUEUE", "S4HANA_PLANNED_ORDER", "SAP_CPI",
    ],
}

# ── SAP process (BP hierarchy) context per incident type ─────────────────────
# Derived from SAP Reference Business Architecture (RBA).
# BPS-327 = Align demand, supply and financial plans (IBP layer)
# BPS-349 = Perform production planning and scheduling (S/4HANA MRP / PP/DS layer)
# This context is injected into the LLM narration prompt so the LLM can
# reason about process boundaries, not just API field values.
_INCIDENT_BP_CONTEXT: dict[str, str] = {
    "planned order missing in MD04": (
        "SAP RBA: Plan to Fulfill → BPS-327 (demand/supply alignment) + BPS-349 (production planning). "
        "Integration chain: IBP supply output → RTI/CPI message → S/4HANA bgRFC → MRP update → MD04. "
        "Key diagnostic boundary: IBP→RTI (supply objects) → CPI→S4 (message delivery) → bgRFC→MRP (processing)."
    ),
    "planned order not reaching PP/DS RRP3": (
        "SAP RBA: Plan to Fulfill → BPS-349 (production planning and scheduling). "
        "Integration chain: S/4HANA MRP planned order (MD04) → CIF integration model → PP/DS scheduling board (RRP3). "
        "Key diagnostic boundary: S4 MRP→CIF (integration model active?) → CIF→PP/DS (qRFC queue SMQ1). "
        "Critical manual check: MM02 → MRP 2 tab → Advanced Planning checkbox (MARC-MTVFP) not available via OData."
    ),
    "quantity or date inconsistency between IBP and S/4HANA": (
        "SAP RBA: Plan to Fulfill → BPS-327 (demand/supply alignment). "
        "Integration chain: IBP planning version key figures → RTI transfer mapping → S/4HANA MRP lot size / horizon. "
        "Key diagnostic boundary: IBP version/horizon settings vs. S/4HANA lot size key and planning horizon (MM02 MRP1)."
    ),
    "PIR exists but no planned order created": (
        "SAP RBA: Plan to Fulfill → BPS-349 (production planning). "
        "Process chain: PIR in MD61/MD62 → MRP run (MD01N) → planned order creation in MD04. "
        "Key diagnostic boundary: MRP type configuration (MM02 MRP1 tab) → MRP run execution → lot size / reorder point."
    ),
    "PP/DS scheduling failure": (
        "SAP RBA: Plan to Fulfill → BPS-349 (production planning and scheduling). "
        "Process chain: Planned order in S/4HANA → CIF transfer → PP/DS order receipt → scheduling heuristic (RRP3). "
        "Key diagnostic boundary: PP/DS capacity constraints, flexible constraints, work center availability. "
        "Critical manual check: ProductionSchedulingProfile (MM02 → MRP 2 tab, MARC-FEVOR field)."
    ),
    "aATP confirmation missing or incorrect": (
        "SAP RBA: Plan to Fulfill → BPS-349. "
        "Process chain: Supply order → aATP check rule (CO09) → product allocation scope → confirmation. "
        "Key diagnostic boundary: aATP check rule assignment and product allocation object coverage for this material/plant."
    ),
    "CIF transfer failure": (
        "SAP RBA: Plan to Fulfill → BPS-349. "
        "Process chain: S/4HANA MRP planned order → CIF integration model → PP/DS qRFC queue (SMQ1) → PP/DS order. "
        "Key diagnostic boundary: CIF integration model active (CURTO_SIMU) → SLG1 APOCIF errors → SMQ1 queue status. "
        "Critical manual check: MM02 → MRP 2 → Advanced Planning checkbox (MARC-MTVFP)."
    ),
    "IBP planning job failure": (
        "SAP RBA: Plan to Fulfill → BPS-327 (demand/supply alignment). "
        "Process chain: IBP demand key figures → supply planning job → supply output → RTI transfer. "
        "Key diagnostic boundary: IBP planning job execution status, version, planning horizon, and key figure availability."
    ),
    "RTI/CPI message failure": (
        "SAP RBA: Plan to Fulfill → BPS-327 (IBP→S4HANA integration chain). "
        "Integration chain: IBP supply output (EXTERNID) → RTI → CPI pipeline → S/4HANA inbound processing. "
        "Key diagnostic boundary: CPI message status (SXMB_MONI) → inbound adapter → bgRFC queue (SM58)."
    ),
    "bgRFC queue blockage": (
        "SAP RBA: Plan to Fulfill → BPS-327 + BPS-349. "
        "Integration chain: CPI message delivered to S/4HANA → bgRFC queue entry → MRP processing → MD04 update. "
        "Key diagnostic boundary: bgRFC queue status (SM58) — look for SYSFAIL or CPICERR on APOC/RSMPP queues."
    ),
}


@dataclass
class KGGroundingResult:
    """
    Enriched investigation context from SAP Knowledge Graph grounding.
    Injected into M1 context extraction and M4/M5 LLM narration.
    """
    incident_type: str
    relevant_systems: list[str] = field(default_factory=list)
    process_context: str = ""
    disambiguated_terms: dict[str, str] = field(default_factory=dict)
    confidence: str = "MEDIUM"        # HIGH (KG live) | MEDIUM (fallback keyword) | LOW (default)
    fallback_used: bool = True
    kg_bp_ids: list[str] = field(default_factory=list)   # e.g. ["BPS-327", "BPS-349"]
    kg_summary: str = ""              # Human-readable KG routing summary


def _disambiguate_terms(query: str) -> dict[str, str]:
    """
    Scan the query for known SAP terms and return their functional descriptions.
    Used to enrich the LLM narration so it understands what the user meant.
    """
    q_lower = query.lower()
    return {
        term: description
        for term, description in _SAP_TERM_MAP.items()
        if term in q_lower
    }


def _detect_incident_type_local(query: str) -> tuple[str, str]:
    """
    Detect incident type from query using curated keyword patterns.
    Returns (incident_type, confidence: HIGH | MEDIUM | LOW).
    Ordered from most specific to most general — first match wins.
    """
    q_lower = query.lower()
    for incident_type, keywords in _INCIDENT_PATTERNS:
        if any(kw in q_lower for kw in keywords):
            return incident_type, "MEDIUM"
    return "planned order missing in MD04", "LOW"


def _map_kg_response_to_incident(kg_response: dict) -> tuple[str, list[str], str]:
    """
    Map the SAP Knowledge Graph BP Mapping response to a USCIA incident type.

    The KG response contains sub_processes with BP IDs (BPS-327, BPS-349) and
    a routing summary. We use these to determine the incident type and provide
    the process context for the LLM narration.

    Returns (incident_type, kg_bp_ids, kg_summary).
    """
    bp_ids: list[str] = []
    kg_summary = kg_response.get("summary", "") or kg_response.get("message", "")

    try:
        sub_processes = kg_response.get("sub_processes", [])
        for sp in sub_processes:
            bp_id = sp.get("id", "")
            if bp_id:
                bp_ids.append(bp_id)

        # Also check top_ord_ids if this is a discover-style response
        top_ord_ids = kg_response.get("top_ord_ids", [])
    except Exception:
        pass

    # Map BP IDs to incident types using SAP RBA hierarchy
    # BPS-327 = demand/supply alignment = IBP/CPI layer incidents
    # BPS-349 = production planning/scheduling = MRP/PP/DS layer incidents
    has_327 = "BPS-327" in bp_ids
    has_349 = "BPS-349" in bp_ids

    if has_327 and not has_349:
        return "RTI/CPI message failure", bp_ids, kg_summary
    if has_349 and not has_327:
        return "planned order not reaching PP/DS RRP3", bp_ids, kg_summary
    if has_327 and has_349:
        # Both process layers involved — most likely a cross-boundary failure
        return "planned order missing in MD04", bp_ids, kg_summary

    # If no BP IDs matched, use the summary text for keyword detection
    if kg_summary:
        incident_type, _ = _detect_incident_type_local(kg_summary)
        return incident_type, bp_ids, kg_summary

    return "planned order missing in MD04", bp_ids, kg_summary


async def _call_kg_api(query: str) -> dict | None:
    """
    Call SAP Knowledge Graph BP Mapping API via BTP Destination 'SAP_KG'.

    Follows the same BTP Destination pattern as S4Client and IBPClient.
    Returns the raw KG response dict, or None if not configured / unavailable.
    Raises nothing — all failures result in fallback mode.
    """
    try:
        from s4hana_client import _first_binding, _DestinationResolver
        import httpx

        dest_name = os.environ.get("KG_DESTINATION_NAME", "SAP_KG")

        if not _first_binding("destination"):
            logger.debug("KG grounding: no BTP destination binding — using local fallback")
            return None

        resolver = _DestinationResolver(timeout=10.0)

        try:
            dest = await resolver.resolve(dest_name)
        except Exception as resolve_exc:
            logger.debug(
                "KG grounding: destination '%s' not found (%s) — using local fallback",
                dest_name, resolve_exc,
            )
            return None

        # SAP Knowledge Graph BP Mapping endpoint
        # The endpoint accepts a natural language business challenge and returns
        # the SAP RBA process hierarchy (E2E, phases, sub-processes with BP IDs).
        kg_url = f"{dest.url}/api/v1/bp-mapping"

        async with httpx.AsyncClient(timeout=10.0) as http:
            r = await http.post(
                kg_url,
                json={"query": query},
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )

        if r.status_code < 400:
            logger.info("KG grounding: live API call succeeded (HTTP %s)", r.status_code)
            return r.json()

        logger.debug(
            "KG grounding: API returned HTTP %s — using local fallback", r.status_code
        )
        return None

    except Exception as exc:
        logger.debug("KG grounding: API call failed (%s) — using local fallback", exc)
        return None


async def ground_investigation_context(query: str) -> KGGroundingResult:
    """
    Ground the user's natural language query in SAP process knowledge.

    This is the KG integration point for M1. It runs BEFORE regex-based
    context extraction so that the investigation starts with an accurate
    incident type and system chain — not a regex guess.

    Priority order:
      1. Live SAP Knowledge Graph API (via BTP Destination 'SAP_KG')
      2. Local curated SAP process knowledge map

    Never raises — always returns a KGGroundingResult.
    Times out in 10 seconds — well within M1 budget.
    """
    disambiguated = _disambiguate_terms(query)

    # ── Try live KG API first ─────────────────────────────────────────────────
    kg_response = await _call_kg_api(query)

    if kg_response:
        incident_type, kg_bp_ids, kg_summary = _map_kg_response_to_incident(kg_response)
        relevant_systems = _INCIDENT_SYSTEMS.get(incident_type, [])
        process_context = _INCIDENT_BP_CONTEXT.get(incident_type, "")

        logger.info(
            "KG.grounding: live — incident_type=%s, bp_ids=%s, systems=%d",
            incident_type, kg_bp_ids, len(relevant_systems),
        )
        return KGGroundingResult(
            incident_type=incident_type,
            relevant_systems=relevant_systems,
            process_context=process_context,
            disambiguated_terms=disambiguated,
            confidence="HIGH",
            fallback_used=False,
            kg_bp_ids=kg_bp_ids,
            kg_summary=kg_summary,
        )

    # ── Local fallback ────────────────────────────────────────────────────────
    incident_type, confidence = _detect_incident_type_local(query)
    relevant_systems = _INCIDENT_SYSTEMS.get(incident_type, [])
    process_context = _INCIDENT_BP_CONTEXT.get(incident_type, "")

    logger.info(
        "KG.grounding: fallback — incident_type=%s, confidence=%s, systems=%d, "
        "terms_disambiguated=%d",
        incident_type, confidence, len(relevant_systems), len(disambiguated),
    )
    return KGGroundingResult(
        incident_type=incident_type,
        relevant_systems=relevant_systems,
        process_context=process_context,
        disambiguated_terms=disambiguated,
        confidence=confidence,
        fallback_used=True,
        kg_bp_ids=[],
        kg_summary="",
    )
