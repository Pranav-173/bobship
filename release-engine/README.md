# Release Engine

The **Release Engine** is the deterministic Python component of the BobShip release-engineering workflow. It receives normalized findings collected by IBM Bob's subagents, calculates release readiness, and generates a Markdown report that is written to `reports/`.

> **IBM Bob is the orchestrator.** The Release Engine is a library component — it never drives the workflow on its own. Bob calls it as part of the BobShip release workflow defined in `.bob/skills/release-engineer/SKILL.md`.

---

## Architecture Role

```
IBM Bob (orchestrator)
        │
        ├── subagents: Test · Security · API · Deployment · Documentation
        │       └── produce raw findings (list of dicts)
        │
        ├── MCP tools (deterministic checks)
        │
        └── Release Engine  ◄── this component
                ├── normalize()      normalize raw findings → Finding[]
                ├── score()          Finding[] → ReleaseScore
                ├── generate()       ReleaseScore + Finding[] → Markdown report
                └── reports/         output directory
```

The engine does **not** replace Bob. Bob feeds it findings; the engine returns a score and report.

---

## Scoring Rules

Defined exactly by `.bob/skills/release-engineer/SKILL.md`:

| Score | Readiness State |
|-------|----------------|
| 90–100 | ✅ READY |
| 75–89 | ⚠️ READY WITH WARNINGS |
| 50–74 | 🚫 NOT READY |
| 0–49 | 🔴 BLOCKED |

**Formula:** `score = max(0, 100 − (blockers × 25) − (warnings × 5))`

- `INFO` findings do not affect the score.
- Score is clamped to [0, 100].

---

## Installation & Setup

Requires **Python 3.8+**. No third-party packages are needed — the engine uses only the Python standard library.

```bash
cd release-engine

# Create and activate virtual environment
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# No pip install needed — stdlib only
```

---

## Public API

Import the package from `release-engine/src/`:

```python
import sys
sys.path.insert(0, "release-engine")
import src as engine

# 1. Normalize raw findings from subagents / MCP tools
findings = engine.normalize(raw_findings_list)

# 2. Score
result = engine.score(findings)
# result.score        → int (0–100)
# result.readiness    → ReadinessState enum
# result.blocker_count, .warning_count, .info_count

# 3. Generate Markdown report (writes to reports/ by default)
markdown = engine.generate(result, findings, repository="my-repo")
```

### Key symbols

| Symbol | Module | Description |
|--------|--------|-------------|
| `normalize(raw_list)` | `src` | Normalize a list of raw finding dicts |
| `normalize_finding(raw)` | `src` | Normalize a single raw finding dict |
| `score(findings)` | `src` | Compute `ReleaseScore` from `Finding[]` |
| `generate(score, findings, ...)` | `src` | Build and write Markdown report |
| `Finding` | `src.models` | Normalized finding dataclass |
| `ReleaseScore` | `src.models` | Score + readiness result |
| `ReleaseReport` | `src.models` | Full report model |
| `Severity` | `src.models` | `BLOCKER / WARNING / INFO` |
| `ReadinessState` | `src.models` | `READY / READY WITH WARNINGS / NOT READY / BLOCKED` |

---

## Input Format

Raw findings are plain Python dicts (or JSON objects). Any of these keys are accepted:

| Key | Type | Required | Notes |
|-----|------|----------|-------|
| `source` | str | recommended | `test`, `security`, `api`, `deployment`, `documentation` |
| `category` | str | optional | Sub-category (e.g. `hardcoded-secret`) |
| `severity` | str | recommended | See severity aliases below |
| `title` | str | one of title/message | Short description |
| `message` | str | one of title/message | Detailed explanation |
| `file_path` / `file` / `path` | str | optional | Repository-relative path |
| `line` / `line_number` | int | optional | 1-based line number |
| `remediation` / `recommendation` | str | optional | Fix guidance |

### Severity aliases

| Canonical | Accepted aliases |
|-----------|-----------------|
| `BLOCKER` | `blocker`, `critical`, `error`, `fatal`, `high` |
| `WARNING` | `warning`, `warn`, `medium`, `moderate`, `low` |
| `INFO` | `info`, `information`, `informational`, `note`, `notice`, `suggestion` |

Unknown severities default to `WARNING` (never silently dropped).

---

## Output Format

- **Return value of `generate()`:** Markdown string
- **Written file:** `reports/release-report-YYYYMMDD-HHMMSS.md`

The report contains:
1. Header (status badge, score, timestamp)
2. Summary table
3. Blockers (must-fix)
4. Warnings (should-fix)
5. Informational findings (if any)
6. Recommended actions

---

## Running Tests

```bash
cd release-engine
python -m pytest tests/ -v
# or without pytest:
python -m unittest discover tests/
```

---

## CLI (Local Development Helper)

A CLI entry point is provided for local testing. **It does not replace Bob orchestration.**

```bash
cd release-engine

# From a JSON file
python __main__.py findings.json --repository my-repo

# From stdin
echo '[{"source":"security","category":"hardcoded-secret","severity":"critical",
        "title":"API key in source","file_path":"config.py","line":42,
        "remediation":"Move to environment variable"}]' |
python __main__.py --repository my-repo

# Print only, do not write to disk
python __main__.py findings.json --no-write

# Also emit structured JSON
python __main__.py findings.json --repository my-repo --json
```

Options:
```
FINDINGS_FILE       JSON file of raw findings ("-" or omit = stdin)
--repository        Repository name in the report header
--output-dir DIR    Override the output directory (default: reports/)
--no-write          Print to stdout only; do not write to disk
--json              Also emit ReleaseReport JSON to stdout
```

---

## Example Invocation

```python
raw = [
    {
        "source": "security",
        "category": "hardcoded-secret",
        "severity": "critical",
        "title": "Hardcoded API key",
        "file_path": "app/config.py",
        "line": 12,
        "remediation": "Move to SECRET_KEY environment variable"
    },
    {
        "source": "test",
        "category": "coverage",
        "severity": "warning",
        "title": "Test coverage is 62% (target: 80%)"
    }
]

import sys; sys.path.insert(0, "release-engine")
import src as engine

findings = engine.normalize(raw)
result   = engine.score(findings)
# score = 70, readiness = NOT READY

report_md = engine.generate(result, findings, repository="my-app")
print(report_md)
# → writes reports/release-report-<timestamp>.md
```

---

## How IBM Bob Invokes This Component

Bob does **not** shell out to the CLI in production. Instead:

1. Bob loads the `release-engineer` skill.
2. Bob delegates analysis to specialized subagents (Test, Security, API, Deployment, Documentation).
3. Each subagent returns raw findings as structured dicts.
4. Bob calls the Release Engine as a Python library (currently via the MCP server layer — see `mcp-server/` for that integration, which is in progress).
5. The engine returns a `ReleaseScore` and a Markdown report.
6. Bob presents blockers to the user and asks for approval before applying fixes.
7. After fixes, Bob re-runs checks, calls the engine again, and generates the final report artifact in `reports/`.

> The MCP server integration is not yet implemented. When complete, the MCP tool will import this package and expose `normalize`, `score`, and `generate` as deterministic, stateless tool calls.

---

## Dependency Policy

The Release Engine uses **Python standard library only** (`dataclasses`, `enum`, `json`, `logging`, `datetime`, `os`, `argparse`, `unittest`).

No third-party packages are required. `requirements.txt` is intentionally empty until a genuine need arises.
