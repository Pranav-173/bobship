# AGENTS.md — Agent (Coding) Mode

This file provides guidance to agents when working with code in this repository.

## Non-Obvious Coding Rules

- **Most source files are empty stubs.** `mcp-server/src/tools/`, `release-engine/src/*.py`, `sample-app/backend/`, `sample-app/frontend/`, `sample-app/tests/`, and `dashboard/src/components/` all contain no implementation yet. Don't assume there's existing logic to integrate with.
- **Release scores live in the skill, not in code.** The scoring thresholds (READY / READY WITH WARNINGS / NOT READY / BLOCKED) are defined in `.bob/skills/release-engineer/SKILL.md` — there is no `scoring.py` implementation yet despite the file existing.
- **`reports/` is output-only.** The only tracked file is `.gitkeep`. Agents write generated reports there; do not put source files there.
- **`sample-app/` bugs are intentional.** It contains controlled release issues for demonstration. Do not "fix" them unless that is the explicit task.
- **MCP tools must be stateless and side-effect-free.** Bob calls them for deterministic facts. Any statefulness breaks the orchestration model.
- **Build commands must be run from their component directory**, not the repo root. No root-level `package.json` exists.
- **Python venv path**: `release-engine/.venv/` or `release-engine/venv/` (both gitignored). Always activate before running Python code.
- **`.env.example` is the only tracked env file.** All others (`.env`, `.env.*`) are gitignored. Never commit real values.
- **Custom modes** live in `.bob/modes/` as `.md` files (e.g., `release-engineer.md`). The file is currently empty — the mode definition goes inside it following IBM Bob's custom mode schema.
