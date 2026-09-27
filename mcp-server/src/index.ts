#!/usr/bin/env node
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

import { resolveTarget } from "./lib/fsutils.js";
import { projectStructure } from "./tools/project-structure.js";
import { gitDiff } from "./tools/git-tools.js";
import { scanSecrets } from "./tools/security-tools.js";
import { inspectEnvironment } from "./tools/env-tools.js";
import { inspectDocker } from "./tools/docker-tools.js";
import { validateOpenapi } from "./tools/api-tools.js";
import { runTests, getTestCoverage } from "./tools/test-tools.js";
import { dependencyCheck } from "./tools/dependency-tools.js";
import { releaseSnapshot } from "./tools/release-tools.js";

/**
 * The repo BobShip is analyzing. Bob's MCP config (.bob/mcp.json) should set
 * cwd to the target repository when launching this server. BOBSHIP_REPO_ROOT
 * is an optional override for local testing outside of Bob.
 */
const REPO_ROOT = process.env.BOBSHIP_REPO_ROOT ?? process.cwd();

function jsonResult(payload: unknown) {
  return {
    content: [{ type: "text" as const, text: JSON.stringify(payload, null, 2) }],
    structuredContent: payload as Record<string, unknown>,
  };
}

const server = new McpServer({
  name: "bobship-mcp-server",
  version: "1.0.0",
});

const pathParam = z
  .string()
  .optional()
  .describe("Path to the target project, relative to the repository root. Defaults to the repository root itself.");

// ---------------------------------------------------------------------------
// 1. project_structure
// ---------------------------------------------------------------------------
server.registerTool(
  "project_structure",
  {
    title: "Project Structure",
    description: `Returns the directory/file structure of the target project, skipping noise directories (node_modules, .git, dist, __pycache__, venv, etc.).

Args:
  - path (string, optional): subdirectory to inspect, relative to repo root.
  - maxDepth (number, optional, default 4): how many directory levels deep to walk.

Returns JSON: { tree: [...nested dirs/files...], fileCount: number, findings: [...] }

Use when: understanding an unfamiliar repository's layout before deeper checks.`,
    inputSchema: { path: pathParam, maxDepth: z.number().int().min(1).max(20).optional() },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  },
  async ({ path: p, maxDepth }) => {
    const target = resolveTarget(REPO_ROOT, p);
    return jsonResult(await projectStructure(REPO_ROOT, target, { maxDepth }));
  }
);

// ---------------------------------------------------------------------------
// 2. git_diff
// ---------------------------------------------------------------------------
server.registerTool(
  "git_diff",
  {
    title: "Git Diff Summary",
    description: `Returns the current git status, branch, last commit, and a diff --stat summary against a base ref.

Args:
  - path (string, optional): repo subdirectory.
  - against (string, optional, default "HEAD"): base ref to diff against.

Returns JSON: { branch, lastCommit, diffStat, findings: [one per changed file] }

Use when: understanding what changed since the last release/commit.`,
    inputSchema: { path: pathParam, against: z.string().optional() },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  },
  async ({ path: p, against }) => {
    const target = resolveTarget(REPO_ROOT, p);
    return jsonResult(await gitDiff(REPO_ROOT, target, { against }));
  }
);

// ---------------------------------------------------------------------------
// 3. scan_secrets
// ---------------------------------------------------------------------------
server.registerTool(
  "scan_secrets",
  {
    title: "Scan For Hardcoded Secrets",
    description: `Scans text files for obvious hardcoded credentials: AWS keys, private key headers, Stripe/GitHub/Slack tokens, JWTs, and generic secret/password/token assignments.

Args:
  - path (string, optional): subdirectory to scan.

Returns JSON: { findings: [{ status: "fail", severity, file, line, message }, ...] }
This is a heuristic regex-based scanner — flag lines still need a human/Bob to confirm before removal.

Use when: checking for exposed credentials before a release.`,
    inputSchema: { path: pathParam },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  },
  async ({ path: p }) => {
    const target = resolveTarget(REPO_ROOT, p);
    return jsonResult(await scanSecrets(REPO_ROOT, target, {}));
  }
);

// ---------------------------------------------------------------------------
// 4. inspect_environment
// ---------------------------------------------------------------------------
server.registerTool(
  "inspect_environment",
  {
    title: "Inspect Environment Variables",
    description: `Cross-references environment variables referenced in code (process.env.X, os.environ, os.getenv) against a .env.example file, flagging variables that are used but undocumented, or documented but unused.

Args:
  - path (string, optional): subdirectory to inspect.
  - envExampleFile (string, optional): explicit path to the example env file, relative to 'path'.

Returns JSON: { findings: [...] }

Use when: verifying required config is documented before deployment.`,
    inputSchema: { path: pathParam, envExampleFile: z.string().optional() },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  },
  async ({ path: p, envExampleFile }) => {
    const target = resolveTarget(REPO_ROOT, p);
    return jsonResult(await inspectEnvironment(REPO_ROOT, target, { envExampleFile }));
  }
);

// ---------------------------------------------------------------------------
// 5. inspect_docker
// ---------------------------------------------------------------------------
server.registerTool(
  "inspect_docker",
  {
    title: "Inspect Docker Configuration",
    description: `Checks Dockerfile(s) and docker-compose file for common production issues: missing HEALTHCHECK, running as root, unpinned/':latest' base images, missing restart policy.

Args:
  - path (string, optional): subdirectory to inspect.

Returns JSON: { findings: [...] }

Use when: verifying deployment configuration before shipping.`,
    inputSchema: { path: pathParam },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  },
  async ({ path: p }) => {
    const target = resolveTarget(REPO_ROOT, p);
    return jsonResult(await inspectDocker(REPO_ROOT, target, {}));
  }
);

// ---------------------------------------------------------------------------
// 6. validate_openapi
// ---------------------------------------------------------------------------
server.registerTool(
  "validate_openapi",
  {
    title: "Validate OpenAPI Contract",
    description: `Compares an OpenAPI/Swagger spec's paths against routes found in backend source (FastAPI/Flask/Express patterns), flagging documented-but-unimplemented and implemented-but-undocumented endpoints.

Args:
  - path (string, optional): repo subdirectory.
  - specFile (string, optional): explicit spec path (default: auto-detects openapi.yaml/json, swagger.yaml/json).
  - backendDir (string, optional): subdirectory to search for route definitions (default: whole 'path').

Returns JSON: { findings: [...] }
NOTE: this is a heuristic text/regex match, not a full schema-level contract validator.

Use when: checking frontend/backend/API-doc drift before a release.`,
    inputSchema: { path: pathParam, specFile: z.string().optional(), backendDir: z.string().optional() },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  },
  async ({ path: p, specFile, backendDir }) => {
    const target = resolveTarget(REPO_ROOT, p);
    return jsonResult(await validateOpenapi(REPO_ROOT, target, { specFile, backendDir }));
  }
);

// ---------------------------------------------------------------------------
// 7. run_tests
// ---------------------------------------------------------------------------
server.registerTool(
  "run_tests",
  {
    title: "Run Project Tests",
    description: `Auto-detects and runs the project's test suite (pytest, or 'npm test'), parsing the pass/fail summary.

Args:
  - path (string, optional): subdirectory to run tests in.
  - timeoutMs (number, optional, default 120000): kill the test run if it exceeds this.

Returns JSON: { findings: [{ status: "pass"|"fail", message: "<n> passed, <n> failed" }] }

Use when: verifying the test suite is green before/after a fix.`,
    inputSchema: { path: pathParam, timeoutMs: z.number().int().min(1000).max(600_000).optional() },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: false },
  },
  async ({ path: p, timeoutMs }) => {
    const target = resolveTarget(REPO_ROOT, p);
    return jsonResult(await runTests(REPO_ROOT, target, { timeoutMs }));
  }
);

// ---------------------------------------------------------------------------
// 8. get_test_coverage
// ---------------------------------------------------------------------------
server.registerTool(
  "get_test_coverage",
  {
    title: "Get Test Coverage",
    description: `Reads existing coverage reports (JS: coverage/coverage-summary.json; Python: coverage.xml) and reports line coverage percentage. Does NOT run tests itself — run_tests (or the project's own coverage command) must produce the report first.

Args:
  - path (string, optional): subdirectory to inspect.

Returns JSON: { findings: [{ message: "Line coverage: NN%" }] }

Use when: assessing whether critical paths are tested.`,
    inputSchema: { path: pathParam },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  },
  async ({ path: p }) => {
    const target = resolveTarget(REPO_ROOT, p);
    return jsonResult(await getTestCoverage(REPO_ROOT, target, {}));
  }
);

// ---------------------------------------------------------------------------
// 9. dependency_check
// ---------------------------------------------------------------------------
server.registerTool(
  "dependency_check",
  {
    title: "Dependency Check",
    description: `Inspects package.json/requirements.txt for missing lockfiles and unpinned ('*'/'latest'/no-version) dependencies. Optionally runs 'npm audit' for known vulnerabilities (requires network access).

Args:
  - path (string, optional): subdirectory to inspect.
  - runAudit (boolean, optional, default false): also run 'npm audit --json'.

Returns JSON: { findings: [...] }

Use when: checking dependency hygiene before a release.`,
    inputSchema: { path: pathParam, runAudit: z.boolean().optional() },
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true },
  },
  async ({ path: p, runAudit }) => {
    const target = resolveTarget(REPO_ROOT, p);
    return jsonResult(await dependencyCheck(REPO_ROOT, target, { runAudit }));
  }
);

// ---------------------------------------------------------------------------
// 10. release_snapshot
// ---------------------------------------------------------------------------
server.registerTool(
  "release_snapshot",
  {
    title: "Release Snapshot",
    description: `Runs every deterministic check (scan_secrets, inspect_docker, inspect_environment, validate_openapi, dependency_check, git_diff, and optionally run_tests) and merges all findings into one machine-readable snapshot.

Does NOT compute a readiness score — that belongs to the release-engine scoring component. This tool only aggregates raw findings so the caller doesn't need 6+ separate round trips.

Args:
  - path (string, optional): subdirectory to inspect.
  - skipTests (boolean, optional, default false): skip run_tests (useful for a fast snapshot).

Returns JSON: { toolsRun: [...], findings: [...], counts: {...}, summary }

Use when: Bob needs the full picture in one call, e.g. at the start of "prepare this project for release".`,
    inputSchema: { path: pathParam, skipTests: z.boolean().optional() },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: false },
  },
  async ({ path: p, skipTests }) => {
    const target = resolveTarget(REPO_ROOT, p);
    return jsonResult(await releaseSnapshot(REPO_ROOT, target, { skipTests }));
  }
);

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error(`bobship-mcp-server running (stdio), repo root: ${REPO_ROOT}`);
}

main().catch((err) => {
  console.error("Fatal error starting bobship-mcp-server:", err);
  process.exit(1);
});
