# USCIA API Catalogue — SAP OData / REST APIs

Complete reference of all SAP APIs available for integration into the USCIA evidence tools.
Each entry shows: **API Name**, **ORD ID** (the stable identifier to reference in MCP generation), **Type**, and **available spec formats**.

> **How to use**: Pass the `ordId` to `ibd-mcp-server__sap_knowledge_graph_api_discovery` or
> `generate_mcp_translation` to produce MCP tool wrappers from the EDMX/OpenAPI specs.

---

## 1. S/4HANA — Planning & MRP

| API Name | ORD ID | Type | Specs |
|---|---|---|---|
| Planned Order (Cloud) | `sap.s4:apiResource:PLANNEDORDER_0001:v1` | OData | EDMX + OpenAPI |
| Planned Order (OP) | `sap.s4:apiResource:OP_PLANNEDORDER_0001:v1` | OData | EDMX + OpenAPI |
| Planned Order (OP v2) | `sap.s4:apiResource:OP_API_PLANNED_ORDERS_SRV_0001:v1` | OData | EDMX + OpenAPI |
| Planned Order (API) | `sap.s4:apiResource:API_PLANNED_ORDERS:v1` | OData | EDMX + OpenAPI |
| Material Planning Data — Read (Cloud) | `sap.s4:apiResource:API_MRP_MATERIALS_SRV_01:v1` | OData | EDMX + OpenAPI |
| Material Planning Data — Read (OP) | `sap.s4:apiResource:OP_API_MRP_MATERIALS_SRV_01_0001:v1` | OData | EDMX + OpenAPI |
| Planned Independent Requirements (Cloud) | `sap.s4:apiResource:API_PLND_INDEP_RQMT_SRV:v1` | OData | EDMX + OpenAPI |
| Planned Independent Requirement (OP) | `sap.s4:apiResource:OP_API_PLND_INDEP_RQMT_SRV_0001:v1` | OData | EDMX + OpenAPI |
| Supply Assignment | `sap.s4:apiResource:OP_API_ARUN_SUPPLY_ASSIGNMENT_SRV_0001:v1` | OData | EDMX + OpenAPI |

**USCIA tools that benefit**: `s4_planned_order.py`, `s4_pir.py`, `s4_material_planning.py`

---

## 2. S/4HANA — PP/DS (Production Planning & Detailed Scheduling)

| API Name | ORD ID | Type | Specs |
|---|---|---|---|
| PPDS Product Time Dependent Stock Level | `sap.s4:apiResource:OP_PPDSPRODTDSTLV_0001:v1` | OData | EDMX + OpenAPI |
| Time Dependent Stock Levels (Cloud) | `sap.s4:apiResource:PRODTIMEDPDNTSTCK_0001:v1` | OData | EDMX + OpenAPI |
| Time Dependent Stock Levels (OP) | `sap.s4:apiResource:OP_PRODTIMEDPDNTSTCK_0001:v1` | OData | EDMX + OpenAPI |
| Flexible Constraint for PPDS | `sap.s4:apiResource:OP_APIFLEXIBLECONSTRAINTS_0001:v1` | OData | EDMX + OpenAPI |
| Flexible Constraint (pMRP) (Cloud) | `sap.s4:apiResource:PMRPFLEXIBLECONSTRAINT_0001:v1` | OData | EDMX + OpenAPI |
| Flexible Constraint (pMRP) (OP) | `sap.s4:apiResource:OP_API_PMRPFLEXIBLECONSTRAINT_0001:v1` | OData | EDMX + OpenAPI |
| Constraint Net (Variant Config) | `sap.s4:apiResource:OP_VARCONFIGNCONSTRAINTNET_0001:v1` | OData | EDMX + OpenAPI |
| Production Routing (v1) | `sap.s4:apiResource:OP_API_PRODUCTION_ROUTING_0001:v1` | OData | EDMX + OpenAPI |
| Production Routing (v3) | `sap.s4:apiResource:OP_API_PRODUCTION_ROUTING_0003:v3` | OData | EDMX + OpenAPI |
| Production Version | `sap.s4:apiResource:OP_PRODUCTIONVERSION_0001:v1` | OData | EDMX + OpenAPI |
| Production Supply Area (Cloud) | `sap.s4:apiResource:API_PRODUCTIONSUPPLYAREA_SRV:v1` | OData | EDMX + OpenAPI |
| Production Supply Area (OP) | `sap.s4:apiResource:OP_API_PRODUCTIONSUPPLYAREA_SRV_0001:v1` | OData | EDMX + OpenAPI |
| Order and Delivery Schedules | *(no ORD ID — use download URL)* | OData | EDMX + OpenAPI |
| Scheduling | *(no ORD ID — use download URL)* | OData | EDMX + OpenAPI |

**USCIA tools that benefit**: `s4_ppds_stock.py`, `s4_ppds_constraints.py`, `s4_ppds_config.py`

---

## 3. S/4HANA — Stock & ATP

| API Name | ORD ID | Type | Specs |
|---|---|---|---|
| Material Stock — Read (Cloud) | `sap.s4:apiResource:API_MATERIAL_STOCK_SRV:v1` | OData | EDMX + OpenAPI |
| Material Stock — Read (OP) | `sap.s4:apiResource:OP_API_MATERIAL_STOCK_SRV:v1` | OData | EDMX + OpenAPI |
| Warehouse Available Stock — Read A2X (Cloud) | `sap.s4:apiResource:WAREHOUSEAVAILABLESTOCK_0001:v1` | OData | EDMX + OpenAPI |
| Warehouse Available Stock — Read A2X (OP) | `sap.s4:apiResource:OP_WAREHOUSEAVAILABLESTOCK_0001:v1` | OData | EDMX + OpenAPI |
| Advanced ATP Check | `sap.s4:apiResource:CE_APIAVAILTOPROMISECHECK_0001:v1` | OData | EDMX + OpenAPI |
| ATP Snapshots | *(no ORD ID — use download URL)* | REST | OpenAPI only |
| Advanced Backorder Processing Run (Cloud) | `sap.s4:apiResource:CE_ABOPRUN_0001:v1` | OData | EDMX + OpenAPI |
| Advanced Backorder Processing Run (OP) | `sap.s4:apiResource:OP_ABOPRUN_0001:v1` | OData | EDMX + OpenAPI |

**USCIA tools that benefit**: `s4_ppds_stock.py`, `s4_atp.py`

---

## 4. S/4HANA — Monitoring, Logs & Queue

| API Name | ORD ID | Type | Specs |
|---|---|---|---|
| Application Logs | *(no ORD ID — use download URL)* | OData | EDMX + OpenAPI |
| Business Events Queue — Read (Cloud) | `sap.s4:apiResource:C_BEHQUEUEDATA_CDS:v1` | OData | EDMX + OpenAPI |
| Business Events Queue — Read (OP) | `sap.s4:apiResource:OP_C_BEHQUEUEDATA_CDS_0001:v1` | OData | EDMX + OpenAPI |
| Business Events Subscription | `sap.s4:apiResource:OP_CA_BEH_SUBSCRIPTION_SRV:v1` | OData | EDMX + OpenAPI |
| External Scheduler Integration | `sap.s4:apiResource:BC_EXT_APPJOB_MANAGEMENT:v2` | OData | EDMX + OpenAPI |
| Read Access Log Integration | `sap.s4:apiResource:CE_SRAL_API_RAW_LOG_0001:v1` | OData | EDMX + OpenAPI |
| Security Audit Log for SIEM | `sap.s4:apiResource:CE_RSAU_LOG_API_0001:v1` | OData | EDMX + OpenAPI |
| Consolidation Task Log — Read (Cloud) | `sap.s4:apiResource:CE_CONSOLIDATIONTASKLOG_0001:v1` | OData | EDMX + OpenAPI |
| Consolidation Task Log — Read (OP) | `sap.s4:apiResource:OP_CONSOLIDATIONTASKLOG_0001:v1` | OData | EDMX + OpenAPI |

**USCIA tools that benefit**: `s4_app_logs.py`, `s4_bgrfc.py`

---

## 5. SAP IBP (Integrated Business Planning)

| API Name | ORD ID | Type | Specs |
|---|---|---|---|
| IBP Scenario Metadata Management | *(no ORD ID — use download URL)* | OData | EDMX + OpenAPI |
| Detailed Pegging Data Extraction | *(no ORD ID — use download URL)* | OData | EDMX + OpenAPI |
| Integrate Key Figure Data with External Systems | *(no ORD ID — use download URL)* | OData | EDMX + OpenAPI |
| Import Planning Calendars | *(no ORD ID — use download URL)* | OData | EDMX + OpenAPI |
| Extract Planning Calendars | *(no ORD ID — use download URL)* | OData | EDMX + OpenAPI |
| Delivery Documents Integration | *(no ORD ID — use download URL)* | OData | EDMX + OpenAPI |
| External Forecasting | *(no ORD ID — use download URL)* | OData | EDMX + OpenAPI |
| External Stock Data Integration | *(no ORD ID — use download URL)* | OData | EDMX + OpenAPI |
| Extract Change History Data | *(no ORD ID — use download URL)* | OData | EDMX + OpenAPI |
| Batch Data Integration | *(no ORD ID — use download URL)* | OData | EDMX + OpenAPI |
| Snapshot Management for Stock and Order Data | *(no ORD ID — use download URL)* | OData | EDMX + OpenAPI |
| Forecast Data Extraction | *(no ORD ID — use download URL)* | OData | EDMX + OpenAPI |
| Extract and Manage Process Management Data | *(no ORD ID — use download URL)* | OData | EDMX + OpenAPI |
| Monitor System Tasks | *(no ORD ID — use download URL)* | OData | EDMX + OpenAPI |
| Integrate Key Figure and Master Data with SAP Analytics Cloud | *(no ORD ID — use download URL)* | OData | EDMX + OpenAPI |
| Integrating Master Data | *(no ORD ID — use download URL)* | OData | EDMX + OpenAPI |
| Realignment Project Integration | *(no ORD ID — use download URL)* | OData | EDMX + OpenAPI |
| Resource Consumption | *(no ORD ID — use download URL)* | OData | EDMX + OpenAPI |
| Telemetry OData Service | *(no ORD ID — use download URL)* | OData | EDMX + OpenAPI |
| Application Logs (IBP) | *(no ORD ID — use download URL)* | OData | EDMX + OpenAPI |

**USCIA tools that benefit**: `ibp_supply.py` — key APIs for Phase 2 IBP live integration are:
- **Detailed Pegging Data Extraction** → supply/demand pegging visibility
- **Monitor System Tasks** → IBP planning job status  
- **IBP Scenario Metadata Management** → planning version/scenario context
- **Extract Change History Data** → change audit trail

---

## 6. SAP Cloud Integration (CPI / RTI)

| API Name | ORD ID | Type | Specs |
|---|---|---|---|
| Message Processing Logs | *(no ORD ID — use download URL)* | OData | EDMX + OpenAPI |
| Log Files | *(no ORD ID — use download URL)* | OData | EDMX + OpenAPI |
| Message Stores | *(no ORD ID — use download URL)* | OData | EDMX + OpenAPI |
| Integration Content | *(no ORD ID — use download URL)* | OData | EDMX + OpenAPI |
| Partner Directory | *(no ORD ID — use download URL)* | OData | EDMX + OpenAPI |
| Security Content | *(no ORD ID — use download URL)* | OData | EDMX + OpenAPI |
| B2B Scenarios | *(no ORD ID — use download URL)* | OData | EDMX + OpenAPI |

**USCIA tools that benefit**: `cpi_messages.py` — **Message Processing Logs** is the primary API
(entity `MessageProcessingLogs`, filter on `Status eq 'FAILED'`).

---

## Priority MCP Generation Order for USCIA

Ordered by diagnostic impact:

| Priority | API | USCIA Tool | Why |
|---|---|---|---|
| 🔴 **P1** | Material Planning Data — Read | `s4_material_planning.py` | Core MRP stock/requirements view |
| 🔴 **P1** | Planned Order | `s4_planned_order.py` | Planned order existence & dates |
| 🔴 **P1** | Planned Independent Requirements | `s4_pir.py` | Demand signal source |
| 🔴 **P1** | PPDS Product Time Dependent Stock Level | `s4_ppds_stock.py` | PP/DS stock horizon |
| 🔴 **P1** | Flexible Constraint for PPDS | `s4_ppds_constraints.py` | Bottleneck constraints |
| 🔴 **P1** | Message Processing Logs (CPI) | `cpi_messages.py` | Integration failure detection |
| 🟡 **P2** | Advanced ATP Check | `s4_atp.py` | Available-to-promise check |
| 🟡 **P2** | Application Logs | `s4_app_logs.py` | S4 error log diagnostic |
| 🟡 **P2** | Business Events Queue — Read | `s4_bgrfc.py` | bgRFC / event queue stalls |
| 🟡 **P2** | Detailed Pegging Data Extraction (IBP) | `ibp_supply.py` | IBP pegging transparency |
| 🟡 **P2** | Monitor System Tasks (IBP) | `ibp_supply.py` | IBP job run status |
| 🟢 **P3** | IBP Scenario Metadata Management | `ibp_supply.py` | Scenario/version context |
| 🟢 **P3** | Extract Change History Data (IBP) | `ibp_supply.py` | Change audit |
| 🟢 **P3** | Production Routing | future tool | Routing completeness check |

---

## Existing MCP Servers (Registry Check)

`ibd-mcp-server__get_mcp` returned internal errors for all checked ORD IDs at time of catalogue
generation — the MCP Registry lookup service was temporarily unavailable. Re-run the check with:
```
ibd-mcp-server__get_mcp(ordId="sap.s4:apiResource:API_MRP_MATERIALS_SRV_01:v1")
```
once the registry recovers. If a pre-built MCP server exists, use it directly — no generation needed.

---

## How to Generate an MCP Tool from a Spec

1. **For APIs with an ORD ID** — use `generate_mcp_translation`:
   ```
   generate_mcp_translation(
     filePath="api-specs/material-planning.edmx",
     apiType="edmx",
     apiOrdId="sap.s4:apiResource:API_MRP_MATERIALS_SRV_01:v1"
   )
   ```

2. **For IBP/CPI APIs without an ORD ID** — download the OpenAPI JSON spec via the pre-signed URL
   above (valid for 1 hour from catalogue generation), save it to `api-specs/`, then run
   `generate_mcp_translation` with `apiType="openapi-v3"` and a descriptive pseudo-ordId.

3. **Check for existing MCP server** — before generating, call:
   ```
   ibd-mcp-server__get_mcp(ordId="sap.s4:apiResource:API_MRP_MATERIALS_SRV_01:v1")
   ```
   SAP may already have a published MCP server for that API — saves generation effort.
