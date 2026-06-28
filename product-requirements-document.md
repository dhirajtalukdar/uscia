# Product Requirements Document (PRD)

**Title:** Unified Supply Chain Intelligence Agent (USCIA)
**Date:** 2026-06-11
**Owner:** Supply Chain CoE
**Solution Category:** AI Agent

---

## Product Purpose & Value Proposition

**Elevator Pitch:**
Supply chain planning failures that span SAP IBP, RTI/CPI, bgRFC, S/4HANA MRP, PP/DS, and aATP currently take 4–8 hours per incident to diagnose and require expertise most organisations cannot staff permanently. USCIA eliminates this bottleneck by acting as an autonomous senior diagnostic consultant: it investigates any of 10 planning anomaly types end-to-end, retrieves live evidence from up to 12 systems in parallel, classifies root causes with explicit evidence tags, delivers a consultant-ready 14-section forensic report in under 5 minutes, and learns from every investigation to become predictively intelligent about recurring failure patterns.

**Business Need:**
Planning failures — missed planned orders, bgRFC blockages, CIF failures, PP/DS scheduling errors — are a recurring and costly operational risk in SAP-integrated supply chain landscapes. Diagnosis currently depends on scarce cross-domain experts, takes hours per incident, produces informal and inconsistent findings, and generates no reusable institutional knowledge. The problem compounds: the same root causes recur because nothing captures or acts on the pattern. USCIA addresses the full problem — not just the individual incident, but the institutional memory gap that allows the same failures to repeat.

**Expected Value:**
- Investigation time: 4–8 hours per incident → under 5 minutes
- Root cause consistency: informal, person-dependent → standardised classification with evidence tags
- Institutional knowledge: zero retention today → full evidence graph + remediation outcome history in HANA Cloud
- Recurring failures: undetected until impact → proactive alerts from pre-failure signature detection
- Consultant readiness: informal notes → structured 14-section forensic report, Consultant and Planner views

**Product Objectives (Prioritised):**
1. Deliver a complete, evidence-grounded forensic investigation for any of 10 planning anomaly types in under 5 minutes.
2. Build and persist a Supply Chain Evidence Graph to HANA Cloud after every investigation, forming the foundation for the learning engine.
3. Learn from investigation outcomes to improve remediation recommendation ranking and detect recurring failure patterns.
4. Generate proactive alerts before planning failures manifest, based on pre-failure signature patterns identified from investigation history.
5. Enforce strict read-only, evidence-first, and graceful degradation constraints at all times — never guess, never write, never abort on a single system failure.

---

## User Profiles & Personas

### Primary Persona: Maya — Supply Chain Planner

Maya is a 35-year-old supply chain planner at a discrete manufacturing company running SAP IBP integrated with S/4HANA and embedded PP/DS. She manages demand-supply alignment for 200+ materials across 4 plants. Two or three times a month she encounters a planning failure — a planned order that should exist in MD04 doesn't, or a PP/DS schedule is blank when it should be populated. Her investigation process is painful: she opens MD04, SLG1, SM58, IBP Monitor, and RRP3 in separate sessions, cross-referencing object references manually. She often hits the limit of her knowledge at the CPI/RTI layer and has to escalate to the integration team, which adds days. She wants to understand what happened and why, get a clear recommended action, and move on. She is technically proficient with SAP transactions but not with API or integration layer concepts.

**Goals:** Identify the root cause of a planning failure fast, get a clear and actionable recommended fix, and understand the business impact so she can communicate it to her manager.
**Key tasks:** Trigger an investigation from a natural language description of the anomaly, confirm material/plant/date context, review the Planner View of the forensic report, pass the escalation path to the right team.

### Secondary Persona: Daniel — Supply Chain CoE Architect

Daniel is a 42-year-old supply chain architect who owns the IBP-to-S/4HANA integration design. He is the person Maya escalates to. He spends significant time each month performing post-mortems on recurring failures, creating runbooks that are never used twice, and onboarding new AMS team members who make the same diagnostic mistakes. He wants a tool that produces a consultant-quality forensic report he can attach to an incident ticket, surfaces recurring patterns across the landscape, and — eventually — acts autonomously on low-risk fixes. He is comfortable with API concepts, HANA, and SAP integration architecture.

**Goals:** Reduce escalation volume from planners, build institutional memory about failure patterns, get evidence-backed forensic reports for incident tickets, and identify systemic issues before they require production escalation.
**Key tasks:** Review Consultant View of forensic reports, analyse recurring pattern alerts, track remediation effectiveness over time, configure new system integrations as MCP tool wrappers.

### Secondary Persona: Priya — AMS Support Consultant

Priya is a 31-year-old AMS consultant supporting multiple customer landscapes. She handles 5–10 planning incident tickets per week across IBP, S/4HANA, and PP/DS. Her knowledge is broad but not always deep on any specific customer's configuration. She spends most of her investigation time gathering basic evidence — queue status, message IDs, MRP type settings — before she can even begin to reason about root cause. She needs a tool that does the evidence gathering for her and gives her a structured starting point, even when some system APIs are unavailable.

**Goals:** Reduce time-to-first-finding per incident, deliver consistent and defensible root cause classifications, and produce a report she can include in the customer ticket without manual reformatting.
**Key tasks:** Trigger investigation with available context (material, plant, approximate date), review Consultant View, use the SAP Objects to Check and Logs and Transactions sections as a guided investigation checklist for any MISSING DATA gaps.

---

## User Goals & Tasks

### For Maya (Supply Chain Planner):
**Goals:**
- Understand why a planned order is missing or incorrect within her shift, without escalating to the integration team
- Receive a plain-English explanation of business impact and a recommended next action

**Key Tasks:**
- Describe the anomaly in natural language or provide material/plant/date as structured input
- Confirm or correct the agent's interpretation of incident type and context
- Review the Planner View: executive summary, business impact, escalation path, recommended action

### For Daniel (CoE Architect):
**Goals:**
- Access a full technical forensic report with evidence references for any investigation
- Identify which materials/plants are experiencing recurring failures and why
- Extend the agent with new system integrations without architectural rework

**Key Tasks:**
- Review Consultant View with API evidence references and SAP transaction guidance
- Monitor recurring pattern alerts and remediation effectiveness trends
- Register new MCP tool wrappers for additional systems

### For Priya (AMS Consultant):
**Goals:**
- Conduct a complete evidence-gathering step in minutes, not hours
- Produce a customer-ready incident report without manual compilation

**Key Tasks:**
- Trigger investigation with partial context; let agent handle parallel evidence collection
- Use MISSING DATA guidance sections as a structured manual checklist for inaccessible systems
- Export or attach the Consultant View to the incident ticket

---

## Product Principles

1. **Evidence before narrative:** Every finding in every report must be traceable to a specific tool call result. The LLM narrates evidence — it never generates findings from general knowledge.
2. **Never abort, always deliver:** A single unavailable system produces a MISSING DATA note with manual guidance — not a failed investigation. The report is always delivered.
3. **Strict read-only:** No tool wrapper may implement a write, create, update, or delete operation on any system. This constraint is absolute and enforced at the tool layer, not just documented.
4. **Phase 4 ready from day one:** Every remediation recommendation carries machine-readable `action_type`, `action_parameters`, and `requires_approval` fields so autonomous execution can be activated in Phase 4 without modifying report or classification logic.
5. **Pluggable by design:** Adding a new system integration or a new root cause classification rule must never require changes to agent core logic. New tool = new wrapper. New rule = updated external YAML/JSON rule set.

---

## Business Context

**Current State:**
Planning failure investigations are manual, informal, and time-consuming. There is no standard diagnostic process. Each investigation produces findings in the investigator's head or in an informal email. The same root causes recur because no system captures what was found or whether the fix worked. Escalation paths are personal relationships, not documented processes.

**Strategic Alignment:**
USCIA supports the organisation's supply chain resilience and digitalisation strategy by eliminating a known operational bottleneck, building institutional knowledge, and creating the foundation for autonomous corrective action in a future phase.

**Success Criteria:**
- End-to-end investigation (M1 to M5 report delivery) completed in under 5 minutes for single material, single plant
- Minimum 20 concurrent investigation sessions supported without degradation
- Forensic report covers all 14 mandatory sections in 100% of completed investigations
- HANA Cloud evidence graph persisted for 100% of completed investigations
- Recurring pattern correctly detected and flagged when ≥3 same-category incidents occur for same material-plant within 90 days
- Test coverage ≥75%; all tests pass before deployment

---

## Goals and Non-Goals

### Goals (In Scope)
- Autonomous investigation of all 10 planning anomaly types (see incident type scope below)
- Parallel evidence collection from up to 12 systems via `asyncio.gather`
- Supply Chain Evidence Graph construction, broken boundary identification, and HANA Cloud persistence
- Deterministic Python root cause classification across 8 categories with LLM narration
- 14-section forensic report in Consultant View and Planner View
- Machine-readable remediation fields (`action_type`, `action_parameters`, `requires_approval`) on every recommendation
- Learning engine: incident persistence (L1), outcome tracking (L2), effectiveness model (L3), pattern detection (L4), predictive alerts (L5)
- OpenTelemetry instrumentation with custom spans for M1–M5 and L1–L5
- Pluggable MCP tool layer with runtime-discoverable tool registry
- Externalised classification rule set (YAML/JSON) — new categories without code changes
- Graceful degradation: structured MISSING_DATA responses for unavailable systems
- Deployment on SAP BTP AI Core via Cloud Foundry, A2A protocol endpoint

### Non-Goals (Out of Scope — Current Build)
- Autonomous corrective actions of any kind (Phase 4)
- Write, create, update, or delete operations on any SAP system
- IBP planning job re-trigger (Phase 4, requires mandatory human approval gate)
- Master data changes of any kind (permanently out of scope)
- ECC / SAP APO legacy landscape support
- S/4HANA Cloud Public Edition (deferred — insufficient PP/DS capability)
- Multi-tenant SaaS deployment

---

## Requirements

### Must-Have Requirements

**R01: Investigation Context Capture (M1)**
- **Problem to Solve:** Users describe planning anomalies in inconsistent ways; the agent must extract a structured investigation context before evidence collection begins.
- **User Story:** As a supply chain planner, I need to describe a planning anomaly in natural language or structured JSON so that the agent captures the correct material, plant, planning version, date range, incident type, and continuity keys before proceeding.
- **Acceptance Criteria:**
  - Given a natural language description, when the agent processes it, then it identifies or asks for: material, plant, planning version, date range, incident type (one of 10), and at least one continuity key.
  - Given ambiguous input, when context is incomplete, then the agent asks one clarifying question at a time before proceeding to M2.
  - Given fully structured JSON input with all required keys, when submitted, then the agent proceeds to M2 without clarifying questions.
- **Maps to Objective:** 1
- **Priority Rank:** 1

**R02: Parallel Multi-System Evidence Collection (M2)**
- **Problem to Solve:** Evidence is spread across up to 12 systems; sequential collection would exceed the 5-minute SLA and leave gaps when any one system is slow.
- **User Story:** As an AMS consultant, I need the agent to query all available systems simultaneously so that I receive a complete evidence payload in seconds, not minutes.
- **Acceptance Criteria:**
  - Given an investigation context, when M2 begins, then all 12 system queries are issued in parallel via `asyncio.gather` — no sequential fallback permitted.
  - Given an unavailable system, when its query fails or times out, then the agent records a MISSING_DATA node with the system name, error description, relevant SAP transaction for manual investigation, and continues without aborting.
  - Given fewer than 3 of 12 systems responding, when evidence collection completes, then the agent warns the user that evidence coverage is insufficient for a reliable classification before proceeding.
- **Maps to Objective:** 1
- **Priority Rank:** 2

**R03: Supply Chain Evidence Graph Construction and Persistence (M3)**
- **Problem to Solve:** Evidence nodes from different systems have no shared identity unless explicitly correlated; without correlation, broken boundaries cannot be identified.
- **User Story:** As a CoE architect, I need a correlated evidence graph persisted to HANA Cloud after every investigation so that patterns across investigations can be analysed and the learning engine has a foundation.
- **Acceptance Criteria:**
  - Given a completed evidence payload, when M3 runs, then all nodes are correlated using continuity keys: Material+Plant, EXTERNID, ORDID, GUID, Integration Message ID, Queue Reference, and timestamp proximity (<5 minutes fallback).
  - Given a missing link between system A and system B for the same continuity key, when the graph is built, then the broken boundary is explicitly identified and flagged as the primary finding for that system pair.
  - Given a completed evidence graph, when M3 completes, then the full graph (IncidentRecord, EvidenceNode, EvidenceLink, FailureClassification, RemediationRecord) is persisted to SAP HANA Cloud asynchronously before M4 begins.
- **Maps to Objective:** 2
- **Priority Rank:** 3

**R04: Deterministic Root Cause Classification with Evidence Tags (M4)**
- **Problem to Solve:** LLM-only classification produces inconsistent and occasionally hallucinated root causes; planners and consultants need to trust the findings.
- **User Story:** As an AMS consultant, I need every root cause finding to be tagged with its evidence basis so that I can defend the classification in a customer ticket.
- **Acceptance Criteria:**
  - Given a completed evidence graph, when M4 runs, then deterministic Python rules classify the root cause into one of: IBP_PLANNING_GAP, RTI_CPI_MESSAGE_FAILURE, BGRFC_QUEUE_BLOCKAGE, MASTER_DATA_CONFIG_ERROR, CIF_TRANSFER_FAILURE, PPDS_SCHEDULING_FAILURE, ATP_SCOPE_MISMATCH, OTHER.
  - Given any finding in the report, when the report is generated, then every finding carries one of: [CONFIRMED] (evidence retrieved from live API), [PROBABLE] (inferred from partial evidence), [MISSING DATA] (insufficient evidence for classification).
  - Given zero API results for a system, when classification runs, then the agent records MISSING DATA for that system boundary — never "no issue found".
  - Given a completed classification, when M4 completes, then every remediation recommendation includes: `action_type` (one of: RESTART_BGRFC, REPROCESS_CPI_MESSAGE, RERUN_PPDS_HEURISTIC, RERUN_MRP_SINGLE_ITEM, RERUN_IBP_JOB, MANUAL_ONLY), `action_parameters` (JSON with object references), `requires_approval: true`.
- **Maps to Objective:** 1, 5
- **Priority Rank:** 4

**R05: 14-Section Forensic Report in Two Views (M5)**
- **Problem to Solve:** Planners and consultants have fundamentally different information needs from the same investigation; a single report format serves neither well.
- **User Story:** As a supply chain planner, I need a plain-English summary with business impact and a clear recommended action; as a consultant, I need the full technical evidence trail with SAP object references and transaction codes.
- **Acceptance Criteria:**
  - Given a completed classification, when M5 runs, then the agent generates a report containing all 14 mandatory sections: Executive Summary, Issue Classification, Affected System Boundary, Evidence Timeline, Evidence Graph Summary, Confirmed Findings, Probable Root Causes, Missing Data Gaps, Recommended Actions, SAP Objects to Check, Logs and Transactions to Review, Business Impact, Escalation Path, Preventive Recommendation.
  - Given a Consultant View request, when the report renders, then all sections include SAP object references, error codes, API evidence citations, and transaction names.
  - Given a Planner View request, when the report renders, then all sections use plain English with no technical jargon; business impact and escalation path are the lead sections.
  - Given a completed report, when M5 completes, then the report is streamed to the user and the incident ID from HANA persistence (L1) is returned at the end of the report.
- **Maps to Objective:** 1
- **Priority Rank:** 5

**R06: Investigation Scope — 10 Incident Types**
- **Problem to Solve:** Planning failures span a wide range of anomaly types; a tool that handles only one type forces manual investigation for the rest.
- **User Story:** As a supply chain planner, I need the agent to handle any planning anomaly I encounter — not just missing planned orders — so that I have a single investigation tool for all supply chain failure types.
- **Acceptance Criteria:**
  - The agent correctly identifies and handles all of the following incident types: (1) planned order missing in MD04, (2) planned order not reaching PP/DS RRP3, (3) quantity/date inconsistency between IBP and S/4HANA, (4) PIR exists but no planned order created, (5) PP/DS scheduling failure, (6) aATP confirmation missing or incorrect, (7) CIF transfer failure, (8) IBP planning job failure, (9) RTI/CPI message failure, (10) bgRFC queue blockage.
  - For each incident type, the agent selects the relevant evidence sources and continuity keys appropriate to that failure mode.
- **Maps to Objective:** 1
- **Priority Rank:** 6

**R07: Pluggable MCP Tool Layer**
- **Problem to Solve:** Hard-coded system integrations require core logic changes every time a new system is added, creating a maintenance bottleneck and architectural fragility.
- **User Story:** As a CoE architect, I need to add a new system integration by creating a single tool wrapper so that I can extend USCIA to cover new systems without modifying agent core logic.
- **Acceptance Criteria:**
  - Given a new MCP tool wrapper, when it is registered with the MCP Agent Gateway, then the agent discovers and uses it at runtime without any changes to agent core logic or the tool registry configuration file.
  - Given the root cause classification rule set (YAML/JSON), when a new rule is added and the agent restarts, then the new rule is applied without code changes to the classifier.
  - Given any tool wrapper, when it is invoked, then it may only perform read operations — any write, create, update, or delete call from a tool wrapper is a build-blocking defect.
- **Maps to Objective:** 5
- **Priority Rank:** 7

**R08: Learning Engine — Incident Persistence and Outcome Tracking (L1–L2)**
- **Problem to Solve:** Without persisting investigation results and remediation outcomes, the same root causes recur and the same fixes are recommended regardless of their effectiveness.
- **User Story:** As a CoE architect, I need every completed investigation and its remediation outcome to be recorded in HANA Cloud so that recommendation quality improves over time.
- **Acceptance Criteria:**
  - Given a completed M5 report, when L1 runs asynchronously, then the full investigation (evidence graph, classification, report sections, recommended actions, material, plant, incident type, timestamp) is persisted to HANA Cloud with a unique incident ID — L1 must not delay M5 report delivery.
  - Given a user returning to report a remediation outcome, when they provide one of (Resolved / Partially Resolved / Not Resolved / Made Worse), then the outcome is linked to the specific remediation action and root cause category in the HANA incident store.
- **Maps to Objective:** 2, 3
- **Priority Rank:** 8

**R09: Learning Engine — Effectiveness Model and Pattern Detection (L3–L4)**
- **Problem to Solve:** Remediation recommendations are static today; the same action is recommended regardless of whether it has worked in this landscape before.
- **User Story:** As a CoE architect, I need recommendations ranked by their historical effectiveness in my landscape so that planners act on the most likely fix first.
- **Acceptance Criteria:**
  - Given a history of remediation outcomes, when L3 runs, then it maintains an effectiveness score per (root_cause_category, recommended_action) pair: resolution rate, average resolution time, and failure mode.
  - Given a completed investigation, when L3 applies, then recommendations are ranked by their effectiveness score for the same root cause category — highest-scoring action ranked first.
  - Given an investigation that completes, when L4 runs, then it queries the HANA incident store for the same material-plant and root cause category; if ≥3 occurrences in 90 days, a RECURRING PATTERN section is added to the report; if ≥5 occurrences, the pattern is flagged as a systemic issue requiring a permanent fix.
- **Maps to Objective:** 3
- **Priority Rank:** 9

**R10: Predictive Alert Generation (L5)**
- **Problem to Solve:** Planning failures are detected after they occur; by then, production impact has already happened.
- **User Story:** As a CoE architect, I need the agent to alert me when pre-failure conditions are building so that I can intervene before a failure reaches MD04 or RRP3.
- **Acceptance Criteria:**
  - Given a scheduled or on-demand predictive analysis run, when L5 executes, then it scans the evidence graph history for pre-failure signatures: bgRFC queue depth trending upward, IBP job duration increasing, CPI message lag increasing, master data change events preceding MASTER_DATA_CONFIG_ERROR incidents.
  - Given a detected pre-failure signature for an active material-plant combination, when L5 fires, then it generates a proactive alert containing: the signature type, historical pattern basis (incident IDs), affected material-plant, and recommended preventive action.
  - Given a landscape with up to 500 active material-plant combinations, when L5 runs, then it completes within 10 minutes.
- **Maps to Objective:** 4
- **Priority Rank:** 10

**R11: OpenTelemetry Instrumentation**
- **Problem to Solve:** Without structured observability, production issues in the agent itself (slow evidence collection, classification failures, HANA persistence errors) are invisible until users report them.
- **User Story:** As a CoE architect, I need every investigation milestone and learning step to emit a structured OpenTelemetry span so that I can monitor agent health, identify slow integrations, and debug production incidents.
- **Acceptance Criteria:**
  - Given any investigation, when each milestone completes, then a custom OTel span is emitted: `uscia.m1_context_capture`, `uscia.m2_evidence_collection`, `uscia.m3_evidence_graph`, `uscia.m4_root_cause`, `uscia.m5_report`.
  - Given any learning step, when it completes, then a custom OTel span is emitted: `uscia.l1_persistence`, `uscia.l2_outcome_tracking`, `uscia.l3_effectiveness`, `uscia.l4_pattern_detection`, `uscia.l5_predictive_alert`.
  - Given the structured log convention, when a milestone is achieved, then the log statement follows the pattern defined in the Milestones section of this PRD.
- **Maps to Objective:** 5
- **Priority Rank:** 11

---

## Non-Functional Requirements

### Performance
- **End-to-end investigation (M1–M5):** Under 5 minutes for single material, single plant, normal system load.
- **Evidence collection (M2):** All 12 system queries in parallel via `asyncio.gather` — no sequential fallback permitted.
- **HANA persistence (L1):** Asynchronous — must not block or delay M5 report delivery.
- **Investigation volume:** 10–20 investigations per day at initial launch, scaling to 50–100 per day as adoption grows. HANA Cloud sizing and AI Core concurrency configuration based on 100 investigations per day as the planning target.
- **Concurrent sessions:** Minimum 20 simultaneous investigations supported at peak without degradation.
- **Predictive scan (L5):** Under 10 minutes for up to 500 active material-plant combinations.

### Reliability
- **Availability:** Agent runtime availability target aligned with SAP BTP CF SLA.
- **Fallback:** Single unavailable system → MISSING_DATA node + manual guidance. Fewer than 3 of 12 systems available → user warning before classification. Investigation is never aborted by a single system failure.

### Explainability
- **Traceability:** Every finding in every report cites the specific tool call result, system name, and continuity key that supports it.
- **Decision Logging:** All milestone log statements (M1–M5, L1–L5) are emitted as structured logs and OTel spans.
- **Uncertainty Communication:** Every finding is tagged [CONFIRMED], [PROBABLE], or [MISSING DATA]. Root cause classification carries a confidence level: HIGH, MEDIUM, or LOW.

### Security
- **Read-only enforcement:** Enforced at the MCP tool layer — no tool wrapper may implement write operations. Violations are build-blocking defects.
- **Credentials:** SAP system credentials managed via BTP Destination Service; no credentials stored in agent code or environment variables.

---

## Solution Architecture

**Architecture Overview:**
USCIA is a Python-based AI agent deployed on SAP BTP AI Core via Cloud Foundry, exposing an A2A protocol endpoint. All SAP system integrations are implemented as MCP tool wrappers registered with the SAP MCP Agent Gateway. The agent core orchestrates evidence collection, deterministic classification, LLM narration, and report generation. SAP HANA Cloud provides both graph storage (evidence graph) and relational storage (incident records, learning engine tables). SAP AI Core Generative AI Hub provides the LLM for narration and report generation.

**Key Components:**

| Component | Purpose |
|---|---|
| Agent Core (Python, A2A) | Orchestrates M1–M5 investigation flow and L1–L5 learning steps |
| MCP Tool Registry | Runtime-discoverable registry of all system integration wrappers |
| S/4HANA Tool Wrappers (×8) | Planned Order, PIR, PP/DS Stock, PP/DS Constraints, Business Events Queue, Application Logs, aATP Check, Material Planning Data — all read-only OData |
| IBP Tool Wrapper | IBP OData/REST API — planning jobs, key figures, supply objects, alerts |
| CPI Tool Wrapper (stub) | SAP Integration Suite CPI message logs — MISSING_DATA stub at go-live; returns manual investigation guidance pointing to SXMB_MONI; replaced with live integration post-deployment when CPI API credentials and endpoint URLs are confirmed for the target landscape |
| PI/PO Tool Wrapper (stub) | SAP PI/PO message monitoring — MISSING_DATA stub for legacy middleware landscapes |
| Cloud ALM Tool Wrapper (stub) | SAP Cloud ALM REST API — MISSING_DATA stub at go-live; activated post-deployment when OAuth 2.0 credentials and integration health monitoring scope are configured; does not block build or deployment |
| Evidence Graph Engine | Correlates evidence nodes by continuity keys; identifies broken boundaries |
| Deterministic Classifier | Python rule engine loaded from external YAML/JSON rule set |
| LLM Narration Layer | SAP AI Core Generative AI Hub — primary model GPT-4o; automatic fallback to highest-capability available model if GPT-4o unavailable; narrates evidence, generates report text |
| Report Generator | Produces 14-section report in Consultant and Planner views; streams to user |
| HANA Cloud Persistence | Graph tables (evidence graph) + relational tables (incidents, learning engine); sized for 100 investigations/day planning target |
| Learning Engine | L1–L5 async post-investigation processing |
| OTel Instrumentation | Custom spans for all M1–M5 and L1–L5 steps |
| Joule Integration | A2A endpoint registered as Joule-callable agent at go-live; Joule is the primary conversational UX; direct A2A API access available as secondary interface for programmatic use and testing |

**Integration Points:**

| System | Integration Type | Direction | Notes |
|---|---|---|---|
| SAP S/4HANA | OData (8 APIs) | Read | Via BTP Destination Service |
| SAP IBP | OData + REST | Read | OAuth 2.0; tenant-specific endpoint |
| SAP Integration Suite (CPI) | REST | Read | MISSING_DATA stub if API not accessible |
| SAP PI/PO | REST | Read | MISSING_DATA stub for legacy middleware |
| SAP Cloud ALM | REST | Read | MISSING_DATA stub if credentials not configured |
| SAP HANA Cloud | HANA Client (Python) | Read/Write | Evidence graph and learning engine persistence only |
| SAP AI Core Gen AI Hub | REST | Read | LLM inference for narration and report generation |

**Deployment Environments:**

| Environment | Purpose |
|---|---|
| Dev | Development and unit testing with mocked API responses |
| QA | Integration testing with mocked LLM and mocked system APIs |
| Prod | Live investigation against production SAP landscape |

**Deployment Target:**

| Parameter | Value |
|---|---|
| BTP Subaccount | [your value] |
| Organisation | [your value] |
| CF Space | [your value] |
| AI Core instance | [your value] |
| HANA Cloud instance | [your value] |
| S/4HANA destination name | [your value] |
| IBP destination name | [your value] |
| CPI destination name | [your value] |
| Cloud ALM destination name | [your value] |
| Joule Studio tenant | [your value] |
| A2A endpoint URL | [configured at deployment] |

---

### Agent Extensibility & Instrumentation

**Agent Extensibility:**
- The MCP tool layer is pluggable: adding a new system integration requires only creating a new tool wrapper module that registers itself with the MCP Agent Gateway. No changes to agent core logic, orchestration, or evidence graph construction are required.
- Root cause classification rules are externalised as a YAML or JSON rule set loaded at agent startup. New root cause categories and detection patterns are added by updating the rule file — no code changes to the classifier are required.
- The remediation action structure (`action_type`, `action_parameters`, `requires_approval`) is designed as the Phase 4 execution contract. When autonomous action is activated in Phase 4, the action execution layer reads these fields directly — no modifications to the report generator or classification logic are required.
- Extension points available from day one: tool registry (new systems), rule set (new categories), action executor (Phase 4 only), report renderer (new views), learning engine (new signal types for L5).

**Business Step Instrumentation:**
All five investigation milestones (M1–M5) and all five learning steps (L1–L5) emit structured log statements and OpenTelemetry custom spans. Span naming convention: `uscia.<step_id>`. Log statements follow the pattern: `<STEP_ID>.achieved: <description>` on success, `<STEP_ID>.missed: <description>` on failure or skip. See Milestones section for full log statement definitions.

---

### Automation & Agent Behaviour

**Automation Level:** Autonomous agent with deterministic pre-classification layer

**Actions the agent performs without human approval:**
- Query all 12 systems in parallel and collect evidence
- Correlate evidence nodes and build the Supply Chain Evidence Graph
- Apply deterministic classification rules
- Generate LLM-narrated forensic report
- Persist evidence graph and incident record to HANA Cloud (async)
- Run recurring pattern detection and predictive alert generation

**Actions that require human review or approval:**
- All remediation actions — the agent recommends only; `requires_approval: true` on every recommendation in the current build
- Remediation outcome reporting (user confirms what happened after acting on a recommendation)

**Model used:** GPT-4o via SAP AI Core Generative AI Hub. If GPT-4o is unavailable in the configured AI Core instance, the agent automatically falls back to the highest-capability model available in the Generative AI Hub deployment. The LLM receives structured evidence output and generates narration and report text only — it does not classify root causes or generate findings from general knowledge.

**Knowledge & data sources accessed:**

| Source | Purpose | Access |
|---|---|---|
| SAP S/4HANA (8 OData APIs) | Planned orders, PIR, PP/DS stock, constraints, queues, logs, aATP, MRP data | Read-only via BTP Destination |
| SAP IBP OData/REST | Planning jobs, key figures, supply objects, alerts | Read-only via BTP Destination |
| SAP Integration Suite CPI | RTI/CPI message processing logs | Read-only (MISSING_DATA stub if unavailable) |
| SAP PI/PO | Integration message monitoring | Read-only (MISSING_DATA stub for legacy) |
| SAP Cloud ALM | Integration health events | Read-only (MISSING_DATA stub if unconfigured) |
| SAP HANA Cloud | Evidence graph persistence and learning engine | Read/Write (persistence layer only) |

**Guardrails & fail-safes:**
- **Absolute read-only:** No tool wrapper may implement write, create, update, or delete operations. Enforced at the MCP tool layer. Violation is a build-blocking defect.
- **Evidence-first:** The agent never states a confirmed finding without a retrieved API result. LLM may not generate findings from general SAP knowledge.
- **Absence = MISSING DATA:** Zero API results for a system → MISSING DATA, never "no issue found."
- **Graceful degradation:** Single unavailable system → MISSING_DATA node with manual guidance; investigation continues. Fewer than 3 of 12 systems responding → user warned before classification.
- **Confidence tagging:** Every finding tagged [CONFIRMED], [PROBABLE], or [MISSING DATA]. Root cause confidence: HIGH, MEDIUM, LOW. No untagged output permitted.

---

## Governance, Risk & Compliance

**Data Handling:**
- USCIA operates on operational SAP data (order numbers, queue statuses, message IDs, planning figures). No PII is processed.
- All data retrieved from SAP systems is read-only and transient within the agent session; persisted data in HANA Cloud consists of technical planning object references and investigation metadata only.
- HANA Cloud instance is provisioned within the customer's BTP subaccount — data does not leave the customer's landscape.

**Compliance:**
- Strict read-only enforcement is the primary compliance control — the agent cannot modify any SAP system state.
- All agent actions are logged via OpenTelemetry spans and structured milestone log statements for auditability.

**Approval Flows:**
- All remediation recommendations carry `requires_approval: true` in the current build. No autonomous corrective action is taken.

---

## Release Criteria

- All 14 report sections present and structurally valid for every completed investigation
- End-to-end investigation SLA ≤5 minutes validated under load (20 concurrent sessions)
- HANA persistence confirmed for 100% of completed investigations
- All tests pass; coverage ≥75%
- OTel spans emitting correctly for M1–M5 and L1–L5
- All tool wrappers validated read-only (no write operation possible)
- MISSING_DATA stubs verified for CPI, PI/PO, and Cloud ALM — correct manual guidance returned
- Recurring pattern detection verified with synthetic incident history (≥3 and ≥5 thresholds)

---

## Milestones

### M1: Investigation Context Captured

- **Description:** Agent has confirmed the full investigation context from the user before any evidence collection begins.
- **Achieved when:** Material, plant, planning version, date range, incident type (one of 10), and at least one continuity key are confirmed.
- **Log on achievement:** `M1.achieved: investigation context captured — material={m}, plant={p}, version={v}, date_range={d}, incident_type={i}, continuity_keys={k}`
- **Log on miss:** `M1.missed: investigation context incomplete — missing_fields={fields}, reason={reason}`

### M2: Multi-System Evidence Collected

- **Description:** All 12 in-scope systems have been queried in parallel and the raw evidence payload consolidated.
- **Achieved when:** `asyncio.gather` completes for all 12 system queries; each returning either evidence nodes or a MISSING_DATA response.
- **Log on achievement:** `M2.achieved: evidence collected — systems_queried={n}, available={a}, unavailable={u}, evidence_nodes={e}`
- **Log on miss:** `M2.missed: evidence collection failed — error={error}, systems_attempted={n}`

### M3: Supply Chain Evidence Graph Built

- **Description:** All evidence nodes correlated by continuity keys; broken boundaries identified; graph persisted to HANA Cloud.
- **Achieved when:** Evidence graph constructed with all nodes and links; at least one broken boundary determination made; graph persisted to HANA Cloud.
- **Log on achievement:** `M3.achieved: evidence graph built — nodes={n}, links={l}, broken_boundaries={b}, persisted_to_hana=true`
- **Log on miss:** `M3.missed: evidence graph construction failed — error={error}, persisted_to_hana=false`

### M4: Root Cause Classified

- **Description:** Deterministic classification rules applied; LLM narration generated; all findings tagged; all remediation recommendations include Phase 4 execution fields.
- **Achieved when:** Root cause category assigned; confidence level set; all findings tagged [CONFIRMED], [PROBABLE], or [MISSING DATA]; all recommendations include `action_type`, `action_parameters`, `requires_approval`.
- **Log on achievement:** `M4.achieved: root cause classified — category={c}, confidence={HIGH|MEDIUM|LOW}, confirmed={n}, probable={n}, missing={n}`
- **Log on miss:** `M4.missed: root cause classification failed — error={error}, evidence_nodes_available={n}`

### M5: Consultant-Ready Forensic Report Delivered

- **Description:** Full 14-section forensic report streamed to the user in both Consultant and Planner views; incident ID from HANA persistence returned.
- **Achieved when:** All 14 sections generated and streamed; `persisted_incident_id` returned at end of report.
- **Log on achievement:** `M5.achieved: forensic report delivered — sections=14, duration_seconds={d}, root_cause={c}, persisted_incident_id={id}`
- **Log on miss:** `M5.missed: report delivery failed — sections_generated={n}, error={error}`

### L1: Incident Persisted to HANA Cloud

- **Description:** Complete investigation record (evidence graph, classification, report, remediation actions) persisted asynchronously after M5 completes.
- **Achieved when:** IncidentRecord with all linked entities written to HANA Cloud; unique incident ID confirmed.
- **Log on achievement:** `L1.achieved: incident persisted — incident_id={id}, nodes={n}, actions={a}`
- **Log on miss:** `L1.missed: incident persistence failed — incident_id={id}, error={error}`

### L2: Remediation Outcome Recorded

- **Description:** User-reported remediation outcome linked to the specific action and root cause category in the HANA incident store.
- **Achieved when:** Outcome (Resolved / Partially Resolved / Not Resolved / Made Worse) saved and linked to incident ID and action.
- **Log on achievement:** `L2.achieved: outcome recorded — incident_id={id}, action_type={a}, outcome={o}`
- **Log on miss:** `L2.missed: outcome recording failed — incident_id={id}, error={error}`

### L3: Remediation Effectiveness Score Updated

- **Description:** Effectiveness score updated for the (root_cause_category, recommended_action) pair based on the latest outcome.
- **Achieved when:** Resolution rate, average resolution time, and failure mode updated for the relevant pair.
- **Log on achievement:** `L3.achieved: effectiveness updated — category={c}, action={a}, resolution_rate={r}`
- **Log on miss:** `L3.missed: effectiveness update failed — category={c}, action={a}, error={error}`

### L4: Recurring Pattern Detection Run

- **Description:** Incident store queried for the same material-plant and root cause category; recurring pattern flag added to report if threshold met.
- **Achieved when:** Pattern query complete; RECURRING PATTERN section added if ≥3 occurrences in 90 days; systemic flag added if ≥5.
- **Log on achievement:** `L4.achieved: pattern detection complete — material={m}, plant={p}, occurrences={n}, pattern_flagged={true|false}, systemic={true|false}`
- **Log on miss:** `L4.missed: pattern detection failed — material={m}, plant={p}, error={error}`

### L5: Predictive Alert Generated

- **Description:** Background scan identifies pre-failure signatures for active material-plant combinations and generates proactive alerts.
- **Achieved when:** Scan completes within 10 minutes for up to 500 material-plant combinations; at least one alert generated when pre-failure signature detected.
- **Log on achievement:** `L5.achieved: predictive scan complete — combinations_scanned={n}, alerts_generated={a}, duration_seconds={d}`
- **Log on miss:** `L5.missed: predictive scan failed — combinations_scanned={n}, error={error}`

---

## Risks, Assumptions, and Dependencies

### Risks

- **Integration layer API coverage gaps:** RTI/CPI logs, bgRFC queue status, and PI/PO monitoring have no confirmed public ORD IDs. Evidence coverage for these system boundaries will be limited to MISSING_DATA stubs until API credentials and endpoints are configured per customer landscape.
- **IBP authentication complexity:** SAP IBP uses OAuth 2.0 with tenant-specific endpoints; the IBP tool wrapper must handle token lifecycle and API version negotiation — this is the highest-risk integration to implement.
- **HANA Cloud graph schema performance:** Evidence graphs of 50–200 nodes per investigation require careful schema design and indexing for efficient traversal. Schema must be validated early.
- **LLM narration quality for novel failure patterns:** For unusual IBP release behaviours or custom bgRFC configurations, LLM narration may produce lower-confidence explanations. The evidence tagging and confidence system is the primary mitigation.
- **Per-customer landscape variation:** MRP types, bgRFC queue names, IBP planning versions, and CIF configurations vary significantly by customer. Tool wrappers must handle configuration variance without hard-coded assumptions.

### Assumptions

- SAP BTP AI Core instance is available in the target subaccount with Generative AI Hub enabled.
- SAP HANA Cloud instance is available in the target BTP subaccount with graph and relational capabilities enabled.
- BTP Destination Service entries for S/4HANA, IBP, CPI, and Cloud ALM are configured before deployment.
- The target S/4HANA system is Cloud Private Edition or on-premise (Public Edition is out of scope).
- Customer is willing to configure API credentials for CPI, PI/PO, and Cloud ALM as part of the deployment; MISSING_DATA stubs are the baseline until they are configured.

### Dependencies

- SAP BTP AI Core (agent runtime and Generative AI Hub)
- SAP HANA Cloud (evidence graph and learning engine persistence)
- SAP BTP Destination Service (credential management for all SAP system connections)
- SAP MCP Agent Gateway (tool registry and runtime discovery)
- S/4HANA OData APIs: PLANNEDORDER_0001, API_MRP_MATERIALS_SRV_01, OP_API_PLND_INDEP_RQMT_SRV_0001, OP_PPDSPRODTDSTLV_0001, OP_APIFLEXIBLECONSTRAINTS_0001, CE_APIAVAILTOPROMISECHECK_0001
- SAP IBP OData/REST API (tenant-specific endpoint and OAuth credentials)

---

## Open Questions

All open questions resolved:

| Question | Answer |
|---|---|
| Target LLM model | GPT-4o via SAP AI Core Generative AI Hub; automatic fallback to highest-capability available model if GPT-4o unavailable |
| CPI REST API credentials | Stub at go-live. CPI tool wrapper ships as a structured MISSING_DATA stub returning manual investigation guidance pointing to SXMB_MONI. Replaced with live integration post-deployment when credentials and endpoint URLs are confirmed for the target landscape |
| SAP Cloud ALM | Stub at go-live. Cloud ALM tool wrapper ships as a MISSING_DATA stub. Activated post-deployment when OAuth 2.0 credentials and integration health monitoring scope are configured. Does not block build or deployment |
| Investigation volume | 10–20/day initially, scaling to 50–100/day. HANA Cloud and AI Core sized for 100 investigations/day planning target; minimum 20 concurrent sessions at peak |
| Joule integration | Integrated with SAP Joule Studio from day one. A2A endpoint configured and registered as a Joule-callable agent at go-live. Joule is the primary conversational UX — users interact with USCIA through Joule, not via direct API. Direct A2A API access available as secondary interface for programmatic use and testing |

---

## Appendix

### Glossary

| Term | Definition |
|---|---|
| A2A | Agent-to-Agent protocol — the communication protocol used by USCIA's endpoint |
| bgRFC | Background Remote Function Call — SAP asynchronous integration mechanism; blockages in bgRFC queues are a common cause of planning failures |
| CIF | Core Interface — SAP mechanism for transferring planned orders from S/4HANA MRP to embedded PP/DS |
| Continuity Key | An identifier (EXTERNID, ORDID, GUID, Message ID, etc.) used to link evidence nodes across system boundaries |
| Evidence Graph | A graph data structure connecting evidence nodes from multiple SAP systems via continuity keys |
| EXTERNID | External ID used by SAP IBP to identify supply objects; the primary continuity key across IBP and RTI/CPI |
| MCP | Model Context Protocol — the protocol used by USCIA's tool wrappers to expose SAP system integrations |
| MD04 | SAP transaction for the Material Requirements Planning supply/demand view |
| MISSING_DATA | Evidence tag applied when a system is unavailable or returns no results; never interpreted as "no issue" |
| PP/DS | Production Planning and Detailed Scheduling — embedded in SAP S/4HANA |
| RRP3 | SAP PP/DS planning board transaction |
| RTI | Real-Time Integration — SAP mechanism for transferring IBP supply outputs to S/4HANA |

### References

- SAP IBP Integration with S/4HANA — SAP Help Portal
- SAP S/4HANA Embedded PP/DS — SAP Help Portal
- SAP AI Core — Agent Framework Documentation
- SAP HANA Cloud Graph Engine — SAP Help Portal
- SAP BTP Destination Service — SAP Help Portal
- OpenTelemetry SDK for Python — opentelemetry.io
- A2A Protocol Specification — google.github.io/A2A
