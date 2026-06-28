# Specification: uscia-agent

> **Guidelines**: Read [guidelines.md](../guidelines.md) and [guidelines-agent.md](../guidelines-agent.md) before executing ANY tasks below. Follow all constraints described there throughout execution.

## Basic Setup

- [ ] Read `product-requirements-document.md` and `intent.md` thoroughly before starting
- [ ] Bootstrap agent code in `assets/uscia-agent/` using skill `sap-agent-bootstrap` (invoke from inside `assets/uscia-agent/`, use copy commands — do NOT create files manually)
- [ ] Install dependencies, validate the agent starts and responds at `/.well-known/agent.json`

---

## API Spec Discovery

> The following 6 S/4HANA OData APIs are required. EDMX spec files must be downloaded using fresh pre-signed URLs from `sap_knowledge_graph_api_discovery` at execution time (URLs expire in 3600s). Re-run discovery immediately before downloading.

| File | ORD ID | Description |
|------|--------|-------------|
| `specification/uscia-agent/api-specs/planned-order.edmx` | `sap.s4:apiResource:PLANNEDORDER_0001:v1` | Planned Order — read planned orders by material/plant |
| `specification/uscia-agent/api-specs/material-planning-data.edmx` | `sap.s4:apiResource:API_MRP_MATERIALS_SRV_01:v1` | Material Planning Data (MD04) — MRP type, lot size, reorder point |
| `specification/uscia-agent/api-specs/planned-independent-requirement.edmx` | `sap.s4:apiResource:OP_API_PLND_INDEP_RQMT_SRV_0001:v1` | Planned Independent Requirements (PIR) — demand basis verification |
| `specification/uscia-agent/api-specs/ppds-stock-level.edmx` | `sap.s4:apiResource:OP_PPDSPRODTDSTLV_0001:v1` | PP/DS Product Time-Dependent Stock Level — RRP3 evidence |
| `specification/uscia-agent/api-specs/ppds-flexible-constraints.edmx` | `sap.s4:apiResource:OP_APIFLEXIBLECONSTRAINTS_0001:v1` | PP/DS Flexible Constraints — scheduling failure evidence |
| `specification/uscia-agent/api-specs/advanced-atp-check.edmx` | `sap.s4:apiResource:CE_APIAVAILTOPROMISECHECK_0001:v1` | Advanced ATP Check — aATP confirmation evidence |

- [ ] Call `sap_knowledge_graph_api_discovery` with query "S/4HANA planned order MRP PIR PP/DS stock flexible constraints ATP" to get fresh download URLs
- [ ] Download all 6 EDMX files to `specification/uscia-agent/api-specs/` immediately after getting URLs
- [ ] Invoke `mcp-translation-file` skill for each downloaded EDMX to generate MCP translation files
  - If `mcp-translation-file` skill or `generate_mcp_translation` tool is unavailable, skip MCP translation and log: `[MCP-SKILL] mcp-translation-file unavailable — agent will use direct OData calls via MISSING_DATA pattern`
- [ ] Invoke `setup-solution` skill to register any generated MCP translation files as MCP server assets
- [ ] Generate `mcp-mock.json` using `mcp-mock-config` skill (required before tests)

---

## HANA Cloud Schema — Evidence Graph and Learning Engine

- [ ] Create `assets/uscia-agent/app/db/schema.sql` with the following tables:

  ```sql
  -- Core investigation record
  CREATE TABLE IF NOT EXISTS IncidentRecord (
      incident_id       VARCHAR(36) PRIMARY KEY,   -- UUID
      material          NVARCHAR(40) NOT NULL,
      plant             NVARCHAR(4)  NOT NULL,
      planning_version  NVARCHAR(10),
      date_range_start  DATE,
      date_range_end    DATE,
      incident_type     NVARCHAR(60) NOT NULL,      -- one of 10 types
      root_cause        NVARCHAR(60),               -- 8-category enum
      confidence        NVARCHAR(10),               -- HIGH | MEDIUM | LOW
      report_consultant NCLOB,
      report_planner    NCLOB,
      created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      duration_seconds  INTEGER
  );

  -- Evidence nodes from each system query
  CREATE TABLE IF NOT EXISTS EvidenceNode (
      node_id         VARCHAR(36) PRIMARY KEY,
      incident_id     VARCHAR(36) REFERENCES IncidentRecord(incident_id),
      system_name     NVARCHAR(60) NOT NULL,        -- e.g. S4HANA_PLANNED_ORDER
      status          NVARCHAR(20) NOT NULL,        -- AVAILABLE | MISSING_DATA
      raw_payload     NCLOB,
      manual_guidance NCLOB,                        -- populated for MISSING_DATA nodes
      created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  );

  -- Links between evidence nodes (continuity key correlations)
  CREATE TABLE IF NOT EXISTS EvidenceLink (
      link_id         VARCHAR(36) PRIMARY KEY,
      incident_id     VARCHAR(36) REFERENCES IncidentRecord(incident_id),
      from_node_id    VARCHAR(36) REFERENCES EvidenceNode(node_id),
      to_node_id      VARCHAR(36) REFERENCES EvidenceNode(node_id),
      continuity_key  NVARCHAR(60),                 -- MATERIAL_PLANT | EXTERNID | ORDID | GUID | MSG_ID | QUEUE_REF | TIMESTAMP_PROXIMITY
      continuity_val  NVARCHAR(255),
      broken_boundary BOOLEAN DEFAULT FALSE
  );

  -- Root cause classification and evidence tagging
  CREATE TABLE IF NOT EXISTS FailureClassification (
      classification_id VARCHAR(36) PRIMARY KEY,
      incident_id       VARCHAR(36) REFERENCES IncidentRecord(incident_id),
      root_cause        NVARCHAR(60) NOT NULL,
      confidence        NVARCHAR(10) NOT NULL,
      confirmed_count   INTEGER DEFAULT 0,
      probable_count    INTEGER DEFAULT 0,
      missing_count     INTEGER DEFAULT 0,
      findings          NCLOB    -- JSON array of {tag, description, evidence_node_id}
  );

  -- Recommended remediation actions (Phase 4 execution-ready)
  CREATE TABLE IF NOT EXISTS RemediationRecord (
      action_id        VARCHAR(36) PRIMARY KEY,
      incident_id      VARCHAR(36) REFERENCES IncidentRecord(incident_id),
      action_type      NVARCHAR(40) NOT NULL,   -- RESTART_BGRFC | REPROCESS_CPI_MESSAGE | RERUN_PPDS_HEURISTIC | RERUN_MRP_SINGLE_ITEM | RERUN_IBP_JOB | MANUAL_ONLY
      action_params    NCLOB NOT NULL,          -- JSON: queue_name, msg_id, material, plant, heuristic_profile, etc.
      requires_approval BOOLEAN DEFAULT TRUE,
      rank             INTEGER DEFAULT 1,       -- effectiveness-ranked position
      outcome          NVARCHAR(30),            -- Resolved | Partially Resolved | Not Resolved | Made Worse
      outcome_at       TIMESTAMP
  );

  -- Learning engine: remediation effectiveness scores
  CREATE TABLE IF NOT EXISTS EffectivenessScore (
      score_id        VARCHAR(36) PRIMARY KEY,
      root_cause      NVARCHAR(60) NOT NULL,
      action_type     NVARCHAR(40) NOT NULL,
      resolution_rate DECIMAL(5,4) DEFAULT 0.0,
      avg_resolution_hours DECIMAL(8,2) DEFAULT 0.0,
      total_attempts  INTEGER DEFAULT 0,
      total_resolved  INTEGER DEFAULT 0,
      updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      UNIQUE (root_cause, action_type)
  );
  ```

- [ ] Create `assets/uscia-agent/app/db/hana_client.py` — thin wrapper over `hdbcli.dbapi` connection pooling; reads `HANA_HOST`, `HANA_PORT`, `HANA_USER`, `HANA_PASSWORD` from environment; exposes `execute(sql, params)` and `fetchall(sql, params)` helpers
- [ ] Create `assets/uscia-agent/app/db/schema_init.py` — runs `schema.sql` at agent startup if tables do not exist; idempotent (uses `IF NOT EXISTS`)

---

## MCP Tool Wrappers — 12 System Integrations

### Group A — S/4HANA OData APIs (live, read-only)

- [ ] Create `assets/uscia-agent/app/tools/s4_planned_order.py`
  - Tool name: `get_planned_orders`
  - OData API: `PLANNEDORDER_0001` via MCP (from translated spec)
  - Inputs: `material`, `plant`, `date_from`, `date_to` (all strings)
  - Returns: list of planned order dicts with fields: `PlannedOrder`, `Material`, `Plant`, `PlannedOrderType`, `PlannedQuantity`, `ScheduledBasicStartDate`, `ScheduledBasicEndDate`, `EXTERNID` (or equivalent external ID field), `ProductionVersion`, `MRPController`
  - On failure: return `{"status": "MISSING_DATA", "system": "S4HANA_PLANNED_ORDER", "guidance": "Check MD04 (transaction MD04) for material {material} plant {plant}. Verify MRP run has been executed."}`

- [ ] Create `assets/uscia-agent/app/tools/s4_material_planning.py`
  - Tool name: `get_material_planning_data`
  - OData API: `API_MRP_MATERIALS_SRV_01` via MCP
  - Inputs: `material`, `plant`
  - Returns: dict with `MRPType`, `MRPController`, `LotSizeKey`, `ReorderPoint`, `SafetyStock`, `PlanningHorizon`, `PlannedDeliveryTime`, `ProductionVersion`
  - On failure: return `{"status": "MISSING_DATA", "system": "S4HANA_MATERIAL_PLANNING", "guidance": "Check material master MRP views (transaction MM03) for material {material} plant {plant}. Verify MRP type and planning horizon are maintained."}`

- [ ] Create `assets/uscia-agent/app/tools/s4_pir.py`
  - Tool name: `get_planned_independent_requirements`
  - OData API: `OP_API_PLND_INDEP_RQMT_SRV_0001` via MCP
  - Inputs: `material`, `plant`, `planning_version`, `date_from`, `date_to`
  - Returns: list of PIR dicts with `RequirementNumber`, `Material`, `Plant`, `PlanningVersion`, `RequirementsQty`, `RequirementsDate`, `ScheduleLine`
  - On failure: return `{"status": "MISSING_DATA", "system": "S4HANA_PIR", "guidance": "Check MD61/MD62 for independent requirements for material {material} plant {plant}."}`

- [ ] Create `assets/uscia-agent/app/tools/s4_ppds_stock.py`
  - Tool name: `get_ppds_stock_level`
  - OData API: `OP_PPDSPRODTDSTLV_0001` via MCP
  - Inputs: `material`, `plant`, `date_from`, `date_to`
  - Returns: list of time-dependent stock level snapshots with `TimeStamp`, `StockQuantity`, `StockUnit`, `ProductionOrderKey`
  - On failure: return `{"status": "MISSING_DATA", "system": "S4HANA_PPDS_STOCK", "guidance": "Check PP/DS stock situation via RRP3 (transaction RRP3) or /SAPAPO/RRP3 for material {material} plant {plant}."}`

- [ ] Create `assets/uscia-agent/app/tools/s4_ppds_constraints.py`
  - Tool name: `get_ppds_flexible_constraints`
  - OData API: `OP_APIFLEXIBLECONSTRAINTS_0001` via MCP
  - Inputs: `material`, `plant`
  - Returns: list of constraint definitions with `ConstraintID`, `ConstraintType`, `ValidFrom`, `ValidTo`, `CapacityLimitValue`, `WorkCenter`
  - On failure: return `{"status": "MISSING_DATA", "system": "S4HANA_PPDS_CONSTRAINTS", "guidance": "Check flexible constraints in PP/DS via /SAPAPO/CDPS0 or constraint editor for plant {plant}."}`

- [ ] Create `assets/uscia-agent/app/tools/s4_atp.py`
  - Tool name: `get_atp_check_result`
  - OData API: `CE_APIAVAILTOPROMISECHECK_0001` via MCP
  - Inputs: `material`, `plant`, `requested_quantity`, `requested_date`
  - Returns: dict with `ConfirmedQuantity`, `ConfirmedDate`, `ATPScope`, `BackorderProcessingActive`, `CheckRuleDescription`
  - On failure: return `{"status": "MISSING_DATA", "system": "S4HANA_ATP", "guidance": "Check ATP configuration in CO09 for material {material} plant {plant}. Verify ATP check rule and scope assignment."}`

- [ ] Create `assets/uscia-agent/app/tools/s4_app_logs.py`
  - Tool name: `get_application_logs`
  - Stub tool — no confirmed public OData API
  - Returns always: `{"status": "MISSING_DATA", "system": "S4HANA_APPLICATION_LOGS", "guidance": "Check application logs in SLG1 (transaction SLG1). Filter by object: MPLANORD (MRP planned orders), APOCIF (CIF transfer), or MRP_PP_DS (PP/DS scheduling). Date range: {date_from} to {date_to}."}`

- [ ] Create `assets/uscia-agent/app/tools/s4_bgrfc.py`
  - Tool name: `get_bgrfc_queue_status`
  - Stub tool — no confirmed public OData API
  - Returns always: `{"status": "MISSING_DATA", "system": "S4HANA_BGRFC_QUEUE", "guidance": "Check bgRFC queue status in SM58 (transaction SM58). Look for queues prefixed with APOC (CIF) or RSMPP (MRP). Filter by date: {date_from}. Check for SYSFAIL or CPICERR errors."}`

### Group B — SAP IBP (live OData/REST, read-only)

- [ ] Create `assets/uscia-agent/app/tools/ibp_supply.py`
  - Tool name: `get_ibp_supply_data`
  - Integration: SAP IBP OData/REST API — OAuth 2.0, tenant-specific endpoint from `IBP_BASE_URL` env var
  - Pattern: implement as MCP tool wrapper; reads `IBP_CLIENT_ID`, `IBP_CLIENT_SECRET`, `IBP_TOKEN_URL`, `IBP_BASE_URL` from environment; implements token caching with refresh on 401
  - Inputs: `material`, `plant`, `planning_version`, `date_from`, `date_to`
  - Returns: dict with `SupplyOrders` (list), `PlanningRunStatus`, `KeyFigures`, `LastRunTimestamp`, `EXTERNIDs` (list of external IDs for continuity key correlation)
  - On failure (any HTTP error or connection error): return `{"status": "MISSING_DATA", "system": "IBP_SUPPLY", "guidance": "Check IBP supply plan in IBP Monitor. Verify planning run completed for version {planning_version}. Check EXTERNID assignment for material {material} location {plant}."}`

### Group C — Integration Layer Stubs (MISSING_DATA at go-live)

- [ ] Create `assets/uscia-agent/app/tools/cpi_messages.py`
  - Tool name: `get_cpi_message_status`
  - Stub tool — CPI API credentials not available at go-live
  - Returns always: `{"status": "MISSING_DATA", "system": "SAP_CPI", "guidance": "Check CPI message processing in SXMB_MONI (transaction SXMB_MONI) or Integration Suite Message Monitor. Filter by interface: IBP_RTI_TO_S4HANA. Look for failed messages in the date range {date_from} to {date_to}. Message ID from IBP EXTERNID: {externid}."}`
  - Note: stub replacement path — when `CPI_BASE_URL`, `CPI_CLIENT_ID`, `CPI_CLIENT_SECRET` env vars are set, activate live integration

- [ ] Create `assets/uscia-agent/app/tools/pipo_messages.py`
  - Tool name: `get_pipo_message_status`
  - Stub tool — PI/PO legacy landscape only
  - Returns always: `{"status": "MISSING_DATA", "system": "SAP_PIPO", "guidance": "Check PI/PO message monitoring in SXMB_MONI (transaction SXMB_MONI) or RWB (Runtime Workbench). Filter by sender interface for IBP/RTI integration. Date range: {date_from} to {date_to}."}`

- [ ] Create `assets/uscia-agent/app/tools/cloud_alm.py`
  - Tool name: `get_cloud_alm_health_events`
  - Stub tool — Cloud ALM OAuth 2.0 not configured at go-live
  - Returns always: `{"status": "MISSING_DATA", "system": "CLOUD_ALM", "guidance": "Check SAP Cloud ALM integration health dashboard. Navigate to Integration & Exception Monitoring. Filter by scenario: IBP_TO_S4HANA. Date range: {date_from} to {date_to}."}`
  - Note: stub replacement path — when `CLOUD_ALM_BASE_URL`, `CLOUD_ALM_CLIENT_ID`, `CLOUD_ALM_CLIENT_SECRET` env vars are set, activate live OAuth 2.0 integration

---

## Evidence Collection Engine (M2)

- [ ] Create `assets/uscia-agent/app/evidence/collector.py`
  - Implements `collect_evidence(context: InvestigationContext) -> EvidencePayload`
  - Calls all 12 tool wrappers in parallel using `asyncio.gather(return_exceptions=True)`
  - NEVER uses sequential fallback — all 12 calls are issued simultaneously
  - Each result is wrapped as an `EvidenceNode` with `system_name`, `status` (`AVAILABLE` or `MISSING_DATA`), `raw_payload`, and `manual_guidance`
  - After collection: count available vs unavailable; if available < 3, set `insufficient_coverage_warning = True`
  - Returns `EvidencePayload` with `nodes: list[EvidenceNode]`, `available_count`, `unavailable_count`, `insufficient_coverage_warning`

- [ ] Create `assets/uscia-agent/app/evidence/models.py` — dataclasses for:
  - `InvestigationContext`: `material`, `plant`, `planning_version`, `date_from`, `date_to`, `incident_type`, `continuity_keys: dict`
  - `EvidenceNode`: `node_id`, `system_name`, `status`, `raw_payload`, `manual_guidance`
  - `EvidencePayload`: `nodes`, `available_count`, `unavailable_count`, `insufficient_coverage_warning`
  - `EvidenceGraph`: `incident_id`, `nodes`, `links`, `broken_boundaries`
  - `EvidenceLink`: `link_id`, `from_node_id`, `to_node_id`, `continuity_key`, `continuity_val`, `broken_boundary`
  - `Classification`: `root_cause`, `confidence`, `confirmed_findings`, `probable_findings`, `missing_findings`, `remediation_actions`
  - `RemediationAction`: `action_id`, `action_type`, `action_params: dict`, `requires_approval: bool`, `rank`

---

## Evidence Graph Engine (M3)

- [ ] Create `assets/uscia-agent/app/evidence/graph_builder.py`
  - Implements `build_evidence_graph(payload: EvidencePayload, context: InvestigationContext) -> EvidenceGraph`
  - Correlation strategy — attempt in order:
    1. `MATERIAL_PLANT` — present in all S/4HANA nodes; always linked
    2. `EXTERNID` — extract from IBP supply data and planned order EXTERNID field; link IBP ↔ S/4HANA ↔ CPI
    3. `ORDID` — planned order number; link S/4HANA ↔ PP/DS nodes
    4. `GUID` — if present in any node payload
    5. `MSG_ID` — integration message ID; link CPI ↔ bgRFC nodes
    6. `QUEUE_REF` — bgRFC queue reference
    7. `TIMESTAMP_PROXIMITY` — fallback: link nodes within 5-minute window (use only if no other key matches)
  - After linking: identify broken boundaries — any expected link where source node is `AVAILABLE` but target node is `MISSING_DATA` or has no matching continuity key value; mark `broken_boundary = True` on the link
  - Persist graph to HANA Cloud asynchronously using `hana_client.execute()`

---

## Deterministic Root Cause Classifier (M4)

- [ ] Create `assets/uscia-agent/app/classification/rules.yaml` — externalised rule set:
  ```yaml
  rules:
    - id: RC001
      name: RTI_CPI_MESSAGE_FAILURE
      conditions:
        - system: IBP_SUPPLY
          status: AVAILABLE
          has_externid: true
        - system: SAP_CPI
          status: MISSING_DATA
        - system: S4HANA_PLANNED_ORDER
          status: AVAILABLE
          planned_orders_count: 0
      evidence_tag: PROBABLE
      confidence: MEDIUM
      description: "IBP supply objects with EXTERNID exist but no corresponding planned orders in S/4HANA; CPI evidence unavailable. RTI/CPI message failure is probable."

    - id: RC002
      name: BGRFC_QUEUE_BLOCKAGE
      conditions:
        - system: S4HANA_BGRFC_QUEUE
          status: MISSING_DATA
        - system: IBP_SUPPLY
          status: AVAILABLE
          has_externid: true
        - system: S4HANA_PLANNED_ORDER
          status: AVAILABLE
          planned_orders_count: 0
      evidence_tag: PROBABLE
      confidence: MEDIUM
      description: "IBP supply objects exist; bgRFC queue evidence unavailable; no planned orders found in S/4HANA. bgRFC queue blockage is probable — check SM58."

    - id: RC003
      name: MASTER_DATA_CONFIG_ERROR
      conditions:
        - system: S4HANA_MATERIAL_PLANNING
          status: AVAILABLE
          mrp_type_is_blank: true
        - system: S4HANA_PLANNED_ORDER
          status: AVAILABLE
          planned_orders_count: 0
      evidence_tag: CONFIRMED
      confidence: HIGH
      description: "Material planning data retrieved; MRP type is blank or not set. No planned orders generated — MRP type configuration error confirmed."

    - id: RC004
      name: PPDS_SCHEDULING_FAILURE
      conditions:
        - system: S4HANA_PLANNED_ORDER
          status: AVAILABLE
          planned_orders_count_gt: 0
        - system: S4HANA_PPDS_STOCK
          status: AVAILABLE
          stock_entries_count: 0
        - system: S4HANA_PPDS_CONSTRAINTS
          status: AVAILABLE
      evidence_tag: CONFIRMED
      confidence: HIGH
      description: "Planned orders exist in S/4HANA but no PP/DS stock level entries found. PP/DS scheduling failure confirmed — check RRP3 and capacity/constraint configuration."

    - id: RC005
      name: CIF_TRANSFER_FAILURE
      conditions:
        - system: S4HANA_PLANNED_ORDER
          status: AVAILABLE
          planned_orders_count_gt: 0
        - system: S4HANA_PPDS_STOCK
          status: AVAILABLE
          stock_entries_count: 0
        - system: S4HANA_APPLICATION_LOGS
          status: MISSING_DATA
      evidence_tag: PROBABLE
      confidence: MEDIUM
      description: "Planned orders exist in MD04 but no PP/DS entries found; application logs unavailable. CIF transfer failure is probable — check SLG1 for APOCIF errors."

    - id: RC006
      name: ATP_SCOPE_MISMATCH
      conditions:
        - system: S4HANA_ATP
          status: AVAILABLE
          confirmed_quantity: 0
        - system: S4HANA_PLANNED_ORDER
          status: AVAILABLE
          planned_orders_count_gt: 0
      evidence_tag: CONFIRMED
      confidence: HIGH
      description: "Planned orders exist but ATP confirmation is zero. ATP scope mismatch confirmed — check CO09 for ATP check rule and scope assignment."

    - id: RC007
      name: IBP_PLANNING_GAP
      conditions:
        - system: IBP_SUPPLY
          status: AVAILABLE
          supply_orders_count: 0
        - system: S4HANA_PIR
          status: AVAILABLE
          pir_count_gt: 0
        - system: S4HANA_PLANNED_ORDER
          status: AVAILABLE
          planned_orders_count: 0
      evidence_tag: CONFIRMED
      confidence: HIGH
      description: "PIR exists in S/4HANA but IBP supply plan is empty. IBP planning gap confirmed — no supply output generated for this material-location. Verify IBP planning job completion and horizon settings."

    - id: RC008
      name: OTHER
      conditions:
        - insufficient_evidence: true
      evidence_tag: MISSING_DATA
      confidence: LOW
      description: "Insufficient evidence to classify root cause. Fewer than 3 systems returned data. Manual investigation required across all system layers."
  ```

- [ ] Create `assets/uscia-agent/app/classification/classifier.py`
  - Implements `classify(graph: EvidenceGraph, payload: EvidencePayload) -> Classification`
  - Loads rules from `rules.yaml` at startup (not hardcoded)
  - Evaluates each rule's conditions against the evidence payload deterministically (no LLM involvement)
  - Selects the first matching rule as primary root cause; if no rule matches, applies RC008
  - Tags each finding: `[CONFIRMED]` if evidence retrieved from live API; `[PROBABLE]` if inferred from partial evidence; `[MISSING DATA]` if no evidence
  - Zero API results for a system → `MISSING DATA`, never "no issue found"
  - Returns `Classification` with `root_cause`, `confidence`, confirmed/probable/missing counts, and ranked `RemediationAction` list

- [ ] Create `assets/uscia-agent/app/classification/remediation_ranker.py`
  - Implements `rank_remediation_actions(classification: Classification) -> list[RemediationAction]`
  - Queries `EffectivenessScore` from HANA Cloud for matching `(root_cause, action_type)` pairs
  - Sorts actions by `resolution_rate` descending; defaults to alphabetical by `action_type` if no history
  - All actions: `requires_approval = True` (hardcoded, never overridable in current build)
  - Returns list of `RemediationAction` with `action_type`, `action_params`, `requires_approval`, `rank`

---

## LLM Narration Layer

- [ ] Create `assets/uscia-agent/app/llm/narrator.py`
  - Implements `narrate_findings(classification: Classification, graph: EvidenceGraph, context: InvestigationContext) -> NarrationResult`
  - LLM: GPT-4o via SAP AI Core Generative AI Hub via `ChatLiteLLM`; model name from `LLM_MODEL_NAME` env var (default: `gpt-4o`); falls back to any available model if GPT-4o unavailable
  - System prompt instructs LLM to:
    - Narrate ONLY the evidence provided in the structured input — never generate findings from general SAP knowledge
    - Use `[CONFIRMED]`, `[PROBABLE]`, `[MISSING DATA]` tags exactly as provided by the classifier
    - Never remove, change, or reinterpret evidence tags
    - Produce Consultant View text (technical, with SAP transaction references) and Planner View text (plain English, business impact first)
    - Set `top` / page-size to maximum 100 on any tool call
  - Input to LLM: structured JSON of classification results and evidence nodes (not raw API responses)
  - Returns `NarrationResult` with `consultant_sections: dict[str, str]` and `planner_sections: dict[str, str]`

---

## Report Generator (M5)

- [ ] Create `assets/uscia-agent/app/report/generator.py`
  - Implements `generate_report(narration: NarrationResult, classification: Classification, graph: EvidenceGraph, context: InvestigationContext, incident_id: str) -> ForensicReport`
  - Enforces exactly 14 mandatory sections — if any section is blank, insert `[MISSING DATA: section could not be generated — manual review required]`
  - Section list (must all be present and non-empty):
    1. Executive Summary
    2. Issue Classification
    3. Affected System Boundary
    4. Evidence Timeline
    5. Evidence Graph Summary
    6. Confirmed Findings
    7. Probable Root Causes
    8. Missing Data Gaps
    9. Recommended Actions (with machine-readable `action_type`, `action_params`, `requires_approval` per action)
    10. SAP Objects to Check
    11. Logs and Transactions to Review
    12. Business Impact
    13. Escalation Path
    14. Preventive Recommendation
  - Two render modes: `consultant_view` (technical, SAP transaction codes, API evidence citations) and `planner_view` (plain English, business impact lead, no jargon)
  - Appends recurring pattern section if L4 pattern detection flag is set
  - Appends systemic issue section if L4 systemic flag is set
  - Returns `ForensicReport` with both view strings and `persisted_incident_id`

- [ ] Validate that `ForensicReport.consultant_view` and `ForensicReport.planner_view` both contain all 14 section headers

---

## Learning Engine — Async Post-Investigation Steps

- [ ] Create `assets/uscia-agent/app/learning/persistence.py` (L1)
  - Implements `persist_incident(incident: IncidentRecord, graph: EvidenceGraph, classification: Classification, report: ForensicReport, actions: list[RemediationAction]) -> str`
  - Writes to HANA Cloud: `IncidentRecord`, `EvidenceNode` (all nodes), `EvidenceLink` (all links), `FailureClassification`, `RemediationRecord` (all actions)
  - Runs as `asyncio.create_task()` — never blocks M5 report delivery
  - Returns `incident_id` (UUID)
  - Log on success: `L1.achieved: incident persisted — incident_id={id}, nodes={n}, actions={a}`
  - Log on failure: `L1.missed: incident persistence failed — incident_id={id}, error={error}`

- [ ] Create `assets/uscia-agent/app/learning/outcome_tracker.py` (L2)
  - Implements `record_outcome(incident_id: str, action_id: str, outcome: str) -> None`
  - Validates `outcome` ∈ `{Resolved, Partially Resolved, Not Resolved, Made Worse}`
  - Updates `RemediationRecord.outcome` and `RemediationRecord.outcome_at` in HANA Cloud
  - Log on success: `L2.achieved: outcome recorded — incident_id={id}, action_type={a}, outcome={o}`
  - Log on failure: `L2.missed: outcome recording failed — incident_id={id}, error={error}`

- [ ] Create `assets/uscia-agent/app/learning/effectiveness.py` (L3)
  - Implements `update_effectiveness(root_cause: str, action_type: str, outcome: str) -> None`
  - Upserts `EffectivenessScore` in HANA Cloud: increments `total_attempts`; if outcome is `Resolved`, increments `total_resolved`; recalculates `resolution_rate = total_resolved / total_attempts`
  - Triggered after every L2 outcome recording
  - Log on success: `L3.achieved: effectiveness updated — category={c}, action={a}, resolution_rate={r}`
  - Log on failure: `L3.missed: effectiveness update failed — category={c}, action={a}, error={error}`

- [ ] Create `assets/uscia-agent/app/learning/pattern_detector.py` (L4)
  - Implements `detect_patterns(material: str, plant: str, root_cause: str, incident_id: str) -> PatternResult`
  - Queries `IncidentRecord` in HANA Cloud: `SELECT COUNT(*) WHERE material=? AND plant=? AND root_cause=? AND created_at > NOW() - 90 days`
  - Returns `PatternResult` with `occurrence_count`, `pattern_flagged` (True if ≥3), `systemic` (True if ≥5)
  - Runs as `asyncio.create_task()` after M5 — does not block report delivery
  - Log on success: `L4.achieved: pattern detection complete — material={m}, plant={p}, occurrences={n}, pattern_flagged={f}, systemic={s}`
  - Log on failure: `L4.missed: pattern detection failed — material={m}, plant={p}, error={error}`

- [ ] Create `assets/uscia-agent/app/learning/predictive_scanner.py` (L5)
  - Implements `scan_for_pre_failure_signatures(material_plant_pairs: list[tuple[str, str]]) -> list[PredictiveAlert]`
  - Signature patterns to detect:
    - bgRFC queue depth trending upward (proxy: ≥2 BGRFC_QUEUE_BLOCKAGE incidents in last 30 days for same plant)
    - IBP job duration increasing (proxy: ≥2 IBP_PLANNING_GAP incidents in last 30 days for same material-plant)
    - CPI message lag increasing (proxy: ≥2 RTI_CPI_MESSAGE_FAILURE incidents in last 30 days for same plant)
    - Master data change preceding failure (proxy: MASTER_DATA_CONFIG_ERROR followed within 24h by any other failure type for same material)
  - Scans up to 500 material-plant combinations; must complete within 10 minutes total
  - Returns list of `PredictiveAlert` with `signature_type`, `historical_incident_ids`, `affected_material`, `affected_plant`, `recommended_preventive_action`
  - Log on success: `L5.achieved: predictive scan complete — combinations_scanned={n}, alerts_generated={a}, duration_seconds={d}`
  - Log on failure: `L5.missed: predictive scan failed — combinations_scanned={n}, error={error}`

---

## Agent Core Orchestration (M1–M5 + L1–L5)

- [ ] Implement `_run_agent(query: str, context_id: str) -> str` in `app/agent.py` — plain async helper (not a generator) that orchestrates the full M1→M5 flow plus async L1/L4 tasks:

  ```python
  async def _run_agent(self, query: str, context_id: str) -> str:
      # M1 — Context capture
      context = await self._extract_investigation_context(query)
      # M2 — Parallel evidence collection
      payload = await collect_evidence(context)
      # M3 — Build evidence graph (async persist)
      graph = build_evidence_graph(payload, context)
      # M4 — Classify root cause
      classification = classify(graph, payload)
      ranked_actions = rank_remediation_actions(classification)
      # LLM narration
      narration = await narrate_findings(classification, graph, context)
      # L4 pattern detection (non-blocking)
      incident_id = str(uuid.uuid4())
      asyncio.create_task(detect_patterns(context.material, context.plant, classification.root_cause, incident_id))
      # M5 — Generate report
      report = generate_report(narration, classification, graph, context, incident_id)
      # L1 incident persistence (non-blocking — must not delay M5)
      asyncio.create_task(persist_incident(incident_id, graph, classification, report, ranked_actions))
      return report.consultant_view  # or planner_view based on user preference
  ```

- [ ] Implement `_extract_investigation_context(query: str) -> InvestigationContext` — uses LLM to extract structured `InvestigationContext` from free-form text; asks one clarifying question at a time via A2A turn if any required field is missing (material, plant, at least one continuity key, incident_type); accepts structured JSON input without clarifying questions
- [ ] Implement `stream()` as a thin generator that calls `_run_agent()` and yields the result — all business logic in `_run_agent()`, never wrapped in `with tracer.start_as_current_span(...)` inside `stream()`
- [ ] Implement `invoke()` for direct A2A calls (non-streaming programmatic access)

---

## Business Step Instrumentation

- [ ] Verify `auto_instrument()` is called at top of `main.py` before any AI framework imports
- [ ] Instrument M1–M5 with OTel spans and structured log statements in `_run_agent()`:
  - `uscia.m1_context_capture` → `M1.achieved: investigation context captured — material={m}, plant={p}, version={v}, date_range={d}, incident_type={i}, continuity_keys={k}`
  - `uscia.m2_evidence_collection` → `M2.achieved: evidence collected — systems_queried={n}, available={a}, unavailable={u}, evidence_nodes={e}`
  - `uscia.m3_evidence_graph` → `M3.achieved: evidence graph built — nodes={n}, links={l}, broken_boundaries={b}, persisted_to_hana=true`
  - `uscia.m4_root_cause` → `M4.achieved: root cause classified — category={c}, confidence={HIGH|MEDIUM|LOW}, confirmed={n}, probable={n}, missing={n}`
  - `uscia.m5_report` → `M5.achieved: forensic report delivered — sections=14, duration_seconds={d}, root_cause={c}, persisted_incident_id={id}`
- [ ] Instrument L1–L5 with OTel spans and structured log statements in the respective learning module functions (use decorator form `@tracer.start_as_current_span` on each learning step function)
- [ ] Use context manager form (`with tracer.start_as_current_span(...)`) only inside non-generator async methods — never inside `stream()`

---

## SAP Joule A2A Registration

- [ ] Verify `/.well-known/agent.json` exposes A2A-compliant agent card with:
  - `name`: `"USCIA - Unified Supply Chain Intelligence Agent"`
  - `description`: describes the 10 supported incident types and 5-minute investigation SLA
  - `capabilities.streaming`: `true`
  - `skills` array with at least one skill entry: `"id": "investigate_planning_failure"`, `"name": "Investigate Supply Chain Planning Failure"`, `"description": "Autonomous end-to-end investigation of supply chain planning failures across IBP, CPI/RTI, bgRFC, S/4HANA MRP, PP/DS, and aATP. Returns 14-section forensic report in Consultant and Planner views."`
- [ ] Document in `assets/uscia-agent/JOULE_REGISTRATION.md`:
  - A2A endpoint URL pattern: `https://<cf-app-route>/`
  - Agent card URL: `https://<cf-app-route>/.well-known/agent.json`
  - Steps to register as Joule-callable agent in Joule Studio: point Joule to the A2A endpoint; Joule discovers skills from agent card
  - Direct A2A API access: `POST /` with `{"message": {"role": "user", "content": "..."}}` for programmatic/testing use

---

## Outcome Recording Endpoint

- [ ] Add A2A skill: `"id": "record_remediation_outcome"` to agent card
- [ ] Implement handler in `_run_agent()` — detects outcome recording intent from query
  - Parses `incident_id`, `action_id`, `outcome` from query (structured JSON or natural language)
  - Calls `record_outcome()` (L2) then `update_effectiveness()` (L3) sequentially
  - Returns confirmation message with updated effectiveness score

---

## Testing

- [ ] `conftest.py` only sets `IBD_TESTING=true` — this causes the agent to run with mock MCP tool results during tests
- [ ] Mock HANA Cloud client in all tests — use `unittest.mock.patch` on `hana_client.execute` and `hana_client.fetchall`
- [ ] Mock `ChatLiteLLM` in all tests — return canned narration responses; never make real AI Core calls

### Unit tests — one per tool wrapper

- [ ] `tests/test_s4_planned_order.py` — mock MCP returning planned orders; assert structure; mock returning error; assert MISSING_DATA stub
- [ ] `tests/test_s4_material_planning.py` — mock returning material data; mock returning error; assert MISSING_DATA stub
- [ ] `tests/test_s4_pir.py` — mock returning PIR list; mock returning error; assert MISSING_DATA stub
- [ ] `tests/test_s4_ppds_stock.py` — mock returning stock levels; mock returning error; assert MISSING_DATA stub
- [ ] `tests/test_s4_ppds_constraints.py` — mock returning constraints; mock returning error; assert MISSING_DATA stub
- [ ] `tests/test_s4_atp.py` — mock returning ATP result; mock returning error; assert MISSING_DATA stub
- [ ] `tests/test_s4_app_logs.py` — assert always returns MISSING_DATA with correct transaction reference (SLG1)
- [ ] `tests/test_s4_bgrfc.py` — assert always returns MISSING_DATA with correct transaction reference (SM58) and SXMB_MONI guidance
- [ ] `tests/test_ibp_supply.py` — mock OAuth token fetch; mock supply data response; mock token refresh on 401; mock HTTP error; assert MISSING_DATA stub
- [ ] `tests/test_cpi_messages.py` — assert always returns MISSING_DATA with correct SXMB_MONI guidance
- [ ] `tests/test_pipo_messages.py` — assert always returns MISSING_DATA
- [ ] `tests/test_cloud_alm.py` — assert always returns MISSING_DATA

### Unit tests — evidence collection and graph

- [ ] `tests/test_evidence_collector.py` — mock all 12 tools; assert `asyncio.gather` called (no sequential fallback); assert correct available/unavailable counts; assert `insufficient_coverage_warning` when < 3 available
- [ ] `tests/test_graph_builder.py` — construct mock EvidencePayload; assert correct continuity key correlation for EXTERNID, ORDID, MATERIAL_PLANT; assert broken boundary flagged when source AVAILABLE and target MISSING_DATA; assert timestamp proximity fallback (<5 min)

### Unit tests — classification and remediation

- [ ] `tests/test_classifier.py` — one test per rule in `rules.yaml` (RC001–RC008); test each condition combination; assert correct root cause category; assert correct evidence tag; assert zero API results → MISSING_DATA not "no issue found"
- [ ] `tests/test_remediation_ranker.py` — mock HANA effectiveness scores; assert actions ranked by resolution_rate; assert `requires_approval = True` on all actions; test with empty effectiveness history (alphabetical fallback)

### Unit tests — report generator

- [ ] `tests/test_report_generator.py` — mock narration and classification; assert all 14 section headers present in both consultant and planner views; assert machine-readable action fields present; assert blank section replaced with MISSING_DATA placeholder; assert RECURRING PATTERN section added when L4 flag set; assert systemic section added when L4 systemic flag set

### Unit tests — learning engine

- [ ] `tests/test_persistence.py` — mock HANA client; assert all tables written (IncidentRecord, EvidenceNode, EvidenceLink, FailureClassification, RemediationRecord); assert L1 runs as `asyncio.create_task` (non-blocking)
- [ ] `tests/test_outcome_tracker.py` — mock HANA client; assert valid outcomes accepted; assert invalid outcomes raise ValueError; assert HANA update called
- [ ] `tests/test_effectiveness.py` — mock HANA client; test resolution rate calculation; test upsert logic; assert `total_resolved / total_attempts` correct
- [ ] `tests/test_pattern_detector.py` — mock HANA fetchall returning 0, 2, 3, 5 occurrences; assert correct `pattern_flagged` and `systemic` flags
- [ ] `tests/test_predictive_scanner.py` — mock HANA incident history; assert all 4 signature types detected correctly; assert scan completes in < 10s for 500 pairs (mock data)

### Integration test

- [ ] `tests/test_integration.py` — mock all 12 MCP tools; mock LLM; mock HANA client; call `agent.invoke()` with structured JSON context for incident type 1 (planned order missing in MD04); assert: M1→M5 milestones logged; all 14 report sections present in response; `persisted_incident_id` in response; L1 `asyncio.create_task` scheduled; OTel spans emitted for all M1–M5 steps

### Run tests

- [ ] Run `pytest` from `assets/uscia-agent/` (no args) — if coverage < 70%, add tests until threshold met
- [ ] Verify `assets/uscia-agent/app/agent.py` has exactly 3 decorated functions: run `grep -c "^@agent_model\|^@agent_config\|^@prompt_section" assets/uscia-agent/app/agent.py` — must return 3
- [ ] Run `pytest` again from `assets/uscia-agent/` (no args) to generate final `test_report.json`
- [ ] Verify `test_report.json` exists in `assets/uscia-agent/`

---

## Validation Checklist

```bash
# Instrumentation — all M milestones present
grep -r "M[1-5]\.achieved" assets/uscia-agent/app/

# Learning engine — all L milestones present
grep -r "L[1-5]\.achieved" assets/uscia-agent/app/

# Decorators — exactly 3
grep -c "^@agent_model\|^@agent_config\|^@prompt_section" assets/uscia-agent/app/agent.py

# Read-only enforcement — no write/create/update/delete in tool wrappers
grep -r "\.post\|\.put\|\.patch\|\.delete\|INSERT INTO\|UPDATE \|DELETE FROM" assets/uscia-agent/app/tools/

# Test report
ls assets/uscia-agent/test_report.json

# Agent card
curl -s http://localhost:8000/.well-known/agent.json | python3 -m json.tool

# MISSING_DATA stubs — CPI, bgRFC, Cloud ALM, PI/PO all return MISSING_DATA
grep -r "MISSING_DATA" assets/uscia-agent/app/tools/cpi_messages.py
grep -r "MISSING_DATA" assets/uscia-agent/app/tools/s4_bgrfc.py
grep -r "SXMB_MONI" assets/uscia-agent/app/tools/cpi_messages.py
grep -r "SM58" assets/uscia-agent/app/tools/s4_bgrfc.py
```
