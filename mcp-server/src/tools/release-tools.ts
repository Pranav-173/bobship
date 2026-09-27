import path from "node:path";
import { gitDiff } from "./git-tools.js";
import { scanSecrets } from "./security-tools.js";
import { inspectEnvironment } from "./env-tools.js";
import { inspectDocker } from "./docker-tools.js";
import { validateOpenapi } from "./api-tools.js";
import { dependencyCheck } from "./dependency-tools.js";
import { runTests } from "./test-tools.js";
import type { Finding, FindingStatus } from "../lib/findings.js";

export interface ReleaseSnapshotInput {
  path?: string;
  skipTests?: boolean; // tests can be slow; allow skipping for a quick snapshot
}

export interface ReleaseSnapshot {
  tool: "release_snapshot";
  target: string;
  generatedAt: string;
  findings: Finding[];
  counts: Record<FindingStatus, number>;
  toolsRun: string[];
  summary: string;
}

/**
 * Runs every deterministic check and merges the findings into one payload.
 * This is intentionally NOT a scoring engine — no readiness score is computed
 * here. Score calculation belongs to the release-engine (per the BobShip
 * plan, that's a separate component). This tool just gives it clean,
 * consistent input in one call instead of ten.
 */
export async function releaseSnapshot(root: string, targetDir: string, input: ReleaseSnapshotInput): Promise<ReleaseSnapshot> {
  const rel = path.relative(root, targetDir) || ".";
  const toolsRun: string[] = [];
  const allFindings: Finding[] = [];

  const run = async <T extends { findings: Finding[] }>(name: string, fn: () => Promise<T>) => {
    try {
      const result = await fn();
      toolsRun.push(name);
      allFindings.push(...result.findings);
    } catch (err) {
      allFindings.push({
        status: "fail",
        severity: "medium",
        category: "structure",
        message: `${name} threw an error: ${(err as Error).message}`,
      });
    }
  };

  await run("scan_secrets", () => scanSecrets(root, targetDir, {}));
  await run("inspect_docker", () => inspectDocker(root, targetDir, {}));
  await run("inspect_environment", () => inspectEnvironment(root, targetDir, {}));
  await run("validate_openapi", () => validateOpenapi(root, targetDir, {}));
  await run("dependency_check", () => dependencyCheck(root, targetDir, {}));
  await run("git_diff", () => gitDiff(root, targetDir, {}));
  if (!input.skipTests) {
    await run("run_tests", () => runTests(root, targetDir, { timeoutMs: 90_000 }));
  }

  const counts: Record<FindingStatus, number> = { pass: 0, warning: 0, fail: 0, info: 0 };
  for (const f of allFindings) counts[f.status]++;

  const critical = allFindings.filter((f) => f.status === "fail" && f.severity === "critical").length;
  const high = allFindings.filter((f) => f.status !== "pass" && f.severity === "high").length;

  return {
    tool: "release_snapshot",
    target: rel,
    generatedAt: new Date().toISOString(),
    findings: allFindings,
    counts,
    toolsRun,
    summary: `${toolsRun.length} check(s) run: ${critical} critical failure(s), ${high} high-severity issue(s), ${counts.warning} warning(s) total.`,
  };
}
