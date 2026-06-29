import asyncio
import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import AsyncGenerator, Literal, Sequence

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import InMemorySaver

# dual-mode: use real decorators on Joule, no-op identity wrappers on CF
try:
    from sap_cloud_sdk.agent_decorators import agent_config, agent_model, prompt_section
except ImportError:
    def _identity_decorator(*_dargs, **_dkwargs):
        def _wrap(fn):
            return fn
        return _wrap

    agent_model = _identity_decorator
    agent_config = _identity_decorator
    prompt_section = _identity_decorator

from aicore import init_llm_from_destination
from s4hana_client import S4Client
from ibp_client import IBPClient
from tools.kg_grounding import ground_investigation_context, KGGroundingResult
from evidence.collector import collect_evidence
from evidence.graph_builder import build_evidence_graph
from evidence.models import InvestigationContext
from classification.classifier import classify
from classification.remediation_ranker import rank_remediation_actions
from llm.narrator import narrate_findings
from report.generator import generate_report
from learning.persistence import persist_incident
from learning.pattern_detector import detect_patterns
from learning.outcome_tracker import record_outcome
from learning.effectiveness import update_effectiveness
from learning.predictive_scanner import scan_for_pre_failure_signatures
from execution.dispatcher import dispatch_approved_actions, format_dispatch_summary
from mcp_tools import get_mcp_tools

logger = logging.getLogger(__name__)

THREAD_TTL_SECONDS = 3600
APPROVAL_TTL_SECONDS = 1800  # pending approvals expire after 30 min

# Action types that can be automated in Phase 4 — these trigger the approval gate.
# MANUAL_ONLY actions are recommendations only; no gate needed.
_EXECUTABLE_ACTION_TYPES = frozenset({
    "RESTART_BGRFC",
    "REPROCESS_CPI_MESSAGE",
    "RERUN_PPDS_HEURISTIC",
    "RERUN_MRP_SINGLE_ITEM",
    "RERUN_IBP_JOB",
})

# ──────────────────────────────────────────────────────────────────────────────
# Approval-gate data structures
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class PendingApproval:
    """Holds all state needed to resume after the user approves or rejects actions."""
    context_id: str
    incident_id: str
    material: str
    plant: str
    root_cause: str
    confidence: str
    executable_actions: list          # RemediationAction objects (non-MANUAL_ONLY)
    full_report: str                  # consultant_view — delivered after approval/rejection
    outcome_hint: str                 # outcome recording footer
    created_at: float = field(default_factory=time.monotonic)


@dataclass
class AgentResult:
    """Return value of _run_agent(): separates content from flow-control flags."""
    content: str
    requires_input: bool = False
    approval_id: str = ""             # set when requires_input=True (pending approval key)


@agent_model(
    key="config.model",
    label="LLM Model",
    description="The language model powering this agent",
)
def get_model_name() -> str:
    return os.environ.get("AGENT_LLM_MODEL", "gpt-4o")


@agent_config(
    key="config.temperature",
    label="LLM Temperature",
    description="Controls randomness of LLM narration (0.0 = deterministic)",
)
def get_temperature() -> float:
    return 0.1


@prompt_section(
    key="prompts.system",
    label="System Prompt",
    description="USCIA system prompt — evidence-first, never hallucinate findings",
    validation={"format": "markdown", "max_length": 5000},
)
def get_system_prompt() -> str:
    return (
        "You are an autonomous supply chain planning failure diagnostic agent. "
        "You investigate cross-system planning failures across SAP IBP, RTI/CPI, bgRFC, "
        "S/4HANA MRP, PP/DS, and aATP. "
        "CRITICAL RULES: "
        "1. NEVER state a finding without evidence retrieved from a tool call. "
        "2. NEVER infer root causes from general SAP knowledge — only from retrieved evidence. "
        "3. If a system is unavailable, always return MISSING_DATA with manual investigation guidance — never 'no issue found'. "
        "4. All tool calls that accept a page-size or top parameter must use a maximum of 100. "
        "5. Always tag every finding as [CONFIRMED], [PROBABLE], or [MISSING DATA]. "
        "6. Always deliver all 14 report sections even when evidence is partial."
    )


# ──────────────────────────────────────────────────────────────────────────────
# Context extraction helpers
# ──────────────────────────────────────────────────────────────────────────────

_INCIDENT_TYPES = [
    "planned order missing in MD04",
    "planned order not reaching PP/DS RRP3",
    "quantity or date inconsistency between IBP and S4HANA",
    "PIR exists but no planned order created",
    "PP/DS scheduling failure",
    "aATP confirmation missing or incorrect",
    "CIF transfer failure",
    "IBP planning job failure",
    "RTI/CPI message failure",
    "bgRFC queue blockage",
]

# Specific multi-word signal phrases per incident type — ordered by specificity.
# A phrase only matches if ALL its words are present in the query.
# Scored: more words in phrase = higher weight. Highest total score wins.
_INCIDENT_SIGNALS: dict[str, list[str]] = {
    "PP/DS scheduling failure": [
        "unscheduled rrp3", "not scheduled ppds", "unscheduled ppds",
        "ppds unscheduled", "rrp3 unscheduled", "ppds received",
        "capacity constraint", "scheduling failure", "rrp3 capacity",
        "ppds capacity", "ppds master data", "ppds scheduling",
        "not reaching rrp3", "missing rrp3", "rrp3 missing",
    ],
    "planned order not reaching PP/DS RRP3": [
        "not reaching rrp3", "not in rrp3", "missing rrp3",
        "not transferred ppds", "cif failure", "not reaching ppds",
        "in md04 not ppds", "md04 not rrp3",
    ],
    "CIF transfer failure": [
        "cif failure", "cif transfer", "not transferred ppds",
        "cif error", "apocif", "core interface",
    ],
    "bgRFC queue blockage": [
        "bgrfc queue", "bgrfc blockage", "queue blocked", "sm58",
        "queue stuck", "bgrfc stuck", "tRFC queue",
    ],
    "RTI/CPI message failure": [
        "rti message", "cpi message", "integration message",
        "sxmb_moni", "message failure", "message routing",
        "ibp not transferred", "rti failure",
    ],
    "IBP planning job failure": [
        "ibp job", "planning job", "ibp planning run", "ibp run",
        "ibp job failed", "planning job failure",
    ],
    "aATP confirmation missing or incorrect": [
        "atp confirmation", "atp missing", "atp incorrect",
        "no confirmation", "co09", "atp check",
    ],
    "quantity or date inconsistency between IBP and S4HANA": [
        "quantity inconsistency", "date inconsistency",
        "different quantity", "wrong quantity", "quantity mismatch",
        "date mismatch", "ibp quantity", "inconsistency ibp",
    ],
    "PIR exists but no planned order created": [
        "pir exists", "pir created", "no planned order",
        "pir but no order", "demand exists no order",
    ],
    "planned order missing in MD04": [
        "missing md04", "not in md04", "md04 missing",
        "not visible md04", "not appearing md04",
    ],
}

# Stop-words that should not contribute to matching
_STOP_WORDS = {"the", "a", "an", "is", "are", "was", "were", "for", "of",
               "in", "on", "at", "to", "and", "or", "but", "it", "its",
               "this", "that", "with", "from", "by", "be", "been", "has",
               "have", "had", "do", "did", "not", "no", "i", "we", "you",
               "my", "our", "their", "there", "here", "why", "how", "what",
               "which", "when", "so", "if", "about", "after", "before"}


def _detect_incident_type(query: str) -> str:
    """
    Detect incident type using scored phrase matching — NOT single-keyword first-match.

    Each incident type has a list of specific signal phrases. A phrase matches only
    when ALL its words are present in the query. Score = number of matched words
    across all matching phrases for that incident type. Highest score wins.

    This prevents 'planned' in 'PP/DS received the planned order but unscheduled'
    from incorrectly matching 'planned order missing in MD04'.
    """
    q = query.lower()
    q_words = set(w.strip(".,?!;:") for w in q.split()) - _STOP_WORDS

    scores: dict[str, int] = {}
    for incident_type, phrases in _INCIDENT_SIGNALS.items():
        score = 0
        for phrase in phrases:
            phrase_words = phrase.split()
            if all(w in q_words for w in phrase_words):
                # Multi-word phrase match — weight by phrase length (more specific = higher score)
                score += len(phrase_words) * 2
        if score > 0:
            scores[incident_type] = score

    if scores:
        best = max(scores, key=lambda k: scores[k])
        logger.debug("incident_type detection: scores=%s, best=%s", scores, best)
        return best

    # Fallback: original keyword scan (but now last resort)
    for t in _INCIDENT_TYPES:
        meaningful_words = [w for w in t.split() if w not in _STOP_WORDS and len(w) > 3]
        if meaningful_words and all(w in q for w in meaningful_words):
            return t

    return "planned order missing in MD04"


def _default_date_range() -> tuple[str, str]:
    """Return (date_from, date_to) covering 6 months back to 6 months forward from today."""
    from datetime import date, timedelta
    today = date.today()
    date_from = (today - timedelta(days=180)).strftime("%Y-%m-%d")
    date_to = (today + timedelta(days=180)).strftime("%Y-%m-%d")
    return date_from, date_to


def _extract_context_from_query(
    query: str,
    prior_context: "InvestigationContext | None" = None,
    grounding: "KGGroundingResult | None" = None,
) -> "InvestigationContext":
    default_from, default_to = _default_date_range()
    json_match = re.search(r"\{.*\}", query, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group())
            # Structured JSON input takes precedence; KG grounding still enriches context fields
            incident_type = data.get("incident_type") or (
                grounding.incident_type if grounding and grounding.confidence in ("HIGH", "MEDIUM")
                else _detect_incident_type(query)
            )
            return InvestigationContext(
                material=data.get("material", "UNKNOWN"),
                plant=data.get("plant", "UNKNOWN"),
                planning_version=data.get("planning_version", "000"),
                date_from=data.get("date_from", default_from),
                date_to=data.get("date_to", default_to),
                incident_type=incident_type,
                continuity_keys=data.get("continuity_keys", {}),
                kg_process_context=grounding.process_context if grounding else "",
                kg_relevant_systems=grounding.relevant_systems if grounding else [],
                kg_disambiguated_terms=grounding.disambiguated_terms if grounding else {},
                kg_bp_ids=grounding.kg_bp_ids if grounding else [],
                kg_confidence=grounding.confidence if grounding else "",
                kg_fallback_used=grounding.fallback_used if grounding else True,
            )
        except Exception:
            pass

    # ── Regex extraction — material, plant, dates ─────────────────────────────
    # Material: uppercase alphanumeric token 3-18 chars — must contain at least one letter
    mat_match = re.search(r"\b([A-Z][A-Z0-9_-]{2,17}|[A-Z0-9_-]{2,17}[A-Z])\b", query)
    # Plant: exactly 2-4 digits after the word "plant" (or "location")
    plant_match = re.search(r"(?:plant|location)\s+([0-9]{2,4})\b", query, re.IGNORECASE)
    # Also check for standalone 2-4 digit codes when prior material exists
    if not plant_match and prior_context and prior_context.material != "UNKNOWN":
        plant_match = re.search(r"\b([0-9]{2,4})\b", query)
    date_match = re.findall(r"\d{4}-\d{2}-\d{2}", query)

    material = mat_match.group(1) if mat_match else "UNKNOWN"
    plant = plant_match.group(1) if plant_match else "UNKNOWN"

    # Carry over material/plant from prior context if not found in this query
    if prior_context:
        if material == "UNKNOWN" and prior_context.material != "UNKNOWN":
            material = prior_context.material
        if plant == "UNKNOWN" and prior_context.plant != "UNKNOWN":
            plant = prior_context.plant

    # ── Incident type: KG grounding wins over regex if confidence is HIGH/MEDIUM ──
    # This is the core improvement: KG understands "nothing in RRP3" means
    # "planned order not reaching PP/DS RRP3" — regex alone cannot do this.
    if grounding and grounding.confidence in ("HIGH", "MEDIUM"):
        incident_type = grounding.incident_type
    else:
        incident_type = _detect_incident_type(query)

    return InvestigationContext(
        material=material,
        plant=plant,
        planning_version="000",
        date_from=date_match[0] if len(date_match) > 0 else default_from,
        date_to=date_match[1] if len(date_match) > 1 else default_to,
        incident_type=incident_type,
        continuity_keys={},
        kg_process_context=grounding.process_context if grounding else "",
        kg_relevant_systems=grounding.relevant_systems if grounding else [],
        kg_disambiguated_terms=grounding.disambiguated_terms if grounding else {},
        kg_bp_ids=grounding.kg_bp_ids if grounding else [],
        kg_confidence=grounding.confidence if grounding else "",
        kg_fallback_used=grounding.fallback_used if grounding else True,
    )


def _is_approval_response(query: str) -> bool:
    """Return True if the user's reply looks like an approval/rejection of pending actions."""
    q = query.lower().strip()
    keywords = [
        "yes", "proceed", "approve", "approved", "go ahead", "confirm",
        "execute", "run it", "do it", "ok", "okay", "sure",
        "no", "reject", "rejected", "cancel", "skip", "don't", "do not",
        "hold", "stop", "abort", "decline", "not now",
    ]
    return any(kw in q for kw in keywords)


def _is_positive_approval(query: str) -> bool:
    """Return True for affirmative approval; False for rejection."""
    q = query.lower().strip()
    positive = ["yes", "proceed", "approve", "approved", "go ahead", "confirm",
                "execute", "run it", "do it", "ok", "okay", "sure"]
    return any(kw in q for kw in positive)


def _format_approval_request(
    material: str,
    plant: str,
    root_cause: str,
    confidence: str,
    executable_actions: list,
) -> str:
    """Build the human-readable approval gate message shown before the full report."""
    lines = [
        "## USCIA — Action Approval Required\n",
        f"**Material:** `{material}` | **Plant:** `{plant}`",
        f"**Root Cause:** `{root_cause}` [{confidence} confidence]\n",
        "### Recommended Actions Pending Your Approval\n",
    ]
    for a in executable_actions:
        params_str = ", ".join(f"{k}={v}" for k, v in (a.action_params or {}).items())
        lines.append(
            f"**{a.rank}. `{a.action_type}`**\n"
            f"   Parameters: {params_str or '(none)'}\n"
        )
    import os as _os
    is_mock = _os.environ.get("IBD_TESTING") == "1"
    if is_mock:
        exec_notice = (
            "> 🔄 **Mock Agent Mode** — Approval will dispatch actions to simulated agents "
            "(loaded from `mcp-mock.json`). "
            "Live specialist agents will be deployed and connected in **Phase 4**.\n"
        )
    else:
        exec_notice = (
            "> ⚠️ **Phase 4 notice:** Execution agents are being deployed on the SAP Agent Gateway. "
            "Approved actions will be dispatched automatically once agents are registered. "
            "Until then, manual guidance is provided as fallback.\n"
        )
    lines += [
        "---",
        exec_notice,
        "**Do you want to proceed with these recommended actions?**\n",
        "- Reply **\"Yes, proceed\"** to approve and dispatch these actions",
        "- Reply **\"No, skip\"** to decline and receive the report for manual review",
    ]
    return "\n".join(lines)


def _is_predictive_scan_request(query: str) -> bool:
    q = query.lower()
    return any(kw in q for kw in [
        "predictive scan", "pre-failure", "predict", "scan landscape",
        "which materials", "proactive alert", "upcoming failures"
    ])


def _is_outcome_recording(query: str) -> bool:
    q = query.lower()
    return any(kw in q for kw in ["outcome", "resolved", "not resolved", "made worse", "partially resolved"])


def _extract_outcome_data(query: str) -> tuple:
    data = {}
    json_match = re.search(r"\{.*\}", query, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group())
        except Exception:
            pass
    incident_id = data.get("incident_id", "")
    action_id = data.get("action_id", "")
    outcome = data.get("outcome", "")
    if not outcome:
        for o in ["Resolved", "Partially Resolved", "Not Resolved", "Made Worse"]:
            if o.lower() in query.lower():
                outcome = o
                break
    return incident_id, action_id, outcome


# ──────────────────────────────────────────────────────────────────────────────
# Agent class
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class AgentResponse:
    status: Literal["input_required", "completed", "error"]
    message: str


class SampleAgent:
    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

    def __init__(
        self,
        s4_client: S4Client | None = None,
        ibp_client: IBPClient | None = None,
    ) -> None:
        self._s4_client: S4Client = s4_client or S4Client()
        self._ibp_client: IBPClient = ibp_client or IBPClient()
        self._checkpointer = InMemorySaver()
        self._last_active: dict[str, float] = {}
        self._llm: BaseChatModel | None = None
        # Per-session context memory: stores last successful InvestigationContext
        self._last_ctx: dict[str, "InvestigationContext"] = {}
        # Pending approval gate: keyed by context_id; expires after APPROVAL_TTL_SECONDS
        self._pending_approvals: dict[str, PendingApproval] = {}

    @property
    def s4_client(self) -> S4Client:
        return self._s4_client

    @property
    def ibp_client(self) -> IBPClient:
        return self._ibp_client

    def _get_pending_approval(self, context_id: str) -> "PendingApproval | None":
        """Return a non-expired pending approval for this context, or None."""
        pa = self._pending_approvals.get(context_id)
        if pa is None:
            return None
        if time.monotonic() - pa.created_at > APPROVAL_TTL_SECONDS:
            del self._pending_approvals[context_id]
            logger.info("approval_gate: pending approval expired — context_id=%s", context_id)
            return None
        return pa

    async def _resolve_approval(self, pa: "PendingApproval", approved: bool) -> str:
        """Build the response message for an approval or rejection decision.

        When approved, attempts to dispatch each executable action to its
        registered MCP tool on the Agent Gateway.  If a tool is not yet
        registered (pre-Phase-4 builds), the dispatcher returns TOOL_NOT_REGISTERED
        and the user receives manual guidance — no exception is raised.
        """
        del self._pending_approvals[pa.context_id]
        decision = "APPROVED" if approved else "DECLINED"
        logger.info(
            "approval_gate: decision recorded — incident_id=%s, material=%s, plant=%s, "
            "root_cause=%s, decision=%s, actions=%d",
            pa.incident_id, pa.material, pa.plant,
            pa.root_cause, decision, len(pa.executable_actions),
        )

        if approved:
            # ── Phase 4 dispatch ──────────────────────────────────────────────
            # Load the live MCP tool list from the Agent Gateway (cached; ~0 ms
            # on repeat calls).  If no execution tools are registered yet the
            # list is empty and every action becomes TOOL_NOT_REGISTERED.
            try:
                live_tools = await get_mcp_tools()
            except Exception:
                logger.warning("approval_gate: could not load MCP tools — dispatch skipped", exc_info=True)
                live_tools = []

            dispatch_results = await dispatch_approved_actions(pa.executable_actions, live_tools)
            dispatch_summary = format_dispatch_summary(dispatch_results)

            action_lines = "\n".join(
                f"  ✅ `{a.action_type}` (action_id={a.action_id}) — approved"
                for a in pa.executable_actions
            )
            header = (
                f"## Actions Approved ✅\n\n"
                f"{action_lines}\n\n"
                f"{dispatch_summary}\n\n"
                f"---\n\n"
            )
        else:
            header = (
                f"## Actions Declined\n\n"
                f"All recommended actions have been declined. "
                f"Please review the forensic report below and apply fixes manually.\n\n"
                f"---\n\n"
            )

        return header + pa.full_report + pa.outcome_hint

    async def _run_predictive_scan(self) -> str:
        """L5 — on-demand predictive scan across all known material-plant pairs."""
        from db import hana_client
        try:
            rows = hana_client.fetchall(
                "SELECT DISTINCT material, plant FROM IncidentRecord "
                "WHERE created_at > ADD_DAYS(CURRENT_TIMESTAMP, -90) "
                "FETCH FIRST 500 ROWS ONLY"
            )
            pairs = [(r[0], r[1]) for r in rows] if rows else []
        except Exception:
            pairs = []

        if not pairs:
            return (
                "## Predictive Scan\n\n"
                "No investigation history found in HANA Cloud yet. "
                "Run investigations first to build the evidence history needed for predictive analysis.\n"
                "The predictive scanner analyses patterns across past incidents to detect pre-failure signatures."
            )

        alerts = await scan_for_pre_failure_signatures(pairs)

        if not alerts:
            return (
                f"## Predictive Scan Complete\n\n"
                f"Scanned {len(pairs)} material-plant combinations from investigation history.\n"
                f"**No pre-failure signatures detected** at this time.\n\n"
                f"Signatures monitored: bgRFC queue depth trending, IBP job duration increasing, "
                f"CPI message lag, master data changes preceding config errors."
            )

        lines = [
            f"## Predictive Scan -- {len(alerts)} Pre-Failure Alert(s) Detected\n",
            f"Scanned {len(pairs)} material-plant combinations.\n",
        ]
        for a in alerts:
            lines.append(
                f"**[ALERT] {a.signature_type}**\n"
                f"- Material: {a.affected_material} / Plant: {a.affected_plant}\n"
                f"- Based on {len(a.historical_incident_ids)} historical incident(s)\n"
                f"- Recommended action: {a.recommended_preventive_action}\n"
            )
        return "\n".join(lines)

    async def _get_llm(self) -> BaseChatModel:
        """Build LLM lazily on first use (avoids startup I/O)."""
        if self._llm is None:
            self._llm = await init_llm_from_destination(
                get_model_name(),
                temperature=get_temperature(),
                max_tokens=4096,
            )
        return self._llm

    def _touch(self, thread_id: str) -> None:
        now = time.monotonic()
        expired = [
            tid for tid, ts in list(self._last_active.items())
            if now - ts > THREAD_TTL_SECONDS
        ]
        for tid in expired:
            del self._last_active[tid]
        self._last_active[thread_id] = now

    async def _run_agent(self, query: str, context_id: str) -> "AgentResult":
        """
        Main investigation orchestrator: M1 -> M2 -> M3 -> M4 -> M5 + async L1/L4.
        Returns AgentResult; stream() reads requires_input to set A2A flow-control flags.
        """
        t_start = time.time()

        # ── Approval gate: resolve a pending approval before running investigation ──
        pa = self._get_pending_approval(context_id)
        if pa is not None and _is_approval_response(query):
            approved = _is_positive_approval(query)
            response = await self._resolve_approval(pa, approved)
            return AgentResult(content=response)

        # ── Predictive scan request ───────────────────────────────────────────
        if _is_predictive_scan_request(query):
            return AgentResult(content=await self._run_predictive_scan())

        # ── Outcome recording ─────────────────────────────────────────────────
        if _is_outcome_recording(query):
            incident_id, action_id, outcome = _extract_outcome_data(query)
            if incident_id and action_id and outcome:
                await record_outcome(incident_id, action_id, outcome)
                await update_effectiveness("UNKNOWN", "UNKNOWN", outcome)
                return AgentResult(
                    content=f"Outcome recorded: {outcome} for incident {incident_id}. Thank you for the feedback."
                )

        # ── KG Grounding (pre-M1) ─────────────────────────────────────────────
        # Ground the query in SAP process knowledge BEFORE regex extraction.
        # Disambiguates SAP terms, maps to BP hierarchy, identifies system chain.
        # Falls back gracefully to local SAP knowledge map if KG API unavailable.
        grounding = await ground_investigation_context(query)

        # ── M1 — Context capture ──────────────────────────────────────────────
        prior = self._last_ctx.get(context_id)
        ctx = _extract_context_from_query(query, prior_context=prior, grounding=grounding)

        # ── M1 clarification — ask before running evidence collection ─────────
        missing_fields = []
        if ctx.material == "UNKNOWN":
            missing_fields.append("material number")
        if ctx.plant == "UNKNOWN":
            missing_fields.append("plant code")

        if missing_fields:
            fields_str = " and ".join(missing_fields)
            # Save what we have so far — material/plant already known won't be asked again
            self._last_ctx[context_id] = ctx
            logger.info(
                "M1.missed: investigation context incomplete — missing_fields=%s, reason=not provided in query",
                missing_fields,
            )
            return AgentResult(
                content=(
                    f"To investigate this planning failure I need a bit more information.\n\n"
                    f"Could you provide the **{fields_str}**?\n\n"
                    f"For example:\n"
                    f"- _Why is the planned order for material **MAT-1234** plant **1000** missing in MD04?_\n\n"
                    f"You can also include a date range if you know when the issue started."
                ),
                requires_input=True,
            )

        logger.info(
            "M1.achieved: investigation context captured — material=%s, plant=%s, version=%s, "
            "date_range=%s to %s, incident_type=%s, continuity_keys=%s, "
            "kg_grounding=%s, kg_confidence=%s, kg_bp_ids=%s, terms_disambiguated=%d",
            ctx.material, ctx.plant, ctx.planning_version,
            ctx.date_from, ctx.date_to, ctx.incident_type, ctx.continuity_keys,
            "LIVE" if not ctx.kg_fallback_used else "FALLBACK",
            ctx.kg_confidence, ctx.kg_bp_ids, len(ctx.kg_disambiguated_terms),
        )
        # Save context for multi-turn clarification
        self._last_ctx[context_id] = ctx

        # ── M2 — Parallel evidence collection ────────────────────────────────
        payload = await collect_evidence(ctx, s4=self._s4_client, ibp=self._ibp_client)

        if payload.insufficient_coverage_warning:
            logger.warning("Insufficient evidence coverage — fewer than 3 systems returned data")

        # ── M3 — Build evidence graph ─────────────────────────────────────────
        graph = build_evidence_graph(payload, ctx)
        graph._material = ctx.material  # type: ignore[attr-defined]
        graph._plant = ctx.plant  # type: ignore[attr-defined]
        graph._incident_type = ctx.incident_type  # type: ignore[attr-defined]

        # ── M4 — Classify root cause ──────────────────────────────────────────
        # Pass ctx so the classifier can bias rule order from KG BP IDs.
        classification = classify(graph, payload, ctx=ctx)
        ranked_actions = rank_remediation_actions(classification)
        classification.remediation_actions = ranked_actions

        # ── LLM narration ─────────────────────────────────────────────────────
        llm = await self._get_llm()
        narration = await narrate_findings(classification, graph, ctx, llm=llm, user_query=query)

        # ── L4 pattern detection (non-blocking) ───────────────────────────────
        incident_id = str(uuid.uuid4())
        pattern_task = asyncio.create_task(
            detect_patterns(ctx.material, ctx.plant, classification.root_cause, incident_id)
        )

        # ── M5 — Generate report ──────────────────────────────────────────────
        try:
            pattern_result = await asyncio.wait_for(asyncio.shield(pattern_task), timeout=2.0)
        except asyncio.TimeoutError:
            pattern_result = None

        report = generate_report(narration, classification, graph, ctx, incident_id, pattern_result)

        duration = round(time.time() - t_start, 1)
        logger.info(
            "M5.achieved: forensic report delivered — sections=14, duration_seconds=%.1f, "
            "root_cause=%s, persisted_incident_id=%s",
            duration, classification.root_cause, incident_id,
        )

        # ── L1 persistence (non-blocking) ─────────────────────────────────────
        asyncio.create_task(
            persist_incident(
                incident_id, graph, classification, report, ranked_actions,
                planning_version=ctx.planning_version,
                duration_seconds=int(duration),
            )
        )

        # Outcome recording hint appended to every delivered report
        outcome_hint = (
            f"\n\n---\n*To record the outcome of this investigation after applying a fix, "
            f"reply with: outcome incident_id={incident_id} action_id=<action_id> "
            f"outcome=Resolved (or: Partially Resolved / Not Resolved / Made Worse)*"
        )

        # ── Approval gate ─────────────────────────────────────────────────────
        # Fire the gate only when at least one action is Phase-4-executable
        # (non-MANUAL_ONLY).  Pure-manual recommendations go straight to report.
        executable_actions = [
            a for a in ranked_actions
            if a.action_type in _EXECUTABLE_ACTION_TYPES
        ]

        if executable_actions:
            # Store state so the next user turn can resolve the approval
            self._pending_approvals[context_id] = PendingApproval(
                context_id=context_id,
                incident_id=incident_id,
                material=ctx.material,
                plant=ctx.plant,
                root_cause=classification.root_cause,
                confidence=classification.confidence,
                executable_actions=executable_actions,
                full_report=report.consultant_view,
                outcome_hint=outcome_hint,
            )
            logger.info(
                "approval_gate: awaiting user decision — incident_id=%s, material=%s, "
                "plant=%s, executable_actions=%d",
                incident_id, ctx.material, ctx.plant, len(executable_actions),
            )
            gate_message = _format_approval_request(
                material=ctx.material,
                plant=ctx.plant,
                root_cause=classification.root_cause,
                confidence=classification.confidence,
                executable_actions=executable_actions,
            )
            return AgentResult(
                content=gate_message,
                requires_input=True,
                approval_id=context_id,
            )

        # No executable actions — deliver report immediately
        return AgentResult(content=report.consultant_view + outcome_hint)

    async def stream(
        self,
        query: str,
        context_id: str,
        tools: Sequence[BaseTool] | None = None,  # kept for API compatibility; unused on CF
    ) -> AsyncGenerator[dict, None]:
        self._touch(context_id)
        yield {"is_task_complete": False, "require_user_input": False, "content": "Investigating..."}

        try:
            result = await self._run_agent(query, context_id)
            if result.requires_input:
                yield {
                    "is_task_complete": False,
                    "require_user_input": True,
                    "content": result.content,
                }
            else:
                yield {
                    "is_task_complete": True,
                    "require_user_input": False,
                    "content": result.content,
                }
        except Exception as exc:
            logger.exception("_run_agent failed")
            yield {
                "is_task_complete": True,
                "require_user_input": False,
                "content": f"Investigation error: {exc}. Please check the logs.",
            }

    async def invoke(
        self,
        query: str,
        context_id: str,
        tools: Sequence[BaseTool] | None = None,  # kept for API compatibility; unused on CF
    ) -> AgentResponse:
        last: dict = {}
        async for chunk in self.stream(query, context_id, tools=tools):
            last = chunk
        if last.get("require_user_input"):
            return AgentResponse(status="input_required", message=last["content"])
        if last.get("is_task_complete"):
            return AgentResponse(status="completed", message=last["content"])
        return AgentResponse(status="error", message=last.get("content", "Unknown error"))
