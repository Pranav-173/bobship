import path from "node:path";
import { commandExists, runCommand } from "../lib/exec.js";
import { fileExists, findFirstExisting, readTextFileSafe } from "../lib/fsutils.js";
import { buildResult, fail, info, pass, warning, type ToolResult } from "../lib/findings.js";

export interface RunTestsInput {
  path?: string;
  timeoutMs?: number;
}

type Runner = "pytest" | "npm" | "none";

async function detectRunner(targetDir: string): Promise<Runner> {
  if (await fileExists(path.join(targetDir, "package.json"))) {
    const pkgRaw = await readTextFileSafe(path.join(targetDir, "package.json"));
    if (pkgRaw) {
      try {
        const pkg = JSON.parse(pkgRaw);
        if (pkg.scripts?.test) return "npm";
      } catch {
        /* fall through */
      }
    }
  }
  const hasPytestConfig = await findFirstExisting(targetDir, ["pytest.ini", "pyproject.toml", "setup.cfg"]);
  const hasTestsDir = await fileExists(path.join(targetDir, "tests"));
  if (hasPytestConfig || hasTestsDir) return "pytest";
  return "none";
}

function parsePytestSummary(output: string): { passed: number; failed: number; errors: number; raw: string } | null {
  // e.g. "5 passed, 2 failed, 1 error in 1.23s" (order/presence of each group varies)
  const line = output.split("\n").reverse().find((l) => /\d+ (passed|failed|error)/.test(l));
  if (!line) return null;
  const passed = Number(line.match(/(\d+) passed/)?.[1] ?? 0);
  const failed = Number(line.match(/(\d+) failed/)?.[1] ?? 0);
  const errors = Number(line.match(/(\d+) error/)?.[1] ?? 0);
  return { passed, failed, errors, raw: line.trim() };
}

function parseNpmTestOutput(output: string): { passed: number; failed: number; raw: string } | null {
  // Best-effort across common runners (jest/vitest print a summary line like this)
  const failMatch = output.match(/Tests:\s+(\d+) failed,\s*(\d+) passed/i) ?? output.match(/(\d+) failing/i);
  const passMatch = output.match(/Tests:\s+(\d+) passed/i) ?? output.match(/(\d+) passing/i);
  if (!failMatch && !passMatch) return null;
  const failed = failMatch ? Number(failMatch[1]) : 0;
  const passed = passMatch ? Number(passMatch[passMatch.length === 2 && !failMatch ? 1 : 1]) : 0;
  return { passed, failed, raw: (failMatch?.[0] ?? "") + " " + (passMatch?.[0] ?? "") };
}

export async function runTests(root: string, targetDir: string, input: RunTestsInput): Promise<ToolResult> {
  const rel = path.relative(root, targetDir) || ".";
  const timeoutMs = input.timeoutMs ?? 120_000;
  const runner = await detectRunner(targetDir);

  if (runner === "none") {
    return buildResult("run_tests", rel, [
      warning("testing", "medium", "No test runner detected (no package.json 'test' script, pytest config, or tests/ directory)."),
    ]);
  }

  if (runner === "pytest") {
    const hasPytest = await commandExists("pytest", targetDir);
    if (!hasPytest) {
      return buildResult("run_tests", rel, [
        fail("testing", "medium", "pytest config/tests directory found, but 'pytest' is not installed or not on PATH."),
      ]);
    }
    const result = await runCommand("pytest", ["-q"], { cwd: targetDir, timeoutMs });
    const summary = parsePytestSummary(result.stdout + "\n" + result.stderr);
    const findings = [];
    if (result.timedOut) {
      findings.push(fail("testing", "high", `pytest did not finish within ${timeoutMs}ms and was killed.`));
    } else if (summary) {
      if (summary.failed > 0 || summary.errors > 0) {
        findings.push(fail("testing", "critical", `pytest: ${summary.raw}`));
      } else {
        findings.push(pass("testing", `pytest: ${summary.raw}`));
      }
    } else if (result.code === 0) {
      findings.push(pass("testing", `pytest exited successfully (code 0), but no summary line could be parsed.`));
    } else {
      findings.push(
        fail(
          "testing",
          "high",
          `pytest exited with code ${result.code}. Output: ${(result.stdout + result.stderr).slice(-500)}`
        )
      );
    }
    return buildResult("run_tests", rel, findings);
  }

  // npm
  const result = await runCommand("npm", ["test", "--silent"], { cwd: targetDir, timeoutMs });
  const summary = parseNpmTestOutput(result.stdout + "\n" + result.stderr);
  const findings = [];
  if (result.timedOut) {
    findings.push(fail("testing", "high", `'npm test' did not finish within ${timeoutMs}ms and was killed.`));
  } else if (summary && (summary.passed > 0 || summary.failed > 0)) {
    if (summary.failed > 0) {
      findings.push(fail("testing", "critical", `npm test: ${summary.passed} passed, ${summary.failed} failed.`));
    } else {
      findings.push(pass("testing", `npm test: ${summary.passed} passed, 0 failed.`));
    }
  } else {
    findings.push(
      result.code === 0
        ? pass("testing", "npm test exited successfully (could not parse a detailed pass/fail summary).")
        : fail("testing", "high", `npm test exited with code ${result.code}. Tail: ${(result.stdout + result.stderr).slice(-500)}`)
    );
  }
  return buildResult("run_tests", rel, findings);
}

export interface GetTestCoverageInput {
  path?: string;
}

export async function getTestCoverage(root: string, targetDir: string, _input: GetTestCoverageInput): Promise<ToolResult> {
  const rel = path.relative(root, targetDir) || ".";

  // JS/TS: istanbul/jest/vitest coverage-summary.json
  const jsSummary = await findFirstExisting(targetDir, [
    "coverage/coverage-summary.json",
    "coverage/coverage-final.json",
  ]);
  if (jsSummary) {
    const raw = await readTextFileSafe(jsSummary);
    if (raw) {
      try {
        const data = JSON.parse(raw);
        const total = data.total;
        if (total?.lines?.pct !== undefined) {
          const pct = total.lines.pct;
          const finding =
            pct >= 80 ? pass("testing", `Line coverage: ${pct}% (from ${path.relative(targetDir, jsSummary)}).`) :
            pct >= 50 ? warning("testing", "medium", `Line coverage is ${pct}% — below the common 80% bar.`) :
            fail("testing", "high", `Line coverage is only ${pct}%.`);
          return buildResult("get_test_coverage", rel, [finding]);
        }
      } catch {
        /* fall through to "unknown" */
      }
    }
  }

  // Python: coverage.xml (cobertura format) — extract line-rate attribute
  const coverageXml = await findFirstExisting(targetDir, ["coverage.xml"]);
  if (coverageXml) {
    const raw = await readTextFileSafe(coverageXml);
    const match = raw?.match(/line-rate="([\d.]+)"/);
    if (match) {
      const pct = Math.round(Number(match[1]) * 100);
      const finding =
        pct >= 80 ? pass("testing", `Line coverage: ${pct}% (from coverage.xml).`) :
        pct >= 50 ? warning("testing", "medium", `Line coverage is ${pct}% — below the common 80% bar.`) :
        fail("testing", "high", `Line coverage is only ${pct}%.`);
      return buildResult("get_test_coverage", rel, [finding]);
    }
  }

  return buildResult("get_test_coverage", rel, [
    info(
      "testing",
      "No coverage report found. Run tests with coverage enabled first (e.g. 'pytest --cov --cov-report=xml' or 'jest --coverage') so this tool has something to read."
    ),
  ]);
}
