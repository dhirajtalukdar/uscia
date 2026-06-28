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

> CPI Message Processing Logs are now live (not a stub). Set `CPI_BASE_URL`, `CPI_TOKEN_URL`,
> `CPI_CLIENT_ID`, `CPI_CLIENT_KEY` OR create a BTP destination named `SAP_CPI` — the tool
> degrades gracefully if neither is configured.
> IBP Monitor System Tasks are also live. The same IBP destination/env vars used for supply
> data also drive job monitoring (same `IBP` BTP destination).
> Cloud ALM is still a stub — activate by setting `CLOUD_ALM_BASE_URL` via `cf set-env`.

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

## Step 8 — Optional: enable additional backends after initial push

```bash
# ── CPI Message Processing Logs (live — fills biggest integration gap) ────────
# Option A: BTP destination (recommended)
#   Create destination 'SAP_CPI' in BTP cockpit with OAuth2ClientCredentials
#   pointing to your CPI tenant. No env vars needed.
#
# Option B: raw env vars
cf set-env uscia-agent CPI_BASE_URL     "<cpi-tenant-url>"
cf set-env uscia-agent CPI_TOKEN_URL    "<cpi-token-url>/oauth/token"
cf set-env uscia-agent CPI_CLIENT_ID    "<cpi-client-id>"
cf set-env uscia-agent CPI_CLIENT_KEY   "<cpi-client-secret>"
# Optional — override default iFlow name if your tenant uses a different name:
# cf set-env uscia-agent CPI_RTI_IFLOW  "IBP_RTI_TO_S4HANA"

# ── IBP Monitor System Tasks (live — driven by same IBP destination/env vars) ─
# No extra config needed if IBP is already configured above.
# Override BTP destination name if needed (default: 'IBP'):
# cf set-env uscia-agent IBP_DESTINATION_NAME "IBP"

# ── Cloud ALM (still Phase 2 stub) ────────────────────────────────────────────
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
| `CPI_BASE_URL` | cf set-env | Optional — activates CPI Message Processing Logs (or use `SAP_CPI` BTP destination) |
| `CPI_TOKEN_URL` | cf set-env | Optional — CPI OAuth token URL |
| `CPI_CLIENT_ID` | cf set-env | Optional — CPI OAuth client ID |
| `CPI_CLIENT_KEY` | cf set-env | Optional — CPI OAuth client secret |
| `CPI_RTI_IFLOW` | cf set-env | Optional — override default iFlow name (default: `IBP_RTI_TO_S4HANA`) |
| `CLOUD_ALM_BASE_URL` | cf set-env | Optional — activates Cloud ALM stub |
| `LOG_LEVEL` | manifest.yml | = `INFO` |
| `JOULE_RUNTIME` | NOT SET in CF | Absence = CF mode |
