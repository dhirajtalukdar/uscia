# IBP API Paths — USCIA Agent (extracted from tools/ibp_supply.py)

## Source
Extracted from `assets/uscia-agent/app/tools/ibp_supply.py` — already using direct OData calls.

IBP uses its own OAuth2 client_credentials flow (IBP_TOKEN_URL, IBP_CLIENT_ID, IBP_CLIENT_SECRET).
The existing IBP client (`_ibp_auth.py` + `ibp_supply.py`) already works via direct HTTP —
it does NOT use BTP destination service. For CF deployment, IBP credentials will be injected
via environment variables (no BTP destination needed, unless the project wants to migrate to one).

---

## IBP Supply Planning
- **Service root**: `/sap/opu/odata/IBP/SUPPLY_PLANNING_SRV`
- **Entity set used**: `SupplyOrders`
- **Filter fields used**: `Material`, `Location`, `PlanningVersion`
- **$select**: (not set — returns all fields)
- **Mandatory params**: `$format=json`
- **Auth**: Bearer token via OAuth2 client_credentials from IBP_TOKEN_URL

---

## CF Environment Variables Required
- `IBP_BASE_URL` — e.g. `https://<tenant>.ibp.cloud.sap`
- `IBP_TOKEN_URL` — OAuth2 token endpoint
- `IBP_CLIENT_ID` — OAuth2 client ID
- `IBP_CLIENT_SECRET` — OAuth2 client secret
