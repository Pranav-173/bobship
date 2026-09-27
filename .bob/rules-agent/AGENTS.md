# AGENTS.md — Agent (Coding) Mode

This file provides guidance to agents when working with code in this repository.

## Non-Obvious Coding Rules

- **MCP server and Release Engine are fully implemented.** `mcp-server/src/tools/` contains 9 tool modules (TypeScript, 11/11 smoke tests passing). `release-engine/src/` contains `analyzer.py`, `scoring.py`, `models.py`, `report_generator.py`, `mcp_adapter.py` (132 Python tests passing). Do not treat these as stubs — read them before modifying.
- **`sample-app/backend/`, `sample-app/frontend/`, `sample-app/tests/`, and `dashboard/src/components/` are genuinely empty.** The controlled demo issues live in `mcp-server/fixtures/sample-repo/`, not in `sample-app/`.
- **Release scores are defined in the skill AND implemented in code.** The thresholds (READY / READY WITH WARNINGS / NOT READY / BLOCKED) are in `.bob/skills/release-engineer/SKILL.md`; `scoring.py` implements them exactly — do not modify either without updating both.
- **`reports/` is output-only.** The only tracked file is `.gitkeep`. Agents write generated reports there; do not put source files there.
- **`sample-app/` bugs are intentional.** It contains controlled release issues for demonstration. Do not "fix" them unless that is the explicit task.
- **MCP tools must be stateless and side-effect-free.** Bob calls them for deterministic facts. Any statefulness breaks the orchestration model.
- **Build commands must be run from their component directory**, not the repo root. No root-level `package.json` exists.
- **Python venv path**: `release-engine/.venv/` or `release-engine/venv/` (both gitignored). Always activate before running Python code.
- **`.env.example` is the only tracked env file.** All others (`.env`, `.env.*`) are gitignored. Never commit real values.
- **Custom modes** live in `.bob/modes/` as `.md` files (e.g., `release-engineer.md`). The file is currently empty — the mode definition goes inside it following IBM Bob's custom mode schema.
