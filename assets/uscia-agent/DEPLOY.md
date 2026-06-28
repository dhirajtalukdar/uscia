# USCIA-Agent — Cloud Foundry Deploy Runbook

**Generated automatically by the migration agent.**
Run these commands from your local machine with CF CLI v8 installed.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| CF CLI v8 | `cf --version` → should be `8.x` |
| Access to BTP subaccount | cf-org + space with `destination` and `connectivity` service instances |
| Service instances created | `proj-vector-destination-service` (destination) + `proj-vector-connectivity-service` (connectivity) |
| BTP destinations configured | `S4HANA` (OnPremise / Cloud Connector), `aicore` (SAP AI Core) |
| IBP credentials at hand | `IBP_BASE_URL`, `IBP_TOKEN_URL`, `IBP_CLIENT_ID`, `IBP_CLIENT_SECRET` |

---

## Step 1 — Set CF API and log in

```bash
# Set API endpoint
cf api [REDACTED]

# Get your SSO passcode — open this URL in a browser:
#   [REDACTED]
# Then paste the one-time code below:
cf login --sso
```

> If your org/space is not auto-selected, run:
> ```bash
> cf target -o <YOUR_ORG> -s <YOUR_SPACE>
> ```

---

## Step 2 — Verify service instances exist

```bash
cf services | grep -E 'proj-vector-destination-service|proj-vector-connectivity-service'
```

Expected output (both lines must appear):
```
proj-vector-destination-service   destination    lite    ...
proj-vector-connectivity-service  connectivity   lite    ...
```

If missing, create them:
```bash
cf create-service destination   lite   proj-vector-destination-service
cf create-service connectivity  lite   proj-vector-connectivity-service
```

---

## Step 3 — Set IBP credentials (not in manifest — injected via env)

```bash
cf set-env uscia-agent IBP_BASE_URL      "<your-ibp-base-url>"
cf set-env uscia-agent IBP_TOKEN_URL     "<your-ibp-token-url>"
cf set-env uscia-agent IBP_CLIENT_ID     "<your-ibp-client-id>"
cf set-env uscia-agent IBP_CLIENT_SECRET "<your-ibp-client-secret>"
```

> CPI and Cloud ALM stub clients are activated by setting `CPI_BASE_URL` / `CLOUD_ALM_BASE_URL`
> via `cf set-env` after the initial push.

---

## Step 4 — Push the app

```bash
# Navigate to the agent directory
cd assets/uscia-agent

# Push (first time — downloads buildpack, installs dependencies)
cf push
```

This reads `manifest.yml` in the current directory. Expected output ends with:
```
state     since                  cpu    memory     disk
running   2025-...               0.x%   ...M/512M  ...
```

---

## Step 5 — Verify health endpoint

```bash
# Get the app route
cf app uscia-agent | grep routes

# Smoke test (replace <ROUTE> with the value from above)
curl -s https://<ROUTE>/.well-known/agent.json | python3 -m json.tool
```

Expected: a JSON agent card with `name: "uscia-agent"` and `version`.

---

## Step 6 — Verify BTP destinations are reachable

```bash
# S4HANA destination (OnPremise / Cloud Connector)
cf ssh uscia-agent -c "cd app && python3 -c \"
import asyncio, s4hana_client
async def t():
    c = s4hana_client.S4Client()
    dest = await c.destination()
    print('S4HANA dest URL:', dest.url)
asyncio.run(t())
\""

# AI Core destination
cf ssh uscia-agent -c "cd app && python3 -c \"
import asyncio, aicore
async def t():
    llm = await aicore.init_llm_from_destination()
    print('LLM type:', type(llm).__name__)
asyncio.run(t())
\""
```

---

## Step 7 — Optional: tail logs

```bash
cf logs uscia-agent --recent
cf logs uscia-agent   # live stream
```

---

## Step 8 — Optional: enable stub backends after initial push

```bash
# CPI integration
cf set-env uscia-agent CPI_BASE_URL     "<cpi-url>"
cf set-env uscia-agent CPI_TOKEN_URL    "<cpi-token-url>"
cf set-env uscia-agent CPI_CLIENT_ID    "<cpi-id>"
cf set-env uscia-agent CPI_CLIENT_KEY   "<cpi-key>"

# Cloud ALM integration
cf set-env uscia-agent CLOUD_ALM_BASE_URL    "<calm-url>"
cf set-env uscia-agent CLOUD_ALM_TOKEN_URL   "<calm-token-url>"
cf set-env uscia-agent CLOUD_ALM_CLIENT_ID   "<calm-id>"
cf set-env uscia-agent CLOUD_ALM_CLIENT_KEY  "<calm-key>"

# Restart app to pick up new env vars
cf restart uscia-agent
```

---

## Rollback

```bash
# Scale down to 0 instances (keeps the app registered)
cf scale uscia-agent -i 0

# Full undeploy
cf delete uscia-agent -f
```

---

## Re-deploy after code changes

```bash
cd assets/uscia-agent
cf push          # hot redeploy — zero downtime if instances > 1
```

---

## Reference: app env vars (all sources)

| Variable | Source | Notes |
|---|---|---|
| `S4HANA_DESTINATION_NAME` | manifest.yml | = `S4HANA` |
| `DESTINATION_NAME` | manifest.yml | = `S4HANA` (compat alias) |
| `AICORE_DESTINATION_NAME` | manifest.yml | = `aicore` |
| `IBP_BASE_URL` | cf set-env | Required for IBP |
| `IBP_TOKEN_URL` | cf set-env | Required for IBP |
| `IBP_CLIENT_ID` | cf set-env | Required for IBP |
| `IBP_CLIENT_SECRET` | cf set-env | Required for IBP |
| `CPI_BASE_URL` | cf set-env | Optional — activates CPI stub |
| `CLOUD_ALM_BASE_URL` | cf set-env | Optional — activates Cloud ALM stub |
| `LOG_LEVEL` | manifest.yml | = `INFO` |
| `JOULE_RUNTIME` | NOT SET in CF | Absence = CF mode |
