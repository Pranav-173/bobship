#!/usr/bin/env node
/**
 * Self-contained CLI smoke test — no external repo required.
 * Runs every tool against fixtures/sample-repo (which has known, intentional
 * issues: a hardcoded secret, an undocumented env var, no Docker healthcheck,
 * an undocumented /orders route, and an unpinned dependency) and asserts each
 * tool actually flags what it's supposed to. Exits 1 on any failure so it can
 * be wired into CI.
 *
 * Run with: npm run smoke-test
 */
import path from "node:path";
import { fileURLToPath } from "node:url";
import { projectStructure } from "../tools/project-structure.js";
import { gitDiff } from "../tools/git-tools.js";
import { scanSecrets } from "../tools/security-tools.js";
import { inspectEnvironment } from "../tools/env-tools.js";
import { inspectDocker } from "../tools/docker-tools.js";
import { validateOpenapi } from "../tools/api-tools.js";
import { runTests, getTestCoverage } from "../tools/test-tools.js";
import { dependencyCheck } from "../tools/dependency-tools.js";
import { releaseSnapshot } from "../tools/release-tools.js";
import type { ToolResult } from "../lib/findings.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
// dist/scripts -> ../../fixtures/sample-repo
const FIXTURE_ROOT = path.resolve(__dirname, "../../fixtures/sample-repo");

let failures = 0;

function check(label: string, condition: boolean, detail: string) {
  if (condition) {
    console.log(`  \x1b[32mPASS\x1b[0m ${label}`);
  } else {
    console.log(`  \x1b[31mFAIL\x1b[0m ${label} — ${detail}`);
    failures++;
  }
}

function hasMessageMatching(result: ToolResult, re: RegExp): boolean {
  return result.findings.some((f) => re.test(f.message));
}

async function run() {
  console.log(`Smoke-testing bobship-mcp-server tools against fixtures/sample-repo\n(${FIXTURE_ROOT})\n`);

  console.log("project_structure:");
  const structure = await projectStructure(FIXTURE_ROOT, FIXTURE_ROOT, {});
  check("runs without throwing and finds files", (structure as any).fileCount > 0, "expected fileCount > 0");

  console.log("git_diff:");
  const git = await gitDiff(FIXTURE_ROOT, FIXTURE_ROOT, {});
  check("runs without throwing", git.findings.length > 0, "expected at least one finding");

  console.log("scan_secrets:");
  const secrets = await scanSecrets(FIXTURE_ROOT, FIXTURE_ROOT, {});
  check("detects the planted Stripe key", hasMessageMatching(secrets, /Stripe live secret key/i), "expected a Stripe key finding");

  console.log("inspect_environment:");
  const env = await inspectEnvironment(FIXTURE_ROOT, FIXTURE_ROOT, {});
  check("flags DEBUG as undocumented", hasMessageMatching(env, /DEBUG.*missing from/i), "expected DEBUG undocumented finding");

  console.log("inspect_docker:");
  const docker = await inspectDocker(FIXTURE_ROOT, FIXTURE_ROOT, {});
  check("flags missing HEALTHCHECK", hasMessageMatching(docker, /no HEALTHCHECK/i), "expected missing-healthcheck finding");

  console.log("validate_openapi:");
  const openapi = await validateOpenapi(FIXTURE_ROOT, FIXTURE_ROOT, {});
  check("flags /orders as unimplemented", hasMessageMatching(openapi, /\/orders.*no matching route/i), "expected /orders mismatch finding");

  console.log("dependency_check:");
  const deps = await dependencyCheck(FIXTURE_ROOT, FIXTURE_ROOT, {});
  check("flags unpinned fastapi dependency", hasMessageMatching(deps, /fastapi.*no version pin/i), "expected unpinned dependency finding");

  console.log("run_tests:");
  const tests = await runTests(FIXTURE_ROOT, FIXTURE_ROOT, { timeoutMs: 30_000 });
  check("runs pytest and reports a result", tests.findings.length > 0, "expected a test result finding");

  console.log("get_test_coverage:");
  const coverage = await getTestCoverage(FIXTURE_ROOT, FIXTURE_ROOT, {});
  check("runs without throwing", coverage.findings.length > 0, "expected at least one finding");

  console.log("release_snapshot:");
  const snapshot = await releaseSnapshot(FIXTURE_ROOT, FIXTURE_ROOT, { skipTests: true });
  check("aggregates findings from multiple tools", snapshot.toolsRun.length >= 5, `expected >=5 tools run, got ${snapshot.toolsRun.length}`);
  check("surfaces at least one critical finding", snapshot.findings.some((f) => f.severity === "critical"), "expected the planted secret to surface as critical");

  console.log(`\n${failures === 0 ? "\x1b[32mAll checks passed.\x1b[0m" : `\x1b[31m${failures} check(s) failed.\x1b[0m`}`);
  process.exit(failures === 0 ? 0 : 1);
}

run().catch((err) => {
  console.error("Smoke test crashed:", err);
  process.exit(1);
});
