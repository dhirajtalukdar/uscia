import os

# dual-mode: Joule telemetry guard — runs on Joule (JOULE_RUNTIME=1), no-op on CF
if os.environ.get("JOULE_RUNTIME"):
    from sap_cloud_sdk.aicore import set_aicore_config
    from sap_cloud_sdk.core.telemetry import auto_instrument
    set_aicore_config()
    auto_instrument()

# HANA schema initialisation (idempotent — runs only if tables don't exist)
try:
    from db.schema_init import init_schema
    init_schema()
except Exception as _schema_exc:
    import logging as _log
    _log.getLogger(__name__).warning("HANA schema init skipped (expected in dev/test): %s", _schema_exc)

import logging
import uvicorn
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from agent_executor import AgentExecutor
from opentelemetry.instrumentation.starlette import StarletteInstrumentor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "5000"))

skill = AgentSkill(
    id="uscia-agent",
    name="uscia-agent",
    description=(
        "Autonomous supply chain planning failure diagnostic agent for SAP IBP, RTI/CPI, bgRFC, "
        "S/4HANA MRP, PP/DS, and aATP. Investigates 10 incident types, collects evidence from 12 "
        "systems in parallel, classifies root causes with evidence tags, and delivers a 14-section "
        "forensic report in Consultant and Planner views in under 5 minutes."
    ),
    tags=["uscia", "supply-chain", "planning", "diagnostic", "ibp", "s4hana", "ppds"],
    examples=[
        "Investigate why planned order for material M-1234 plant 1000 is missing in MD04 after IBP run",
        "Why did the planned order not reach PP/DS RRP3 for material P-5678 plant 2000?",
    ],
)
agent_card = AgentCard(
    name="uscia-agent",
    description=(
        "Autonomous supply chain planning failure diagnostic agent for SAP IBP, RTI/CPI, bgRFC, "
        "S/4HANA MRP, PP/DS, and aATP. Investigates 10 incident types, collects evidence from 12 "
        "systems in parallel, classifies root causes with evidence tags, and delivers a 14-section "
        "forensic report in Consultant and Planner views in under 5 minutes."
    ),
    url=os.environ.get("AGENT_PUBLIC_URL", f"http://{HOST}:{PORT}/"),
    version="1.0.0",
    default_input_modes=["text", "text/plain"],
    default_output_modes=["text", "text/plain"],
    capabilities=AgentCapabilities(streaming=True, push_notifications=False),
    skills=[skill],
)

server = A2AStarletteApplication(
    agent_card=agent_card,
    http_handler=DefaultRequestHandler(
        agent_executor=AgentExecutor(),
        task_store=InMemoryTaskStore(),
    ),
)

# Build the ASGI app at module level so gunicorn can import it as main:application
app = server.build()
StarletteInstrumentor().instrument_app(app)

# gunicorn/uvicorn entry point: gunicorn --chdir app main:application
application = app


def _run_dev() -> None:
    """Dev-mode entry point (python -m main or click CLI for local runs)."""
    logger.info(f"Starting A2A server at http://{HOST}:{PORT}")
    uvicorn.run(app, host=HOST, port=PORT)


if __name__ == "__main__":
    _run_dev()
