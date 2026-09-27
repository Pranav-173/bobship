# AGENTS.md — Ask Mode

This file provides guidance to agents when working with code in this repository.

## Non-Obvious Documentation Context

- **`docs/` files are empty.** `ARCHITECTURE.md`, `BOB_WORKFLOW.md`, and `MCP_TOOLS.md` all exist but contain no content yet. Don't cite them as sources of truth.
- **`release-engine/requirements.txt` is empty.** Python dependencies are not yet declared — don't assume any libraries are available.
- **The skill is the authoritative spec.** `.bob/skills/release-engineer/SKILL.md` is the most complete implemented document in the repo and defines the actual workflow and scoring thresholds.
- **`sample-app/` is a demo with intentional bugs**, not a real application. Questions about its "correct" behavior should be framed around release-readiness analysis, not production correctness.
- **The dashboard is visualization only** — it has no business logic. Questions about workflow orchestration should always point back to IBM Bob and the release-engineer skill.
- **MCP server README is empty** — refer to `docs/MCP_TOOLS.md` (when populated) or the skill for tool contracts.
