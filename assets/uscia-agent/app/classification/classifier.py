"""
Deterministic root cause classifier.
Loads rules from rules.yaml at startup. No LLM involvement in classification.
"""
from __future__ import annotations
import json
import logging
import os
from pathlib import Path

import yaml

from evidence.models import Classification, EvidenceGraph, EvidencePayload, RemediationAction
import uuid

logger = logging.getLogger(__name__)

_RULES: list[dict] = []

# Default remediation actions per root cause category
_DEFAULT_ACTIONS: dict[str, dict] = {
    "RTI_CPI_MESSAGE_FAILURE": {
        "action_type": "REPROCESS_CPI_MESSAGE",
        "description": "Reprocess the failed CPI/RTI integration message in SXMB_MONI",
    },
    "BGRFC_QUEUE_BLOCKAGE": {
        "action_type": "RESTART_BGRFC",
        "description": "Restart the blocked bgRFC queue entry in SM58",
    },
    "MASTER_DATA_CONFIG_ERROR": {
        "action_type": "MANUAL_ONLY",
        "description": "Correct MRP type and planning horizon in material master (MM02 → MRP1 tab)",
    },
    "MATERIAL_NOT_FOUND": {
        "action_type": "MANUAL_ONLY",
        "description": "Verify material exists in S/4HANA for this plant. Check MM03 and confirm plant assignment in MM01.",
    },
    "PPDS_SCHEDULING_FAILURE": {
        "action_type": "RERUN_PPDS_HEURISTIC",
        "description": "Rerun PP/DS scheduling heuristic in RRP3",
    },
    "CIF_TRANSFER_FAILURE": {
        "action_type": "MANUAL_ONLY",
        "description": "Check SLG1 for APOCIF errors and rerun CIF initial load if required",
    },
    "ATP_SCOPE_MISMATCH": {
        "action_type": "MANUAL_ONLY",
        "description": "Correct ATP check rule and scope assignment in CO09",
    },
    "IBP_PLANNING_GAP": {
        "action_type": "RERUN_IBP_JOB",
        "description": "Rerun IBP supply planning job for affected material-location",
    },
    "OTHER": {
        "action_type": "MANUAL_ONLY",
        "description": "Perform manual cross-system investigation — insufficient evidence for automated recommendation",
    },
}


def _load_rules() -> list[dict]:
    global _RULES
    if _RULES:
        return _RULES
    rules_path = Path(__file__).parent / "rules.yaml"
    with open(rules_path) as f:
        data = yaml.safe_load(f)
    _RULES = data.get("rules", [])
    logger.info("Loaded %d classification rules from rules.yaml", len(_RULES))
    return _RULES


def _node_data(payload: EvidencePayload, system: str) -> dict:
    for node in payload.nodes:
        if node.system_name == system:
            if node.raw_payload:
                if isinstance(node.raw_payload, str):
                    try:
                        return json.loads(node.raw_payload)
                    except Exception:
                        return {}
                # OData v2 wraps results under "results", v4 under "value"
                # Normalise both to a consistent dict
                p = node.raw_payload if isinstance(node.raw_payload, dict) else {}
                if "results" in p and "value" not in p:
                    # Normalise OData v2 → v4-style for downstream checks
                    return {"value": p["results"], **{k: v for k, v in p.items() if k != "results"}}
                return p
    return {}


def _is_available(payload: EvidencePayload, system: str) -> bool:
    return any(n.system_name == system and n.status == "AVAILABLE" for n in payload.nodes)


def _is_missing(payload: EvidencePayload, system: str) -> bool:
    return any(n.system_name == system and n.status == "MISSING_DATA" for n in payload.nodes)


def _count_items(data: dict) -> int:
    """Count items in an OData v2 (results) or v4 (value) response list."""
    val = (data.get("value") or data.get("results") or
           data.get("data") or data.get("SupplyOrders") or [])
    if isinstance(val, list):
        return len(val)
    return 0 if not val else 1


def _check_conditions(rule: dict, payload: EvidencePayload) -> bool:
    """Evaluate rule conditions against the evidence payload."""
    conds = rule.get("conditions", {})

    # ibp_has_supply
    if conds.get("ibp_has_supply"):
        ibp_data = _node_data(payload, "IBP_SUPPLY")
        if _count_items(ibp_data) == 0 and not ibp_data:
            return False

    # s4_planned_orders_count == 0
    if "s4_planned_orders_count" in conds and conds["s4_planned_orders_count"] == 0:
        po_data = _node_data(payload, "S4HANA_PLANNED_ORDER")
        if _count_items(po_data) != 0:
            return False

    # s4_planned_orders_count_gt > 0
    if conds.get("s4_planned_orders_count_gt") == 0:
        po_data = _node_data(payload, "S4HANA_PLANNED_ORDER")
        if _count_items(po_data) == 0:
            return False

    # mrp_type_blank — only fires if material planning returned data AND MRP type is blank
    if conds.get("mrp_type_blank"):
        mp_data = _node_data(payload, "S4HANA_MATERIAL_PLANNING")
        items = mp_data.get("value") or mp_data.get("results") or []
        if not items and not mp_data.get("Material"):
            return False  # no material master record — not a config error
        val = items[0] if isinstance(items, list) and items else mp_data
        if val.get("MRPType"):  # MRP type is set — not a blank config error
            return False

    # ppds_stock_entries_count == 0
    if "ppds_stock_entries_count" in conds and conds["ppds_stock_entries_count"] == 0:
        stock_data = _node_data(payload, "S4HANA_PPDS_STOCK")
        if _count_items(stock_data) != 0:
            return False

    # atp_confirmed_quantity_zero
    if conds.get("atp_confirmed_quantity_zero"):
        atp_data = _node_data(payload, "S4HANA_ATP")
        val = (atp_data.get("value") or [{}])[0] if isinstance(atp_data.get("value"), list) else atp_data
        confirmed = val.get("ConfirmedQuantity", "")
        if confirmed and str(confirmed) not in ("0", "0.000", ""):
            return False

    # pir_count_gt > 0
    if conds.get("pir_count_gt") == 0:
        pir_data = _node_data(payload, "S4HANA_PIR")
        if _count_items(pir_data) == 0:
            return False

    # pir_count_zero: fire only when PIR count is 0
    if conds.get("pir_count_zero"):
        pir_data = _node_data(payload, "S4HANA_PIR")
        if _count_items(pir_data) != 0:
            return False

    # ibp_supply_orders_count == 0
    if "ibp_supply_orders_count" in conds and conds["ibp_supply_orders_count"] == 0:
        ibp_data = _node_data(payload, "IBP_SUPPLY")
        if _count_items(ibp_data) != 0:
            return False

    return True


def _summarise_node_finding(node) -> str:
    """Generate a meaningful finding description from a node's actual data."""
    if node.status != "AVAILABLE":
        return f"[MISSING DATA] {node.system_name}: {node.manual_guidance[:150]}"

    payload = node.raw_payload or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            payload = {}

    items = payload.get("value") or payload.get("results") or payload.get("data") or []
    count = len(items) if isinstance(items, list) else (1 if payload else 0)

    # Build a meaningful summary based on what was actually found
    details = []
    if count == 0:
        details.append("0 records returned")
    else:
        details.append(f"{count} record(s) found")
        first = items[0] if isinstance(items, list) and items else (payload if isinstance(payload, dict) else {})
        for key in ["MRPType", "MRPTypeName", "MRPController", "LotSizingProcedure",
                    "PlannedOrder", "TotalQuantity", "ScheduledBasicStartDate",
                    "QueueStatus", "BusinessEvent", "Object", "Severity",
                    "AdvncdPlngFlxCnsKey", "ProductAllocationObject"]:
            val = first.get(key)
            if val is not None:
                details.append(f"{key}={val!r}")

    detail_str = "; ".join(details[:4])  # cap at 4 fields for readability
    return f"[CONFIRMED] {node.system_name}: {detail_str}"


def _material_exists_in_s4(payload: EvidencePayload) -> bool:
    """
    Return True if material-specific data was found in S/4HANA for this material/plant.
    Only checks systems that filter strictly by material+plant -- excludes ATP (global
    allocation data), PPDS stock, app logs, and bgRFC (not material-filtered).
    """
    for system in ["S4HANA_PLANNED_ORDER", "S4HANA_MATERIAL_PLANNING",
                   "S4HANA_PIR", "S4HANA_PPDS_CONSTRAINTS"]:
        if not _is_available(payload, system):
            continue
        data = _node_data(payload, system)
        if not data:
            continue
        items = (data.get("value") or data.get("results") or
                 data.get("data") or data.get("SupplyOrders") or [])
        if isinstance(items, list) and len(items) > 0:
            return True
        if isinstance(data, dict) and any(data.get(k) for k in
                                           ["Material", "Product", "PlannedOrder"]):
            return True
    return False


# ── KG-driven classifier bias ─────────────────────────────────────────────────
# Maps SAP Reference Architecture BP IDs to the rule sets they favour.
# BPS-349: Production planning & scheduling  → PP/DS / MRP layer rules
# BPS-327: Demand/supply alignment & transfer → IBP / CPI / bgRFC layer rules
# NEUTRAL rules apply regardless of BP layer.
_BP349_RULE_IDS: frozenset[str] = frozenset({"RC004", "RC005", "RC006"})
_BP327_RULE_IDS: frozenset[str] = frozenset({"RC001", "RC002", "RC007"})
_NEUTRAL_RULE_IDS: frozenset[str] = frozenset({"RC003", "RC003B", "RC008"})


def _apply_kg_bias(rules: list[dict], kg_bp_ids: list[str]) -> list[dict]:
    """Reorder deterministic rules based on KG BP IDs.

    Evidence conditions still apply — we are only changing evaluation ORDER so
    the most BP-relevant rules are tried first.  When both or neither BP IDs are
    present, the original order is preserved.

    Fallback rule (RC008) is always kept last.
    """
    if not kg_bp_ids:
        return rules

    has_349 = "BPS-349" in kg_bp_ids
    has_327 = "BPS-327" in kg_bp_ids

    if has_349 and not has_327:
        priority_ids = _BP349_RULE_IDS
        bias_direction = "PP/DS-scheduling (BPS-349)"
    elif has_327 and not has_349:
        priority_ids = _BP327_RULE_IDS
        bias_direction = "IBP/CPI-integration (BPS-327)"
    else:
        # Both present or unrecognised — no bias
        return rules

    fallback_rules = [r for r in rules if r.get("fallback")]
    non_fallback = [r for r in rules if not r.get("fallback")]

    prioritised = [r for r in non_fallback if r.get("id") in priority_ids]
    deprioritised = [r for r in non_fallback if r.get("id") not in priority_ids]

    logger.info(
        "M4.kg_bias: rule order biased — bp_ids=%s, direction=%s, "
        "prioritised_rules=%s, deprioritised_rules=%s",
        kg_bp_ids,
        bias_direction,
        [r["id"] for r in prioritised],
        [r["id"] for r in deprioritised],
    )
    return prioritised + deprioritised + fallback_rules


def classify(
    graph: EvidenceGraph,
    payload: EvidencePayload,
    ctx: "InvestigationContext | None" = None,
) -> Classification:
    """
    Apply deterministic classification rules to the evidence payload.
    Returns a Classification with root_cause, confidence, and tagged findings.
    Zero API results for any system → MISSING_DATA, never 'no issue found'.

    When *ctx* carries KG BP IDs at HIGH or MEDIUM confidence, the rule
    evaluation order is biased toward the most relevant process layer
    (BPS-349 → PP/DS rules first; BPS-327 → IBP/CPI rules first).
    Evidence conditions still govern which rule fires — bias only changes
    which rule is *tried first*.
    """
    rules = _load_rules()

    # ── Apply KG-driven rule bias (optional, evidence conditions still apply) ─
    kg_bp_ids: list[str] = []
    if ctx is not None and ctx.kg_confidence in ("HIGH", "MEDIUM") and ctx.kg_bp_ids:
        kg_bp_ids = ctx.kg_bp_ids
    rules = _apply_kg_bias(rules, kg_bp_ids)

    confirmed: list[str] = []
    probable: list[str] = []
    missing: list[str] = []

    # Build finding lists from evidence nodes — with actual data values
    for node in payload.nodes:
        finding = _summarise_node_finding(node)
        if node.status == "AVAILABLE":
            confirmed.append(finding)
        else:
            missing.append(finding)

    # ── Pre-check: material/plant not found in S/4HANA at all ────────────────
    # Fire MATERIAL_NOT_FOUND when planned order AND material planning are both
    # reachable but produced zero meaningful data for this material/plant.
    po_available = _is_available(payload, "S4HANA_PLANNED_ORDER")
    mp_available = _is_available(payload, "S4HANA_MATERIAL_PLANNING")
    if po_available and mp_available and not _material_exists_in_s4(payload):
        root_cause = "MATERIAL_NOT_FOUND"
        confidence = "HIGH"
        description = (
            "All queried S/4HANA systems returned 0 records for this material/plant. "
            "The material may not exist in this plant, may not be assigned to an MRP area, "
            "or the plant code may be incorrect. Verify in MM03 and MD04."
        )
        confirmed.insert(0, f"[CONFIRMED] {root_cause}: {description}")
        action_def = _DEFAULT_ACTIONS["MATERIAL_NOT_FOUND"]
        action = RemediationAction(
            action_id=str(uuid.uuid4()),
            action_type=action_def["action_type"],
            action_params={
                "root_cause": root_cause,
                "description": action_def["description"],
                "material": getattr(graph, "_material", ""),
                "plant": getattr(graph, "_plant", ""),
            },
            requires_approval=True,
            rank=1,
        )
        logger.info(
            "M4.achieved: root cause classified — category=%s, confidence=%s, confirmed=%d, probable=%d, missing=%d",
            root_cause, confidence, len(confirmed), len(probable), len(missing),
        )
        return Classification(
            root_cause=root_cause,
            confidence=confidence,
            confirmed_findings=confirmed,
            probable_findings=probable,
            missing_findings=missing,
            remediation_actions=[action],
            rule_id="RC000",
            description=description,
        )

    # ── Evaluate YAML rules in order; apply first match ───────────────────────
    matched_rule = None
    for rule in rules:
        if rule.get("fallback"):
            continue  # RC008 is evaluated last

        # Check required_available
        req_avail = rule.get("required_available", [])
        if not all(_is_available(payload, s) for s in req_avail):
            continue

        # Check required_missing
        req_missing = rule.get("required_missing", [])
        if not all(_is_missing(payload, s) for s in req_missing):
            continue

        # Check conditions
        if not _check_conditions(rule, payload):
            continue

        matched_rule = rule
        break

    if matched_rule is None:
        # RC008 fallback
        matched_rule = next(r for r in rules if r.get("fallback"))

    root_cause = matched_rule["name"]
    confidence = matched_rule["confidence"]
    tag = matched_rule["evidence_tag"]
    description = matched_rule.get("description", "").strip()

    # If ALL nodes are MISSING_DATA, override confidence to INDETERMINATE
    all_missing = all(n.status == "MISSING_DATA" for n in payload.nodes) if payload.nodes else False
    if all_missing:
        confidence = "INDETERMINATE"

    # Enrich RC008 description when we have partial evidence but no rule matched
    if root_cause == "OTHER" and not all_missing:
        avail_systems = [n.system_name for n in payload.nodes if n.status == "AVAILABLE"]
        # Check if material exists but no planned orders — that's the key diagnostic fact
        po_data = _node_data(payload, "S4HANA_PLANNED_ORDER")
        po_count = _count_items(po_data)
        mp_data = _node_data(payload, "S4HANA_MATERIAL_PLANNING")
        mp_items = mp_data.get("value") or mp_data.get("results") or []
        mrp_type = mp_items[0].get("MRPType", "") if mp_items else ""
        if po_count == 0 and mrp_type:
            description = (
                f"Material planning data retrieved — MRPType={mrp_type!r}, "
                f"0 planned orders found in date range. "
                f"Possible causes: (1) MRP has not been run — execute MD01N for this material/plant; "
                f"(2) No demand exists — check PIR in MD61/MD62; "
                f"(3) Planning horizon too short — check planning horizon in MM02; "
                f"(4) IBP supply data unavailable — cannot verify IBP→S4HANA integration chain. "
                f"Systems with data: {', '.join(avail_systems)}."
            )
        elif po_count == 0:
            description = (
                f"0 planned orders found. Material planning data structure did not expose MRP type. "
                f"Verify MRP type in MM03 and confirm MRP has been run (MD01N). "
                f"Systems with data: {', '.join(avail_systems)}."
            )

    # Tag findings based on rule evidence_tag
    if tag == "CONFIRMED":
        confirmed.insert(0, f"[CONFIRMED] {root_cause}: {description}")
    elif tag == "PROBABLE":
        probable.append(f"[PROBABLE] {root_cause}: {description}")
    else:
        missing.append(f"[MISSING DATA] {root_cause}: {description}")

    action_def = _DEFAULT_ACTIONS.get(root_cause, _DEFAULT_ACTIONS["OTHER"])
    action = RemediationAction(
        action_id=str(uuid.uuid4()),
        action_type=action_def["action_type"],
        action_params={
            "root_cause": root_cause,
            "description": action_def["description"],
            "material": getattr(graph, "_material", ""),
            "plant": getattr(graph, "_plant", ""),
        },
        requires_approval=True,
        rank=1,
    )

    logger.info(
        "M4.achieved: root cause classified — category=%s, confidence=%s, confirmed=%d, probable=%d, missing=%d",
        root_cause, confidence, len(confirmed), len(probable), len(missing),
    )

    return Classification(
        root_cause=root_cause,
        confidence=confidence,
        confirmed_findings=confirmed,
        probable_findings=probable,
        missing_findings=missing,
        remediation_actions=[action],
        rule_id=matched_rule["id"],
        description=description,
    )
