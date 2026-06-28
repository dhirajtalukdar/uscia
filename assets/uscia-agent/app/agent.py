import asyncio
import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass
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

logger = logging.getLogger(__name__)

THREAD_TTL_SECONDS = 3600


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


def _detect_incident_type(query: str) -> str:
    q = query.lower()
    for t in _INCIDENT_TYPES:
        if any(kw in q for kw in t.split()):
            return t
    return "planned order missing in MD04"


def _default_date_range() -> tuple[str, str]:
    """Return (date_from, date_to) covering 6 months back to 6 months forward from today."""
    from datetime import date, timedelta
    today = date.today()
    date_from = (today - timedelta(days=180)).strftime("%Y-%m-%d")
    date_to = (today + timedelta(days=180)).strftime("%Y-%m-%d")
    return date_from, date_to


def _extract_context_from_query(query: str, prior_context: "InvestigationContext | None" = None) -> "InvestigationContext":
    default_from, default_to = _default_date_range()
    json_match = re.search(r"\{.*\}", query, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group())
            return InvestigationContext(
                material=data.get("material", "UNKNOWN"),
                plant=data.get("plant", "UNKNOWN"),
                planning_version=data.get("planning_version", "000"),
                date_from=data.get("date_from", default_from),
                date_to=data.get("date_to", default_to),
                incident_type=data.get("incident_type", _detect_incident_type(query)),
                continuity_keys=data.get("continuity_keys", {}),
            )
        except Exception:
            pass

    # Material: uppercase alphanumeric token 3-18 chars — must contain at least one letter
    mat_match = re.search(r"\b([A-Z][A-Z0-9_-]{2,17}|[A-Z0-9_-]{2,17}[A-Z])\b", query)
    # Plant: exactly 2-4 digits after the word "plant" (or "location") — NOT "code", "number" etc.
    plant_match = re.search(r"(?:plant|location)\s+([0-9]{2,4})\b", query, re.IGNORECASE)
    # Also check for standalone 2-4 digit codes that look like plant codes when prior material exists
    if not plant_match and prior_context and prior_context.material != "UNKNOWN":
        plant_match = re.search(r"\b([0-9]{2,4})\b", query)
    date_match = re.findall(r"\d{4}-\d{2}-\d{2}", query)

    material = mat_match.group(1) if mat_match else "UNKNOWN"
    plant = plant_match.group(1) if plant_match else "UNKNOWN"

    # Carry over material/plant from prior context if current query didn't provide them
    if prior_context:
        if material == "UNKNOWN" and prior_context.material != "UNKNOWN":
            material = prior_context.material
        if plant == "UNKNOWN" and prior_context.plant != "UNKNOWN":
            plant = prior_context.plant

    return InvestigationContext(
        material=material,
        plant=plant,
        planning_version="000",
        date_from=date_match[0] if len(date_match) > 0 else default_from,
        date_to=date_match[1] if len(date_match) > 1 else default_to,
        incident_type=_detect_incident_type(query),
        continuity_keys={},
    )


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

    @property
    def s4_client(self) -> S4Client:
        return self._s4_client

    @property
    def ibp_client(self) -> IBPClient:
        return self._ibp_client

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

    async def _run_agent(self, query: str, context_id: str) -> str:
        """
        Main investigation orchestrator: M1 -> M2 -> M3 -> M4 -> M5 + async L1/L4.
        All business logic lives here — stream() is a thin generator wrapper.
        """
        t_start = time.time()

        # ── Predictive scan request ───────────────────────────────────────────
        if _is_predictive_scan_request(query):
            return await self._run_predictive_scan()

        # ── Outcome recording ─────────────────────────────────────────────────
        if _is_outcome_recording(query):
            incident_id, action_id, outcome = _extract_outcome_data(query)
            if incident_id and action_id and outcome:
                await record_outcome(incident_id, action_id, outcome)
                await update_effectiveness("UNKNOWN", "UNKNOWN", outcome)
                return f"Outcome recorded: {outcome} for incident {incident_id}. Thank you for the feedback."

        # ── M1 — Context capture ──────────────────────────────────────────────
        prior = self._last_ctx.get(context_id)
        ctx = _extract_context_from_query(query, prior_context=prior)

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
            return (
                f"To investigate this planning failure I need a bit more information.\n\n"
                f"Could you provide the **{fields_str}**?\n\n"
                f"For example:\n"
                f"- _Why is the planned order for material **MAT-1234** plant **1000** missing in MD04?_\n\n"
                f"You can also include a date range if you know when the issue started."
            )

        logger.info(
            "M1.achieved: investigation context captured — material=%s, plant=%s, version=%s, "
            "date_range=%s to %s, incident_type=%s, continuity_keys=%s",
            ctx.material, ctx.plant, ctx.planning_version,
            ctx.date_from, ctx.date_to, ctx.incident_type, ctx.continuity_keys,
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
        classification = classify(graph, payload)
        ranked_actions = rank_remediation_actions(classification)
        classification.remediation_actions = ranked_actions

        # ── LLM narration ─────────────────────────────────────────────────────
        llm = await self._get_llm()
        narration = await narrate_findings(classification, graph, ctx, llm=llm)

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

        # Append outcome recording hint at end of report
        outcome_hint = (
            f"\n\n---\n*To record the outcome of this investigation after applying a fix, "
            f"reply with: outcome incident_id={incident_id} action_id=<action_id> "
            f"outcome=Resolved (or: Partially Resolved / Not Resolved / Made Worse)*"
        )

        return report.consultant_view + outcome_hint

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
            yield {"is_task_complete": True, "require_user_input": False, "content": result}
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
        if last.get("is_task_complete"):
            return AgentResponse(status="completed", message=last["content"])
        if last.get("require_user_input"):
            return AgentResponse(status="input_required", message=last["content"])
        return AgentResponse(status="error", message=last.get("content", "Unknown error"))
