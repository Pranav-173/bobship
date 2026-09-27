# bobship-mcp-server

Deterministic release-engineering tools for IBM Bob, built for **BobShip**
(IBM Bob 2.0 Hackathon). This server does the "boring, reliable" checks —
git, secrets, Docker, OpenAPI, tests, dependencies — so Bob's reasoning is
grounded in real tool output instead of guesses.

This is **Member 2's** component (`mcp-server/`) from the execution plan.

## Tools

All tools return the same finding shape so downstream consumers (the
release-engine's scoring/report generator) can treat every tool's output
identically:

```json
{
  "status": "pass" | "warning" | "fail" | "info",
  "severity": "critical" | "high" | "medium" | "low" | "info",
  "category": "testing" | "security" | "api" | "deployment" | "documentation" | "dependencies" | "git" | "structure",
  "file": "optional/path.py",
  "line": 42,
  "message": "human-readable description"
}
```

Every tool call returns `{ findings: [...], counts: {...}, summary, tool, target }`.

| Tool | What it does | Read-only? |
|---|---|---|
| `project_structure` | Directory/file tree, skipping node_modules/.git/dist/venv/etc. | yes |
| `git_diff` | Branch, last commit, status, `diff --stat` vs a base ref. | yes |
| `scan_secrets` | Regex scan for hardcoded AWS/Stripe/GitHub/Slack keys, JWTs, generic `secret=`/`password=` assignments, private key headers. | yes |
| `inspect_environment` | Cross-references `process.env.X` / `os.environ` / `os.getenv` usage against `.env.example`. | yes |
| `inspect_docker` | Dockerfile/compose checks: HEALTHCHECK, non-root USER, pinned base image, restart policy. | yes |
| `validate_openapi` | Heuristic match of OpenAPI `paths` against FastAPI/Flask/Express route definitions found in code. | yes |
| `run_tests` | Auto-detects and runs `pytest` or `npm test`, parses the pass/fail summary. | **no** (executes tests) |
| `get_test_coverage` | Reads existing coverage reports (`coverage/coverage-summary.json`, `coverage.xml`) — does not run tests itself. | yes |
| `dependency_check` | Flags missing lockfiles and unpinned versions in `package.json`/`requirements.txt`. Optional `runAudit: true` shells out to `npm audit`. | yes (unless audit) |
| `release_snapshot` | Runs everything above (except `run_tests` if `skipTests: true`) and merges all findings into one payload. **Does not compute a score** — that's the release-engine's job. | no |

### Known limitations (by design, given the timeline)

- `scan_secrets` is regex-based — expect occasional false positives on
  clearly-placeholder values (it tries to flag these as `medium` instead of
  the pattern's usual severity, but isn't perfect).
- `validate_openapi` does a **text/regex route match**, not a schema-level
  contract diff. It catches "this endpoint exists in one place but not the
  other" — it does not check request/response body shapes.
- `dependency_check`'s `npm audit` mode needs network access and is off by
  default for that reason.

These are explicitly OK for the hackathon scope — see `docs` in the plan:
deterministic-but-imperfect tools are what Bob is supposed to reason over and
double check, not a replacement for Bob's judgment.

## Setup

```bash
cd mcp-server
npm install
npm run build
```

## Testing it yourself (no SmartPay needed yet)

A fixture repo with known, intentional issues ships in `fixtures/sample-repo/`
(a hardcoded Stripe key, an undocumented env var, a missing Docker
healthcheck, an undocumented `/orders` route, an unpinned dependency). Run:

```bash
npm run smoke-test
```

This builds, spins up each tool against the fixture, and asserts that every
expected issue is actually caught. If a teammate changes something and this
goes red, the server broke — fix it before it reaches Bob.

To point any tool at a **real** repo instead, from the CLI (bypassing Bob),
set `BOBSHIP_REPO_ROOT` and use the MCP Inspector:

```bash
BOBSHIP_REPO_ROOT=/path/to/sample-app npx @modelcontextprotocol/inspector node dist/index.js
```

That opens a local web UI where you can call any tool by hand and see raw
JSON output — the fastest way to sanity-check a tool without wiring up Bob
first.

## Connecting to IBM Bob

Add this to the repo's `.bob/mcp.json` (create it if Member 1 hasn't yet):

```json
{
  "mcpServers": {
    "bobship": {
      "command": "node",
      "args": ["mcp-server/dist/index.js"],
      "cwd": "${workspaceRoot}"
    }
  }
}
```

By default the server treats its own working directory as the repo root
(`BOBSHIP_REPO_ROOT` env var overrides this for local testing). Every tool
accepts an optional `path` argument, relative to that root, if Bob needs to
scope a check to a subdirectory (e.g. `sample-app/backend`).

After wiring this in, restart/reload Bob and confirm the tools appear —
Bob should be able to call e.g. `scan_secrets` and get back real JSON.

## Project structure

```
mcp-server/
├── src/
│   ├── index.ts          # Server entry point — registers all 10 tools
│   ├── lib/
│   │   ├── findings.ts   # Shared Finding type + builders (pass/warning/fail/info)
│   │   ├── exec.ts       # Timeout-guarded subprocess execution
│   │   └── fsutils.ts    # Directory walking, safe file reads, path resolution
│   ├── tools/            # One file per tool group
│   └── scripts/
│       └── smoke-test.ts # Self-test against fixtures/sample-repo
├── fixtures/sample-repo/ # Known-bad fixture used by the smoke test
└── dist/                 # Compiled output (git-ignored)
```

## Extending

To add a new tool: write the logic in `src/tools/`, returning a `ToolResult`
via `buildResult()` from `src/lib/findings.ts`, then register it in
`src/index.ts` with a Zod input schema and a description that states
exactly what it returns (Bob relies on the description to decide when to
call it — be explicit).
