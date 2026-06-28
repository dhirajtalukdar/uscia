# S/4HANA API Paths — USCIA Agent (extracted from existing tool code + SAP API Hub ORD IDs)

## Source
Extracted from `assets/uscia-agent/app/tools/*.py` (existing MCP tool call parameters)
and confirmed against SAP Business Accelerator Hub ORD IDs in `asset.yaml`.

All services are OData v2 (`/sap/opu/odata/sap/*` paths). CSRF required for writes (none used here — read-only).

---

## 1. Planned Order — PLANNEDORDER_0001
- **ORD ID**: `sap.s4:apiResource:PLANNEDORDER_0001:v1`
- **Service root**: `/sap/opu/odata/sap/API_PLANNED_ORDERS_SRV`
- **Entity set used**: `A_PlannedOrder`
- **Key fields**: `PlannedOrder` (string, 10 chars)
- **Filter fields used**: `Material`, `ProductionPlant`, `ScheduledBasicStartDate`, `ScheduledBasicEndDate`
- **$select fields**: `PlannedOrder, Material, ProductionPlant, MRPPlant, MRPArea, PlannedOrderType, PlannedOrderProfile, MaterialDescription, ProductionVersion, MRPController, PlannedTotalQty, PlannedScrapQty, ProductionUnit, ScheduledBasicStartDate, ScheduledBasicEndDate, ScheduledOpeningDate, PlannedOrderCreationDate, LastChangeDateTime, PlannedOrderStatus, OrderIsCreated`
- **Mandatory params**: `sap-client=910`, `$format=json`
- **Note**: Field `Material` maps to SAP material number; `ProductionPlant` = plant code.

---

## 2. Material Planning Data — API_MRP_MATERIALS_SRV_01
- **ORD ID**: `sap.s4:apiResource:API_MRP_MATERIALS_SRV_01:v1`
- **Service root**: `/sap/opu/odata/sap/API_MRP_MATERIALS_SRV_01`
- **Entity sets used**:
  - `A_MrpMaterial` (MRP data per material/plant)
- **Key fields**: `Material` (string), `MRPPlant` (string, 4 chars)
- **Filter fields used**: `Material`, `MRPPlant`
- **$select fields**: `Material, MRPPlant, MRPType, MRPTypeName, LotSizingCode, LotSizingProcedureName, ReorderThresholdQuantity, MaximumStockQuantity, MinimumLotSizeQuantity, MaximumLotSizeQuantity, FixedLotSizeQuantity, ProductionHorizon, PlanningTimeHorizon, MRPController, PurchasingGroup, SpecialProcurementType, IndependentRequirementsEdit, PlannedDeliveryDurationInDays`
- **Mandatory params**: `sap-client=910`, `$format=json`

---

## 3. Planned Independent Requirements — OP_API_PLND_INDEP_RQMT_SRV_0001
- **ORD ID**: `sap.s4:apiResource:OP_API_PLND_INDEP_RQMT_SRV_0001:v1`
- **Service root**: `/sap/opu/odata/sap/API_PLND_INDEP_RQMT_SRV`
- **Entity sets used**:
  - `A_PlndIndepRqmt`
- **Key fields**: `Material` (string), `MRPPlant` (string), `PlanningVersion` (string, 3 chars), `RequirementDate` (date), `RequirementsSegment` (string)
- **Filter fields used**: `Material`, `MRPPlant`, `PlanningVersion`, `RequirementDate`
- **$select fields**: `Material, MRPPlant, PlanningVersion, RequirementDate, PlannedIndepRqmtInBaseUnit, BaseUnit, PlannedIndepRqmtNumber, RequirementsSegment, PlndIndepRqmtIsFullyConsumed, Reservation`
- **Mandatory params**: `sap-client=910`, `$format=json`

---

## 4. PPDS Product Time-Dependent Stock Level — OP_PPDSPRODTDSTLV_0001
- **ORD ID**: `sap.s4:apiResource:OP_PPDSPRODTDSTLV_0001:v1`
- **Service root**: `/sap/opu/odata/sap/OP_PPDSPRODTDSTLV_0001`
- **Entity sets used**:
  - `A_PPDSProdTimeDependentStockLvl`
- **Key fields**: `Product` (string), `Location` (string, 4 chars), `TimeStamp` (datetime)
- **Filter fields used**: `Product`, `Location`, `TimeStamp`
- **$select fields**: `Product, Location, TimeStamp, TotalStockQtyInBaseUnit, ProjectedStockQtyInBaseUnit, SafetyStockQtyInBaseUnit, ReorderPointQtyInBaseUnit, BaseUnit, StockLevelCategory`
- **Mandatory params**: `sap-client=910`, `$format=json`

---

## 5. PPDS Flexible Constraints — OP_APIFLEXIBLECONSTRAINTS_0001
- **ORD ID**: `sap.s4:apiResource:OP_APIFLEXIBLECONSTRAINTS_0001:v1`
- **Service root**: `/sap/opu/odata/sap/OP_APIFLEXIBLECONSTRAINTS_0001`
- **Entity sets used**:
  - `A_FlexibleConstraint`
- **Key fields**: `ConstraintType` (string), `Plant` (string), `ConstraintID` (string)
- **Filter fields used**: `Material`, `Plant`
- **$select fields**: `ConstraintType, Plant, ConstraintID, Material, ValidFromDate, ValidToDate, ConstraintQuantity, ConstraintUnit, IsActive, ConstraintDescription`
- **Mandatory params**: `sap-client=910`, `$format=json`

---

## 6. Advanced ATP Check — CE_APIAVAILTOPROMISECHECK_0001
- **ORD ID**: `sap.s4:apiResource:CE_APIAVAILTOPROMISECHECK_0001:v1`
- **Service root**: `/sap/opu/odata/sap/API_AVAILABILITYCHECKING_SRV`
- **Entity sets used**:
  - `A_AvailabilityCheckingResultItem`
- **Key fields**: `CheckingRuleID` (string), `RequestedMaterial` (string), `RequestedPlant` (string)
- **Filter fields used**: `RequestedMaterial`, `RequestedPlant`, `RequestedDate`
- **$select fields**: `CheckingRuleID, RequestedMaterial, RequestedPlant, RequestedDate, RequestedQuantity, ConfirmedQuantity, AvailableQuantity, ConfirmedDate, ATPCategory, BackorderProcessingResult`
- **Mandatory params**: `sap-client=910`, `$format=json`
- **Note**: This is a POST-based check API; read results via GET on confirmation items. The existing tool only does a read-style check.
