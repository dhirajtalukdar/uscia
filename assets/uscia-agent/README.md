# USCIA - Unified Supply Chain Intelligence Agent

Autonomous supply chain planning failure diagnostic agent for SAP IBP, RTI/CPI, bgRFC, S/4HANA MRP, PP/DS, and aATP. Investigates 10 incident types, collects evidence from 12 systems in parallel, classifies root causes with evidence tags, and delivers a 14-section forensic report in Consultant and Planner views in under 5 minutes.

## Overview

Uses A2A Protocol, LangGraph, LiteLLM, and SAP Cloud SDK.

## Structure

- `app/main.py` - A2A server entry
- `app/agent_executor.py` - Request handling
- `app/agent.py` - Agent logic
