"""
LLM Narration Layer.
Uses GPT-4o via SAP AI Core Generative AI Hub (ChatLiteLLM).
Falls back to highest-capability available model if GPT-4o is unavailable.
LLM receives ONLY structured evidence output -- it NEVER generates findings independently.
"""
from __future__ import annotations
import json
import logging
from evidence.models import (
    Classification,
    EvidenceGraph,
    InvestigationContext,
    NarrationResult,
)

logger = logging.getLogger(__name__)

# Key systems per incident type -- tells LLM which evidence matters most
_INCIDENT_KEY_SYSTEMS = {
    "planned order missing in MD04": [
        "S4HANA_PLANNED_ORDER", "S4HANA_MATERIAL_PLANNING", "S4HANA_PIR",
        "IBP_SUPPLY", "S4HANA_BGRFC_QUEUE", "SAP_CPI"
    ],
    "planned order not reaching PP/DS RRP3": [
        "S4HANA_PLANNED_ORDER", "S4HANA_PPDS_STOCK", "S4HANA_PPDS_CONSTRAINTS",
        "S4HANA_APPLICATION_LOGS"
    ],
    "quantity or date inconsistency between IBP and S/4HANA": [
        "IBP_SUPPLY", "S4HANA_PLANNED_ORDER", "S4HANA_MATERIAL_PLANNING"
    ],
    "PIR exists but no planned order created": [
        "S4HANA_PIR", "S4HANA_PLANNED_ORDER", "S4HANA_MATERIAL_PLANNING"
    ],
    "PP/DS scheduling failure": [
        "S4HANA_PPDS_STOCK", "S4HANA_PPDS_CONSTRAINTS", "S4HANA_PLANNED_ORDER",
        "S4HANA_APPLICATION_LOGS"
    ],
    "aATP confirmation missing or incorrect": [
        "S4HANA_ATP", "S4HANA_PLANNED_ORDER"
    ],
    "CIF transfer failure": [
        "S4HANA_PLANNED_ORDER", "S4HANA_PPDS_STOCK", "S4HANA_APPLICATION_LOGS"
    ],
    "IBP planning job failure": [
        "IBP_SUPPLY", "S4HANA_PIR"
    ],
    "RTI/CPI message failure": [
        "SAP_CPI", "IBP_SUPPLY", "S4HANA_PLANNED_ORDER", "S4HANA_BGRFC_QUEUE"
    ],
    "bgRFC queue blockage": [
        "S4HANA_BGRFC_QUEUE", "S4HANA_PLANNED_ORDER", "SAP_CPI"
    ],
}


_SYSTEM_PROMPT = """You are a senior SAP supply chain forensic consultant. You are responding directly to a user who described a specific problem. Your report must:

1. ACKNOWLEDGE THE USER'S STATED SCENARIO FIRST — start by repeating back what the user said they observed, then compare it to what the evidence shows.

2. SURFACE CONTRADICTIONS EXPLICITLY — if the user says "PP/DS received the order" but evidence shows no orders in PP/DS, say this clearly:
   "You mentioned that the order reached PP/DS scheduling. However, our live evidence shows no planned orders in MD04 and no scheduling records in PP/DS for material X, plant Y. This contradiction has two possible explanations: (a) the order may exist in a date range outside our query window — please provide the planned order number to narrow the search, or (b) the order was recently deleted or consumed."

3. ASK FOLLOW-UP QUESTIONS when:
   - User mentioned a specific order but didn't provide the number → ask for it
   - Evidence found multiple planned orders → ask which one they're investigating
   - Evidence contradicts user's stated context → ask for clarification before concluding
   Format follow-up questions as: "To investigate further, could you provide: [specific question]?"

4. CITE ACTUAL DATA — state what was found, not "systems affected":
   - 0 records → "No planned orders found in MD04 for material X, plant Y in the queried date range"
   - MRPType found → "Material master shows MRP Type PD — make-to-stock planning is configured"
   - bgRFC entries → describe the actual event types found and whether any relate to this material

5. CONSULTANT VIEW: Technical, specific field values, SAP transactions, diagnostic chain.
6. PLANNER VIEW: 2-3 sentences max per section. Plain English. What is wrong, what is the impact, what to do.
7. All 14 sections mandatory. Plain text only in JSON values.
"""

_14_SECTIONS = [
    "executive_summary",
    "issue_classification",
    "affected_system_boundary",
    "evidence_timeline",
    "evidence_graph_summary",
    "confirmed_findings",
    "probable_root_causes",
    "missing_data_gaps",
    "recommended_actions",
    "sap_objects_to_check",
    "logs_and_transactions",
    "business_impact",
    "escalation_path",
    "preventive_recommendation",
]


def _build_evidence_payload(
    classification: Classification,
    graph: EvidenceGraph,
    ctx: InvestigationContext,
) -> str:
    """Build a structured JSON evidence payload for the LLM.
    Extracts system-specific diagnostic fields so the LLM can cite real data values.
    """

    def _extract_key_facts(n) -> dict:
        entry: dict = {"system": n.system_name, "status": n.status}
        if n.status != "AVAILABLE" or not n.raw_payload:
            entry["guidance"] = n.manual_guidance[:300]
            return entry

        payload = n.raw_payload
        if isinstance(payload, str):
            try:
                import json as _j
                payload = _j.loads(payload)
            except Exception:
                entry["raw"] = str(payload)[:200]
                return entry
        if not isinstance(payload, dict):
            return entry

        items = (payload.get("value") or payload.get("results") or
                 payload.get("data") or payload.get("SupplyOrders") or [])
        count = len(items) if isinstance(items, list) else 0
        entry["record_count"] = count
        first = items[0] if isinstance(items, list) and items else {}

        if count == 0:
            entry["finding"] = "No records returned for this material/plant in queried date range."
            return entry

        if n.system_name == "S4HANA_PLANNED_ORDER":
            entry["planned_order_count"] = count
            entry["sample"] = {k: first.get(k) for k in
                ["PlannedOrder", "TotalQuantity", "ScheduledBasicStartDate",
                 "ScheduledBasicEndDate", "PlannedOrderIsFirm", "MRPController"]
                if first.get(k) is not None}

        elif n.system_name == "S4HANA_MATERIAL_PLANNING":
            entry["mrp_rows"] = count
            entry["mrp_data"] = {k: first.get(k) for k in
                ["Material", "MRPPlant", "MRPType", "MRPTypeName", "MRPController",
                 "LotSizingProcedure", "ReorderThresholdQuantity", "SafetyStockQuantity",
                 "MaterialPlannedDeliveryDurn", "PlanningTimeFenceInDays"]
                if first.get(k) is not None}

        elif n.system_name == "S4HANA_PIR":
            entry["pir_count"] = count
            entry["sample"] = {k: first.get(k) for k in
                ["Product", "Plant", "PlndIndepRqmtType", "PlndIndepRqmtVersion"]
                if first.get(k) is not None}

        elif n.system_name == "S4HANA_PPDS_STOCK":
            entry["stock_entries"] = count

        elif n.system_name == "S4HANA_PPDS_CONSTRAINTS":
            entry["constraint_count"] = count
            entry["sample"] = {k: first.get(k) for k in
                ["AdvncdPlngFlxCnsKey", "AdvncdPlngFlxCnsMinQty",
                 "AdvncdPlngFlxCnsMaxQty", "AdvncdPlngFlxCnsObslt"]
                if first.get(k) is not None}

        elif n.system_name == "S4HANA_ATP":
            entry["atp_entries"] = count
            entry["sample"] = {k: first.get(k) for k in
                ["ProductAllocationObject", "ProductAllocationQuantity",
                 "ProdAllocAssignedQuantity", "ProdAllocLoadCriticality"]
                if first.get(k) is not None}

        elif n.system_name == "S4HANA_APPLICATION_LOGS":
            entry["log_entries"] = count
            if isinstance(items, list):
                from collections import Counter
                sev = Counter(i.get("Severity", "unknown") for i in items)
                entry["severity_counts"] = dict(sev)
                entry["objects_found"] = list({i.get("Object") for i in items if i.get("Object")})

        elif n.system_name == "S4HANA_BGRFC_QUEUE":
            entry["queue_entries"] = count
            entry["sample"] = {k: first.get(k) for k in
                ["BusinessEvent", "SAPObjectType", "BusEventPriority"]
                if first.get(k) is not None}

        return entry

    node_details = [_extract_key_facts(n) for n in graph.nodes]

    return json.dumps({
        "investigation_context": {
            "material": ctx.material,
            "plant": ctx.plant,
            "planning_version": ctx.planning_version,
            "date_from": ctx.date_from,
            "date_to": ctx.date_to,
            "incident_type": ctx.incident_type,
        },
        "deterministic_classification": {
            "root_cause": classification.root_cause,
            "confidence": classification.confidence,
            "rule_id": classification.rule_id,
            "description": classification.description,
        },
        "confirmed_findings": classification.confirmed_findings,
        "probable_findings": classification.probable_findings,
        "missing_findings": classification.missing_findings,
        "broken_boundaries": graph.broken_boundaries,
        "system_evidence": node_details,
        "remediation_actions": [
            {
                "action_type": a.action_type,
                "action_params": a.action_params,
                "requires_approval": a.requires_approval,
                "rank": a.rank,
            }
            for a in classification.remediation_actions
        ],
    }, indent=2)


def _fallback_narration(classification: Classification, ctx: InvestigationContext) -> NarrationResult:
    """Minimal structured narration when LLM is unavailable.

    Returns empty section dicts so report/generator.py's _auto_section() fires
    for each section individually, producing section-appropriate content rather
    than dumping the entire findings list identically into all 14 sections.
    """
    return NarrationResult(
        consultant_sections={},
        planner_sections={},
        fallback_used=True,
    )


async def narrate_findings(
    classification: Classification,
    graph: EvidenceGraph,
    ctx: InvestigationContext,
    llm=None,
    user_query: str = "",
) -> NarrationResult:
    """
    Generate Consultant and Planner view narrations via SAP AI Core LLM.
    Accepts an already-initialised LangChain BaseChatModel (gen_ai_hub on CF,
    ChatLiteLLM on Joule). Falls back to deterministic narration if no LLM provided
    or if the LLM call fails.
    """
    if llm is None:
        logger.warning("No LLM provided to narrate_findings -- using deterministic fallback")
        return _fallback_narration(classification, ctx)

    logger.info("narrate_findings: LLM type=%s, methods=%s",
                type(llm).__name__,
                [m for m in ['invoke', 'ainvoke', 'predict', 'apredict', '__call__'] if hasattr(llm, m)])

    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        evidence_json = _build_evidence_payload(classification, graph, ctx)

        # Incident-type focus hint
        key_systems = _INCIDENT_KEY_SYSTEMS.get(ctx.incident_type, [])
        focus_hint = ""
        if key_systems:
            func_names = {
                "S4HANA_PLANNED_ORDER": "Planned Orders in MD04",
                "S4HANA_MATERIAL_PLANNING": "Material Master MRP config (MM02/MM03)",
                "S4HANA_PIR": "Planned Independent Requirements (PIR)",
                "S4HANA_PPDS_STOCK": "PP/DS resource utilization",
                "S4HANA_PPDS_CONFIG": "Material Master MRP Issues & PP/DS configuration",
                "S4HANA_APPLICATION_LOGS": "SLG1 CIF/APOCIF transfer logs",
                "S4HANA_BGRFC_QUEUE": "bgRFC/BEH queue status",
                "S4HANA_ATP": "Product Allocation / aATP",
                "IBP_SUPPLY": "IBP Supply Planning",
                "SAP_CPI": "CPI/RTI message routing (SXMB_MONI)",
            }
            focus_names = [func_names.get(s, s) for s in key_systems]
            focus_hint = f"\nFor '{ctx.incident_type}', the key diagnostic areas are: {', '.join(focus_names)}."

        # ── KG Process Context injection ──────────────────────────────────────
        # If KG grounding ran at M1, inject the SAP RBA process chain and
        # disambiguated terms into the prompt so the LLM reasons about the
        # correct process boundary — not just raw API field values.
        kg_context_block = ""
        if ctx.kg_process_context:
            kg_source = "SAP Knowledge Graph (live)" if not ctx.kg_fallback_used else "SAP process knowledge (local)"
            kg_context_block = (
                f"\nSAP Process Context (from {kg_source}):\n"
                f"{ctx.kg_process_context}\n"
            )
            if ctx.kg_bp_ids:
                kg_context_block += f"Business Process IDs: {', '.join(ctx.kg_bp_ids)}\n"
            if ctx.kg_disambiguated_terms:
                terms_str = "; ".join(
                    f"{k} = {v}" for k, v in list(ctx.kg_disambiguated_terms.items())[:5]
                )
                kg_context_block += f"User terms resolved: {terms_str}\n"
            if ctx.kg_relevant_systems:
                kg_context_block += (
                    f"Priority systems for this incident type: "
                    f"{', '.join(ctx.kg_relevant_systems[:4])}\n"
                )

        # Inject user's original query so LLM can acknowledge and compare against evidence
        user_context_block = ""
        if user_query:
            user_context_block = (
                f"\nUSER'S ORIGINAL QUERY (what they described):\n\"{user_query}\"\n\n"
                "IMPORTANT: Compare the user's stated scenario to the evidence above. "
                "If there is a contradiction (e.g. user says 'order is in PP/DS' but evidence shows no PP/DS records), "
                "acknowledge this explicitly in the executive summary and ask a clarifying follow-up question. "
                "Never ignore what the user told you.\n\n"
            )

        prompt = (
            f"Generate a forensic supply chain investigation report based ONLY on the evidence below.\n\n"
            f"Evidence from live SAP systems:\n{evidence_json}\n\n"
            f"{user_context_block}"
            f"{kg_context_block}"
            f"{focus_hint}\n"
            "Rules:\n"
            "- Start by acknowledging what the user described, then state what the evidence shows.\n"
            "- If evidence contradicts the user's stated context, say so explicitly and ask for clarification.\n"
            "- NEVER use API service names. Use functional SAP terms (Planned Orders in MD04, PP/DS scheduling, etc.).\n"
            "- Cite actual field values when present (MRPType, record counts, etc.).\n"
            "- If PP/DS config shows ProductionSchedulingProfile blank: state PP/DS integration not configured, "
            "check MM02 MRP 2 tab for Advanced Planning checkbox.\n"
            "- For MISSING systems: state what could not be verified and give the SAP transaction to check manually.\n\n"
            "Return ONLY a JSON object with exactly two keys: 'consultant_view' and 'planner_view'.\n"
            f"Each must be a JSON object with these exact 14 keys: {_14_SECTIONS}.\n"
            "Plain text only -- no markdown. Consultant view: technical + SAP transactions. "
            "Planner view: plain English only, max 3 sentences per section."
        )

        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]

        # gen_ai_hub models may return synchronous LLMs -- try ainvoke first, fall back to invoke
        logger.info("narrate_findings: calling ainvoke...")
        try:
            response = await llm.ainvoke(messages)
        except (NotImplementedError, AttributeError):
            import asyncio
            logger.info("narrate_findings: ainvoke not available, using run_in_executor...")
            response = await asyncio.get_event_loop().run_in_executor(
                None, lambda: llm.invoke(messages)
            )
        logger.info("narrate_findings: response received, content length=%d", len(response.content or ''))
        logger.info("narrate_findings: first 500 chars: %s", (response.content or '')[:500])
        raw = response.content

        # Parse JSON -- handle both raw JSON and ```json fenced output
        try:
            import re
            # Strip ```json ... ``` fences if present
            stripped = re.sub(r'^```(?:json)?\s*', '', raw.strip(), flags=re.IGNORECASE)
            stripped = re.sub(r'\s*```$', '', stripped.strip())
            # Find outermost JSON object
            json_match = re.search(r'\{.*\}', stripped, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                consultant = parsed.get("consultant_view", {})
                planner = parsed.get("planner_view", {})
                if consultant or planner:
                    logger.info("narrate_findings: parsed successfully, consultant keys=%d", len(consultant))
                    return NarrationResult(
                        consultant_sections=consultant if isinstance(consultant, dict) else {},
                        planner_sections=planner if isinstance(planner, dict) else {},
                        fallback_used=False,
                    )
            logger.warning("narrate_findings: no JSON object found in response")
        except Exception as parse_exc:
            logger.warning("LLM JSON parse failed: %s", parse_exc)

    except Exception as exc:
        logger.warning("LLM narration failed: %s -- using deterministic fallback", exc)

    return _fallback_narration(classification, ctx)
