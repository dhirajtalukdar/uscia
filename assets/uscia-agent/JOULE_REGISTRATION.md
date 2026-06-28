# Joule Studio Registration — USCIA Agent

## Overview
The Unified Supply Chain Intelligence Agent (USCIA) is deployed as an A2A-protocol agent on SAP BTP AI Core. It is callable from SAP Joule via the A2A endpoint registration.

## A2A Endpoint
After deployment, the agent exposes:

```
GET  https://<AGENT_PUBLIC_URL>/.well-known/agent.json
POST https://<AGENT_PUBLIC_URL>/
```

The agent card at `/.well-known/agent.json` contains:
- `name`: `uscia-agent`
- `skills`: `investigate_planning_failure` — main investigation skill
- `capabilities.streaming`: `true`

## Skills

### `investigate_planning_failure`
**Trigger phrase for Joule:**
> "Investigate planning failure for material \<MATERIAL\> plant \<PLANT\>"

**Required input:**
```json
{
  "material": "M-1234",
  "plant": "1000",
  "incident_type": "planned order missing in MD04",
  "date_from": "2024-01-01",
  "date_to": "2024-12-31",
  "planning_version": "000"
}
```

**Output:** 14-section forensic report in Consultant and Planner views.

### `record_remediation_outcome`
**Trigger phrase for Joule:**
> "Record outcome for investigation \<INCIDENT_ID\>"

**Required input:**
```json
{
  "incident_id": "<uuid>",
  "action_id": "<uuid>",
  "outcome": "Resolved | Partially Resolved | Not Resolved | Made Worse"
}
```

## Registration Steps

### Step 1: Obtain deployment URL
After running `cf push` or AI Core deployment, note the public URL. Set as:
```bash
cf set-env uscia-agent AGENT_PUBLIC_URL [REDACTED] Step 2: Verify agent card
```bash
curl https://<AGENT_PUBLIC_URL>/.well-known/agent.json
```
Expected response:
```json
{
  "name": "uscia-agent",
  "version": "1.0.0",
  "capabilities": {"streaming": true},
  "skills": [{"id": "uscia-agent", "name": "uscia-agent", ...}]
}
```

### Step 3: Register in Joule Studio
1. Navigate to Joule Studio > Agent Registry > Register External Agent
2. Provide the A2A endpoint URL: `https://<AGENT_PUBLIC_URL>/`
3. Paste the agent card JSON from Step 2
4. Assign the Joule skill phrases from above
5. Set auth: OAuth 2.0 with AI Core service credentials

### Step 4: Verify direct A2A call
```bash
curl -X POST https://<AGENT_PUBLIC_URL>/ \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tasks/send",
    "id": "1",
    "params": {
      "message": {
        "role": "user",
        "parts": [{"type": "text", "text": "{\"material\": \"M-1234\", \"plant\": \"1000\", \"incident_type\": \"planned order missing in MD04\", \"date_from\": \"2024-01-01\", \"date_to\": \"2024-12-31\", \"planning_version\": \"000\"}"}]
      }
    }
  }'
```

## Environment Variables Required at Deployment

| Variable | Description |
|----------|-------------|
| `LLM_MODEL_NAME` | GPT-4o model name via SAP AI Core Hub (default: `gpt-4o`) |
| `AGENT_PUBLIC_URL` | Public CF/AI Core route for the agent |
| `IBP_BASE_URL` | SAP IBP tenant URL (optional — MISSING_DATA fallback if absent) |
| `IBP_TOKEN_URL` | IBP OAuth token endpoint |
| `IBP_CLIENT_ID` | IBP OAuth client ID |
| `IBP_CLIENT_SECRET` | IBP OAuth client secret |
| `HANA_HOST` | HANA Cloud host for learning engine persistence |
| `HANA_PORT` | HANA Cloud port (default: 443) |
| `HANA_USER` | HANA Cloud username |
| `HANA_PASSWORD` | HANA Cloud password |
| `AICORE_AUTH_URL` | AI Core auth URL (auto-configured by `set_aicore_config()`) |
| `AICORE_CLIENT_ID` | AI Core client ID |
| `AICORE_CLIENT_SECRET` | AI Core client secret |
| `AICORE_RESOURCE_GROUP` | AI Core resource group |
| `AICORE_BASE_URL` | AI Core base URL |

## Capacity and SLA Notes
- Target: 100 investigations/day, 20 concurrent at peak
- Report delivery SLA: under 5 minutes per investigation
- All 12 evidence systems queried in parallel via `asyncio.gather`
- HANA persistence is non-blocking (`asyncio.create_task`) — does not delay report delivery

## S/4HANA API Integration
All 6 S/4HANA APIs are declared in `asset.yaml` under `requires` using their SAP ORD IDs. The Agent Gateway resolves these at runtime — no EDMX files or MCP translation files are needed. S/4HANA tools are live from first deployment.
