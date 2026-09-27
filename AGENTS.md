# AGENTS.md

This file provides guidance to agents when working with code in this repository.

## Project

BobShip is an AI-powered release engineering workflow built around IBM Bob. IBM Bob is the **central orchestrator** — never bypass it with direct scripts or dashboards.

## Repository Structure

| Path | Purpose |
|------|---------|
| `.bob/` | IBM Bob config: skills (`skills/`), custom modes (`modes/`) |
| `mcp-server/src/tools/` | MCP tool implementations (deterministic, stateless) |
| `release-engine/src/` | Python: finding normalization, scoring, report generation |
| `sample-app/` | SmartPay demo app with intentional controlled release issues |
| `dashboard/src/components/` | Visualization only — no workflow logic here |
| `reports/` | Output directory for generated release reports (git-tracked via `.gitkeep`) |
| `docs/` | Architecture docs (`ARCHITECTURE.md`, `BOB_WORKFLOW.md`, `MCP_TOOLS.md`) |

## Stack

- **MCP server**: Node.js / TypeScript — fully implemented; `mcp-server/src/tools/` contains 9 tool modules; `mcp-server/package.json` has `build` / `start` / `smoke-test` scripts
- **Release engine**: Python (`release-engine/src/`) — fully implemented: `analyzer.py`, `scoring.py`, `models.py`, `report_generator.py`, `mcp_adapter.py`; 132 tests passing
- **Sample app**: Multi-component (`backend/`, `frontend/`, `tests/` subdirs are intentionally empty scaffolds — demo issues live in `mcp-server/fixtures/sample-repo/`)
- **Dashboard**: Self-contained HTML (`dashboard/release-dashboard.html`) — teammate-owned; `dashboard/src/components/` is an empty placeholder

## Commands

Build commands live in per-component directories, not the repo root.

- Python virtual env is expected at `release-engine/.venv/` or `release-engine/venv/`
- Env files follow `.env` / `.env.*` pattern (`.env.example` is tracked, others gitignored)

## Architecture Constraints

- **IBM Bob is the orchestrator** — MCP tools provide deterministic facts; subagents provide specialized reasoning; the dashboard is visualization only.
- **MCP tools must be stateless** — no side effects; Bob calls them for facts, not actions.
- **Release score thresholds** (from skill): 90–100 = READY, 75–89 = READY WITH WARNINGS, 50–74 = NOT READY, 0–49 = BLOCKED.
- **Never claim verification without actually running checks.**
- **Ask for approval before destructive or risky changes.**
- **Do not commit secrets** — `*.pem`, `*.key`, `credentials.json`, `.env.*` are all gitignored.

## BobShip Workflow (when asked to prepare a project for release)

1. Load the `release-engineer` skill (`.bob/skills/release-engineer/SKILL.md`).
2. Inspect repository structure.
3. Delegate independent analysis to specialized subagents (Test, Security, API, Deployment, Documentation).
4. Use MCP tools for deterministic checks.
5. Normalize findings, score release readiness.
6. Present blockers — get approval for risky fixes.
7. Apply safe fixes, re-run checks, verify.
8. Generate release artifacts in `reports/`.

## Subagent Responsibilities

| Agent | Scope |
|-------|-------|
| Test Agent | tests, coverage, regression readiness |
| Security Agent | secrets, unsafe config, security blockers |
| API Agent | API implementation, OpenAPI, request/response consistency |
| Deployment Agent | Docker, deployment config, environment requirements |
| Documentation Agent | README, setup instructions, config docs |
