# Unified Supply Chain Intelligence Agent (USCIA)

A continuously learning supply chain intelligence platform implemented as a pro-code Python AI agent (A2A protocol), deployed on SAP BTP AI Core via Cloud Foundry.

## Business challenge

SAP supply chain planners, CoE teams, consultants, and AMS support teams regularly encounter planning failures where expected outcomes do not materialise. The most common and most painful symptom: a planned order created in SAP IBP does not appear in S/4HANA MD04, or does not reach PP/DS RRP3 for scheduling. Diagnosing this requires expert knowledge across six or more SAP system layers — IBP planning logic, RTI/CPI message routing, bgRFC queue processing, S/4HANA MRP configuration, embedded PP/DS master data, aATP scope settings, and execution handoff. This investigation currently takes 4–8 hours per incident, depends on scarce cross-domain expertise, produces inconsistent informal findings, and leaves no reusable institutional knowledge. USCIA eliminates this gap by acting as an autonomous senior diagnostic consultant: it investigates cross-system planning failures end-to-end, builds a Supply Chain Evidence Graph from live system data, classifies root causes with evidence tags, generates a consultant-ready forensic report, learns from every investigation, and over time becomes proactively intelligent about recurring failure patterns.

Investigation scope covers all of the following incident types: (1) planned order missing in MD04 after IBP planning run, (2) planned order not reaching PP/DS RRP3 after S/4HANA MRP, (3) planned order quantity or date inconsistent between IBP and S/4HANA, (4) PIR created in S/4HANA but no corresponding planned order generated, (5) PP/DS scheduling failure — order received but not scheduled due to capacity, constraint, or master data issue, (6) aATP confirmation missing or incorrect for a confirmed supply order, (7) CIF transfer failure — planned order in MD04 but not transferred to PP/DS, (8) IBP planning job failure — no supply output generated for material-location, (9) RTI/CPI message failure — IBP output not transferred to S/4HANA, (10) bgRFC queue blockage — message received by S/4HANA but not processed.

## Key Milestones

**M1 — Investigation Context Captured**
User has provided or confirmed: material, plant, planning version, date range, and at least one continuity key (planned order number, EXTERNID, demand reference, integration message ID, or similar). Agent has clarified any ambiguous inputs before proceeding. Supports both conversational natural language input and structured JSON input.
Log: `M1.achieved: investigation context captured — material={m}, plant={p}, version={v}, date_range={d}, incident_type={i}, continuity_keys={k}`

**M2 — Multi-System Evidence Collected**
Agent has queried all 12 in-scope systems in parallel using `asyncio.gather` and consolidated the raw evidence payload. Systems: S/4HANA Planned Order OData, PIR OData, PP/DS Stock Level OData, PP/DS Flexible Constraints OData, Business Events Queue OData, Application Logs OData, Advanced ATP Check OData, Material Planning Data OData, SAP Integration Suite CPI Message Processing Logs REST API, SAP PI/PO Message Monitoring API, SAP IBP OData/REST API, SAP Cloud ALM REST API. Any system without a public API spec returns status MISSING_DATA with manual investigation guidance and the relevant SAP transaction.
Log: `M2.achieved: evidence collected — systems_queried={n}, available={a}, unavailable={u}, evidence_nodes={e}`

**M3 — Supply Chain Evidence Graph Built**
Agent has correlated all retrieved evidence across continuity keys (Material+Plant, EXTERNID, ORDID, GUID, Integration Message ID, Queue Reference, Timestamp proximity <5 min fallback) and produced a Supply Chain Evidence Graph persisted to SAP HANA Cloud. The graph identifies and marks broken boundaries: any point where a node exists in system A but no corresponding node can be found in system B for the same continuity key. Schema: IncidentRecord → EvidenceNode → EvidenceLink, with FailureClassification and RemediationRecord as related entities.
Log: `M3.achieved: evidence graph built — nodes={n}, links={l}, broken_boundaries={b}, persisted_to_hana=true`

**M4 — Root Cause Classified**
Agent applies deterministic pre-classification rules (Python, not LLM) then uses LLM reasoning to synthesise findings. Root cause categories: IBP_PLANNING_GAP, RTI_CPI_MESSAGE_FAILURE, BGRFC_QUEUE_BLOCKAGE, MASTER_DATA_CONFIG_ERROR, CIF_TRANSFER_FAILURE, PPDS_SCHEDULING_FAILURE, ATP_SCOPE_MISMATCH, OTHER. Every finding tagged [CONFIRMED], [PROBABLE], or [MISSING DATA]. Agent never outputs an untagged finding. Absence of API results = MISSING DATA, never "no issue found".
Every remediation recommendation in the report must include machine-readable fields: `action_type` (enum: RESTART_BGRFC, REPROCESS_CPI_MESSAGE, RERUN_PPDS_HEURISTIC, RERUN_MRP_SINGLE_ITEM, RERUN_IBP_JOB, MANUAL_ONLY), `action_parameters` (JSON object containing the specific object references required to execute the action — e.g. queue name, message ID, material, plant, heuristic profile), and `requires_approval` (always `true` in the current build). All actions in the current build are recommendations only — no tool wrapper may implement write, create, update, or delete operations on any system. This field structure enables Phase 4 autonomous execution without modifying the report generator or classification logic.
Log: `M4.achieved: root cause classified — category={c}, confidence={HIGH|MEDIUM|LOW}, confirmed={n}, probable={n}, missing={n}`

**M5 — Consultant-Ready Forensic Report Delivered**
Agent generates a full 14-section forensic report streamed to the user in two views (Consultant View — technical, with SAP object references and error codes; Planner View — plain English with business impact and escalation path). All 14 sections are mandatory: Executive Summary, Issue Classification, Affected System Boundary, Evidence Timeline, Evidence Graph Summary, Confirmed Findings, Probable Root Causes, Missing Data Gaps, Recommended Actions, SAP Objects to Check, Logs and Transactions to Review, Business Impact, Escalation Path, Preventive Recommendation.
Log: `M5.achieved: forensic report delivered — sections=14, duration_seconds={d}, root_cause={c}, persisted_incident_id={id}`

**Learning Engine Steps (async, post-M5)**
L1 — Incident Persistence to HANA Cloud (evidence graph + classification + report + remediation actions)
L2 — Remediation Outcome Tracking (user feedback loop: Resolved / Partially Resolved / Not Resolved / Made Worse)
L3 — Remediation Effectiveness Model (effectiveness score per action-category pair)
L4 — Recurring Pattern Detection (flag if ≥3 occurrences in 90 days; escalate as systemic if ≥5)
L5 — Predictive Alert Generation (background scan for pre-failure signatures; proactive alerts with historical basis)

## Business Architecture (RBA)

### End-to-End Process

Plan to Fulfill (generic)

### Process Hierarchy

```
Plan to Fulfill (generic)
└── Plan to Optimize Fulfillment (generic)
    └── Align demand, supply and financial plans (BPS-327)
        └── Perform sales and operations planning
└── Make to Inspect (generic)
    └── Perform production planning and scheduling (BPS-349)
        └── Plan and schedule production
```

### Summary

The USCIA business challenge maps squarely to the **Plan to Fulfill** E2E, covering two sub-processes: demand/supply/financial plan alignment (BPS-327, driven by IBP) and production planning and scheduling (BPS-349, driven by S/4HANA MRP/PP/DS). The agent's diagnostic scope spans the full integration chain between these two sub-processes — RTI/CPI, bgRFC, CIF — making it a cross-boundary intelligence layer that no single SAP standard product addresses natively.

## Fit Gap Analysis

| Requirement (business) | Standard asset(s) found | API ORD ID | MCP Server ORD ID | Gap? | Notes / assumptions |
| ---------------------- | ----------------------- | ---------- | ----------------- | ---- | ------------------- |
| Demand/supply plan alignment and S&OP (BPS-327) | SAP IBP — S&OP Demand and Supply Balancing, Financial Alignment, Process Management (all Mandatory) | SAP IBP OData/REST API (no public ORD ID on Accelerator Hub) | — | No (standard SAP IBP) | IBP is the source system; USCIA queries it read-only |
| Production planning and scheduling (BPS-349) | SAP IBP — MRP (SC2096), Resource Capacity Planning (SC2993); SAP S/4HANA Cloud Private — Constraint-based Planning (SC5673), MRP (SC5690) | `sap.s4:apiResource:PLANNEDORDER_0001:v1` | — | No (standard SAP) | USCIA queries planned orders read-only via OData |
| MD04 / Material planning data read | SAP S/4HANA | `sap.s4:apiResource:API_MRP_MATERIALS_SRV_01:v1` | — | No | No MCP server found; direct OData call from agent |
| Planned Independent Requirements read | SAP S/4HANA | `sap.s4:apiResource:OP_API_PLND_INDEP_RQMT_SRV_0001:v1` | — | No | No MCP server found; direct OData call from agent |
| PP/DS time-dependent stock level read | SAP S/4HANA | `sap.s4:apiResource:OP_PPDSPRODTDSTLV_0001:v1` | — | No | No MCP server found; direct OData call from agent |
| PP/DS flexible constraint read | SAP S/4HANA | `sap.s4:apiResource:OP_APIFLEXIBLECONSTRAINTS_0001:v1` | — | No | No MCP server found; direct OData call from agent |
| Advanced ATP check read | SAP S/4HANA | `sap.s4:apiResource:CE_APIAVAILTOPROMISECHECK_0001:v1` | — | No | No MCP server found; direct OData call from agent |
| CPI/RTI message processing log read | SAP Integration Suite | SAP IS CPI Message Processing Logs REST API (no public ORD ID) | — | **Yes** | No public API spec on Accelerator Hub; implement structured MISSING_DATA stub |
| bgRFC queue status read | SAP S/4HANA | S/4HANA Business Events Queue OData (no public ORD ID confirmed) | — | **Yes** | No confirmed public API; implement structured MISSING_DATA stub with SM58 guidance |
| SAP Application Logs read (SLG1 equivalent) | SAP S/4HANA | Application Logs OData (no public ORD ID confirmed) | — | **Yes** | Partial — API spec found on hub without ORD ID; implement stub if not accessible |
| SAP Cloud ALM integration health events | SAP Cloud ALM | SAP Cloud ALM REST API (external product, separate authentication) | — | **Yes** | Requires separate Cloud ALM tenant credentials; implement stub if not configured |
| SAP PI/PO message monitoring | SAP PI/PO (legacy middleware) | SAP PI/PO Message Monitoring API | — | **Yes** | Legacy landscape only; implement stub for parallel PI/PO environments |
| Cross-system evidence graph construction and persistence | No standard SAP product | — | — | **Yes** | Custom: HANA Cloud graph schema (IncidentRecord, EvidenceNode, EvidenceLink, FailureClassification, RemediationRecord) |
| Root cause classification with evidence tagging | No standard SAP product | — | — | **Yes** | Custom: deterministic Python classification rules + LLM narration layer |
| 14-section forensic report (Consultant + Planner views) | No standard SAP product | — | — | **Yes** | Custom: report generation with structured output streaming |
| Learning engine (incident persistence, effectiveness model, pattern detection) | No standard SAP product | — | — | **Yes** | Custom: HANA Cloud relational tables + effectiveness scoring model |
| Predictive alert generation from pre-failure signatures | No standard SAP product (partial overlap with IBP Alerts) | — | — | **Yes** | Custom: background analysis mode scanning evidence graph history |
| OpenTelemetry instrumentation (M1–M5, L1–L5 spans) | SAP AI Core / BTP Observability | — | — | **Maybe** | SAP AI Core supports OTel; custom span naming required per spec |
| Pluggable MCP tool registry (discoverable at runtime) | SAP AI Core MCP Agent Gateway | — | — | **Maybe** | MCP Agent Gateway available on BTP; tool registry pattern must be implemented in agent |

### Key findings

- **Strong standard coverage for source systems**: SAP IBP and S/4HANA together provide mandatory standard capabilities for BPS-327 and BPS-349; all relevant S/4HANA OData APIs (Planned Order, PIR, PP/DS Stock, PP/DS Constraints, aATP, MRP) are available on the Accelerator Hub — no MCP servers exist for these, so the agent will call them directly as MCP tool wrappers.
- **Integration layer is the primary gap**: RTI/CPI message logs, bgRFC queue status, and SAP PI/PO monitoring have no confirmed public ORD IDs on the Accelerator Hub; these three systems require structured MISSING_DATA stubs in the agent tool layer with explicit manual investigation guidance.
- **No standard product covers the diagnostic intelligence layer**: The evidence graph, root cause classifier, forensic report generator, learning engine, and predictive alert generator are all custom developments — this is the core value of USCIA and cannot be addressed by configuration alone.
- **SAP HANA Cloud is the persistence and learning foundation**: Graph capabilities for evidence graph storage and traversal; relational tables for incident records and effectiveness scoring; this is a design dependency that must be provisioned as part of the solution.
- **Evidence-First and Graceful Degradation are architectural constraints, not features**: The agent must enforce read-only at the tool layer, never infer findings without evidence, and continue investigation when individual systems are unavailable — these must be enforced in the core agent framework, not just documented.
- **Phase 4 action execution must be architected now**: Autonomous corrective actions are out of scope for the current build, but every recommended action must carry `action_type` and `action_parameters` fields so Phase 4 can activate them without restructuring core logic.

## Recommendations

### USCIA — Autonomous Supply Chain Diagnostic Agent on SAP BTP AI Core

#### Executive Summary

Build USCIA as a pro-code Python AI agent (A2A) on SAP BTP AI Core, using pluggable MCP tool wrappers for all SAP system integrations and SAP HANA Cloud for evidence graph persistence and learning engine storage.

#### Recommended Solution

USCIA is implemented as a Python-based AI agent deployed on SAP BTP AI Core via Cloud Foundry, implementing the A2A (Agent-to-Agent) protocol. All SAP system integrations (S/4HANA OData APIs, IBP REST API, CPI REST API, Cloud ALM REST API) are implemented as MCP tool wrappers registered with the SAP MCP Agent Gateway — adding a new system requires only adding a new tool wrapper, with no changes to agent core logic. The agent core implements: (1) evidence collection via `asyncio.gather` across all 12 system tools in parallel; (2) deterministic Python root cause classification rules; (3) LLM-based narration and report generation via SAP AI Core Generative AI Hub — primary model GPT-4o, with automatic fallback to the highest-capability model available in the deployment if GPT-4o is unavailable; (4) HANA Cloud graph + relational persistence for evidence graphs, incident records, and the learning engine, sized for 100 investigations per day with minimum 20 concurrent sessions at peak; (5) OpenTelemetry instrumentation with custom spans for all M1–M5 milestones and L1–L5 learning steps. The CPI tool wrapper ships as a structured MISSING_DATA stub returning manual investigation guidance pointing to SXMB_MONI — replaced with live integration post-deployment when CPI API credentials and endpoint URLs are confirmed. The Cloud ALM tool wrapper ships as a MISSING_DATA stub, activated post-deployment when OAuth 2.0 credentials and integration health monitoring scope are configured. The agent enforces strict read-only at the MCP tool layer — no tool wrapper may implement write operations. The solution is deployed as an AI Core serving configuration with a Cloud Foundry-hosted agent runtime, exposed via the A2A protocol endpoint registered as a Joule-callable agent from day one. Users interact with USCIA through SAP Joule as the primary conversational interface. Direct A2A API access is available as a secondary interface for programmatic use and testing.

#### Problem Statement

Supply chain planning failure diagnosis currently requires 4–8 hours per incident, scarce cross-domain expertise spanning IBP, CPI/RTI, bgRFC, S/4HANA MRP, PP/DS, and aATP, produces inconsistent findings, and generates no reusable institutional knowledge. USCIA reduces investigation time to under 5 minutes, captures institutional knowledge in HANA Cloud after every investigation, and over time becomes predictively intelligent about recurring failure patterns in the landscape it monitors.

#### Affected User Roles

- Supply Chain Planners (IBP / S/4HANA)
- Supply Chain CoE teams and architects
- SAP AMS support teams and consultants
- PP/DS and IBP integration specialists

#### Important factors

##### Evidence-First architecture prevents hallucinated findings
The deterministic Python classification layer ensures that root cause categories are derived from retrieved API results, not from LLM inference from general SAP knowledge. The LLM receives structured evidence output and generates causal narrative — it never generates findings independently. This is critical for consultant credibility.

##### Pluggable MCP tool layer enables continuous extension
The MCP tool layer must be pluggable: adding a new system integration requires only adding a new tool wrapper without modifying agent core logic. Each tool wrapper is a self-contained module that registers itself with the MCP Agent Gateway at runtime — the agent discovers available tools from the registry rather than from a hard-coded list. Root cause classification rules must be externalised as a configurable rule set (e.g., YAML or JSON rules loaded at startup) so that new root cause categories and detection patterns can be added without code changes to the classifier. New systems (e.g., SAP EWM, SAP TM, SAP Ariba supply confirmation) can be added in Phase 3+ without touching agent core logic.

##### Graceful degradation preserves investigation value when systems are unavailable
A single unavailable system never aborts the investigation. The agent continues with available evidence, marks gaps explicitly as MISSING_DATA, and provides manual investigation guidance per system. If fewer than 3 of 12 systems respond, the agent warns of insufficient evidence coverage.

##### HANA Cloud persistence is the foundation for all three capability layers
Without HANA Cloud persistence, the learning engine and predictive intelligence layers cannot function. This is not optional infrastructure — it is a core architectural dependency. Evidence graph schema (IncidentRecord, EvidenceNode, EvidenceLink, FailureClassification, RemediationRecord) must be provisioned before the first investigation.

##### Phase 4 action execution layer must be designed now
Autonomous corrective actions are deferred to Phase 4, but the architecture must accommodate them without restructuring. Every remediation recommendation must carry machine-readable `action_type` and `action_parameters` fields from day one. This is a non-negotiable architectural constraint for the current build.

#### Potential risks

##### Integration layer API coverage gaps
RTI/CPI message logs, bgRFC queue status, and SAP PI/PO monitoring have no confirmed public ORD IDs. The agent will deliver reduced evidence coverage for these system boundaries until proper API credentials and endpoints are configured. Mitigation: structured MISSING_DATA stubs with explicit manual investigation guidance.

##### IBP OData/REST API authentication complexity
SAP IBP uses OAuth 2.0 with tenant-specific endpoints that vary by customer landscape. The IBP MCP tool wrapper must handle token management, tenant routing, and API version negotiation. This is the most complex integration in the agent's evidence collection layer.

##### HANA Cloud graph capability maturity
SAP HANA Cloud graph engine is production-ready but requires specific schema design for efficient traversal of evidence graphs with 50–200 nodes per investigation. Graph schema design and indexing strategy must be validated in the early development phase.

##### LLM inference quality for novel failure patterns
For failure patterns not yet in the training data (new IBP release behaviours, custom bgRFC configurations), the LLM narration layer may produce lower-confidence explanations. The confidence tagging system (HIGH/MEDIUM/LOW) and the [CONFIRMED]/[PROBABLE]/[MISSING DATA] evidence tags are the primary mitigations — they prevent overconfident output.

#### Deployment Target

| Parameter | Value |
| --------- | ----- |
| BTP Subaccount | [your value] |
| Organisation | [your value] |
| CF Space | [your value] |
| AI Core instance | [your value] |
| HANA Cloud instance | [your value] |
| S/4HANA destination name | [your value] |
| IBP destination name | [your value] |
| CPI destination name | [your value] |
| Cloud ALM destination name | [your value] |

#### Performance Requirements

- End-to-end investigation (M1 to M5 report delivery): under 5 minutes for single material, single plant, normal system load.
- Evidence collection (M2): all 12 system queries executed fully in parallel via `asyncio.gather` — no sequential fallback permitted.
- HANA persistence (L1): asynchronous — must not block or delay M5 report delivery to the user.
- Investigation volume: 10–20 investigations per day at initial launch, scaling to 50–100 per day as adoption grows; HANA Cloud and AI Core sized for 100 investigations per day as the planning target.
- Concurrent investigations: minimum 20 simultaneous investigation sessions supported without degradation.
- Predictive analysis scan (L5): complete within 10 minutes for a landscape with up to 500 active material-plant combinations.

#### Testing Requirements

- Unit tests for every MCP tool wrapper with mocked API responses.
- Unit tests for all deterministic root cause classification rules — one test per rule per root cause category.
- Unit tests for evidence graph construction, continuity key matching, and broken boundary detection.
- Unit tests for all 14 report sections — verify presence and structure.
- Unit tests for learning engine steps L1–L4 (persistence, outcome recording, effectiveness scoring, pattern detection).
- Integration test: end-to-end flow from material+plant input to 14-section report with mocked LLM and mocked system APIs.
- Minimum test coverage: 75%.
- All tests must pass before deployment.

#### Recommended solution category

AI Agent

#### Intent fit
95%
