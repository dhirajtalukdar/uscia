# USCIA Dashboard — Cloud Foundry Deploy Runbook

Deploy the dashboard as a **separate** CF app alongside the already-deployed `uscia-agent`.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| CF CLI v8 | `cf --version` |
| Logged in to the same CF org/space as `uscia-agent` | `cf target` to verify |
| `uscia-agent` already running | `cf app uscia-agent` must show `running` |

---

## Step 1 — Build the React client locally (first deploy only)

The nodejs buildpack on CF will run `npm run build` automatically.
For a local smoke-test before pushing:

```bash
cd assets/uscia-dashboard
npm install
npm run build          # builds React into client/dist
node server.js         # verify at http://localhost:3000
```

---

## Step 2 — Push to Cloud Foundry

```bash
cd assets/uscia-dashboard
cf push
```

CF will:
1. Detect the nodejs buildpack
2. Run `npm install` + `npm run build` (which builds the React client)
3. Start `node server.js`
4. Assign route: `uscia-dashboard.<your-shared-domain>`

---

## Step 3 — Verify

```bash
# Get the route
cf app uscia-dashboard | grep routes

# Smoke-test health endpoint
curl -s https://<ROUTE>/health | python3 -m json.tool
# Expected: {"status":"ok","agent":"[REDACTED]