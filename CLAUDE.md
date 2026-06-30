# USCIA 2.1 — Claude Code Project Context

## What this project is

**Unified Supply Chain Intelligence Agent (USCIA)** — an autonomous Python AI agent deployed on SAP BTP AI Core via Cloud Foundry. It diagnoses SAP supply chain planning failures end-to-end by querying 15 systems in parallel, building an evidence graph, classifying root causes deterministically, and delivering a 14-section forensic report in under 5 minutes.

Primary interface: **SAP Joule** (A2A protocol endpoint). Secondary: direct A2A API / the dashboard.

## Repository layout

```
USCIA 2.1/
├── assets/uscia-agent/          # Python A2A agent — the core
│   ├── app/
│   │   ├── main.py              # ASGI entry point, A2A server setup
│   │   ├── agent.py             # SampleAgent — full M1→M5 orchestration
│   │   ├── agent_executor.py    # A2A executor wrapper
│   │   ├── mcp_tools.py         # MCP tool loader (mock/Agent Gateway)
│   │   ├── aicore.py            # LLM init from BTP destination
│   │   ├── s4hana_client.py     # S/4HANA OData client
│   │   ├── ibp_client.py        # IBP REST client (OAuth2)
│   │   ├── evidence/
│   │   │   ├── collector.py     # asyncio.gather across 15 systems (M2)
│   │   │   ├── graph_builder.py # Evidence graph construction (M3)
│   │   │   └── models.py        # Core dataclasses (InvestigationContext, EvidenceNode, etc.)
│   │   ├── classification/
│   │   │   ├── classifier.py    # Deterministic YAML rule engine (M4)
│   │   │   ├── rules.yaml       # Externalised root cause rules (RC000–RC008)
│   │   │   └── remediation_ranker.py
│   │   ├── report/
│   │   │   └── generator.py     # 14-section report generator (M5)
│   │   ├── llm/
│   │   │   └── narrator.py      # LLM narration layer (GPT-4o via AI Core)
│   │   ├── learning/            # L1–L5 async post-M5 steps
│   │   ├── tools/               # 15 MCP tool wrappers (one per system)
│   │   ├── db/                  # HANA Cloud client + schema
│   │   └── execution/           # Phase 4 dispatcher (stub)
│   ├── manifest.yml             # CF deployment manifest
│   ├── mcp-mock.json            # Mock MCP tool responses for IBD_TESTING=1
│   └── requirements.txt
├── assets/uscia-dashboard/      # Node.js + React dashboard
│   ├── server.js                # Express: A2A proxy + static serve
│   ├── manifest.yml             # CF deployment manifest
│   └── client/src/              # React + UI5 web components
│       ├── App.jsx
│       ├── components/ReportView.jsx    # 14-section report renderer
│       ├── components/ChatArea.jsx
│       ├── components/LineageFlow.jsx   # Evidence graph visualisation
│       └── components/FioriShell.jsx
├── intent.md                    # Business challenge + milestones spec
├── product-requirements-document.md
├── solution.yaml
└── specification/
```

## Investigation flow (M1→M5)

```
User message
  → M1: Context capture (material, plant, planning_version, date_range, incident_type, continuity_keys)
  → LLM Orchestrator (ASK / INVESTIGATE / INVESTIGATE_LIMITED / CONTRADICTION)
  → M2: asyncio.gather across 15 systems in parallel (never sequential)
  → M3: Evidence graph construction + broken boundary detection
  → M4: Deterministic YAML rule classification + LLM narration
  → Approval gate (if executable actions exist)
  → M5: 14-section forensic report (Consultant + Planner views)
  → async L1 (HANA persistence) + L4 (pattern detection)
```

## 15 evidence systems (M2)

| # | System name | API type | Notes |
|---|-------------|----------|-------|
| 1 | S4HANA_PLANNED_ORDER | OData v4 | PLANNEDORDER_0001 |
| 2 | S4HANA_MATERIAL_PLANNING | OData | API_MRP_MATERIALS_SRV_01 |
| 3 | S4HANA_PIR | OData | OP_API_PLND_INDEP_RQMT_SRV_0001 |
| 4 | S4HANA_PPDS_STOCK | OData | OP_PPDSPRODTDSTLV_0001 |
| 5 | S4HANA_PPDS_CONSTRAINTS | OData | OP_APIFLEXIBLECONSTRAINTS_0001 |
| 6 | S4HANA_ATP | OData | CE_APIAVAILTOPROMISECHECK_0001 |
| 7 | S4HANA_APPLICATION_LOGS | OData | SLG1 equivalent |
| 8 | S4HANA_BGRFC_QUEUE | OData | SM58 equivalent — MISSING_DATA stub |
| 9 | S4HANA_PPDS_CONFIG | OData | MRP + PP/DS config check |
| 10 | IBP_SUPPLY | REST | IBP OAuth2 — most complex auth |
| 11 | SAP_CPI | REST | MISSING_DATA stub → points to SXMB_MONI |
| 12 | SAP_PIPO | REST | MISSING_DATA stub (legacy PI/PO) |
| 13 | CLOUD_ALM | REST | MISSING_DATA stub — activate post-deploy |
| 14 | SAP_BDC | REST | SAP Business Data Cloud analytics |
| 15 | IBP_JOB_MONITOR | REST | IBP planning job run status |

## 10 incident types

1. Planned order missing in MD04
2. Planned order not reaching PP/DS RRP3
3. Quantity/date inconsistency between IBP and S/4HANA
4. PIR exists but no planned order created
5. PP/DS scheduling failure
6. aATP confirmation missing or incorrect
7. CIF transfer failure
8. IBP planning job failure
9. RTI/CPI message failure
10. bgRFC queue blockage

## Root cause classification rules (rules.yaml)

| Rule ID | Category | Confidence |
|---------|----------|------------|
| RC000 | MATERIAL_NOT_FOUND | HIGH — fires when S/4 returns 0 records for material/plant |
| RC001 | RTI_CPI_MESSAGE_FAILURE | HIGH |
| RC002 | BGRFC_QUEUE_BLOCKAGE | HIGH |
| RC003 | MASTER_DATA_CONFIG_ERROR | HIGH |
| RC003B | MASTER_DATA_CONFIG_ERROR | MEDIUM — MRP type blank variant |
| RC004 | PPDS_SCHEDULING_FAILURE | HIGH |
| RC005 | CIF_TRANSFER_FAILURE | MEDIUM |
| RC006 | ATP_SCOPE_MISMATCH | MEDIUM |
| RC007 | IBP_PLANNING_GAP | MEDIUM |
| RC008 | OTHER | LOW — fallback when no rule matches |

KG BP ID bias: BPS-349 floats RC004/RC005/RC006 first; BPS-327 floats RC001/RC002/RC007 first.

## Approval gate (Phase 4 ready)

After M4, if any action is non-MANUAL_ONLY (RESTART_BGRFC, REPROCESS_CPI_MESSAGE, RERUN_PPDS_HEURISTIC, RERUN_MRP_SINGLE_ITEM, RERUN_IBP_JOB), the agent pauses and asks the user to approve before delivering the full report. This is the Phase 4 execution contract — every action carries `action_type`, `action_params`, `requires_approval: true`.

## Deployment

### Agent (uscia-agent)
```bash
cd assets/uscia-agent
cf push
```
- Python buildpack, gunicorn + uvicorn worker
- Binds: `proj-vector-destination-service`, `proj-vector-connectivity-service`
- Key env vars: `S4HANA_DESTINATION_NAME=S4HANA`, `AICORE_DESTINATION_NAME=aicore`, `IBP_DESTINATION_NAME=IBP`
- Health check: `GET /.well-known/agent.json`
- Port: `$PORT` (CF-assigned)

### Dashboard (uscia-dashboard)
```bash
cd assets/uscia-dashboard/client && npm run build
cd .. && cf push
```
- Node.js buildpack, Express server
- Key env var: `USCIA_AGENT_URL` — must point to the deployed agent URL

### Local dev / testing
```bash
# Agent
cd assets/uscia-agent
IBD_TESTING=1 python app/main.py     # uses mcp-mock.json, no live SAP calls

# Dashboard
cd assets/uscia-dashboard
node server.js                        # USCIA_AGENT_URL=http://localhost:5000
```

## Key architectural constraints (enforce always)

1. **Strict read-only** — no tool wrapper may write, create, update, or delete on any SAP system. Violation = build-blocking defect.
2. **Evidence-first** — LLM narrates evidence only; never generates findings from general SAP knowledge.
3. **Absence = MISSING DATA** — zero API results → MISSING_DATA tag, never "no issue found".
4. **Never abort** — single unavailable system → MISSING_DATA node + manual guidance; investigation continues.
5. **asyncio.gather only** — all 15 M2 queries in parallel; no sequential fallback permitted.
6. **Pluggable by design** — new system = new tool wrapper in `app/tools/`; no changes to agent core.
7. **Phase 4 ready** — every remediation action must carry `action_type`, `action_params`, `requires_approval`.

## LLM conversational orchestrator

In `agent.py`, the LLM orchestrator (`_llm_orchestrate`) runs per turn before M2. It decides:
- `ASK` — needs more info (one focused question)
- `INVESTIGATE` — has enough context
- `INVESTIGATE_LIMITED` — user can't provide more; proceed with disclaimer
- `CONTRADICTION` — user contradicts earlier statement

Structured JSON queries bypass the orchestrator entirely.

## Supporting MCP servers (in this repo)

- `ibp_unofficial_abap_mcp-main/` — IBP ABAP Intelligence MCP server (release repo); 32 ABAP tools
- `s4-mcp-server-main/` — S/4HANA OData + HANA SQL MCP server (FastMCP, Streamable HTTP on :8080)

## CF login
```bash
cf login --sso
```

## Tests
```bash
cd assets/uscia-agent
pytest                   # requires IBD_TESTING=1 or mocked env
pytest --cov=app         # coverage target ≥ 75%
```
