# Migration summary

_For full detail, read `state.json`._

- Agent: `assets/uscia-agent`
- Last code run: 2026-06-12-121950
- Runtime mode: dual-mode
- Systems: s4hana_pc (S4HANA), ibp (IBP), cpi (CPI — stub), cloud_alm (CLOUD_ALM — stub)
- AI Core destination: aicore
- LLM model: gpt-4o
- Client strategy: per-system
- Deployment: runbook ready — see `assets/uscia-agent/DEPLOY.md`; must run CF commands from local machine (sandbox DNS blocks [REDACTED])
- Tests: 108/108 passing (2026-06-12)
- Deploy phase: RUNBOOK READY
