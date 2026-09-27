import path from "node:path";
import { runCommand } from "../lib/exec.js";
import { fileExists, readTextFileSafe } from "../lib/fsutils.js";
import { buildResult, fail, info, pass, warning, type ToolResult } from "../lib/findings.js";

export interface DependencyCheckInput {
  path?: string;
  runAudit?: boolean; // opt-in: shells out to `npm audit`, requires network access
}

export async function dependencyCheck(root: string, targetDir: string, input: DependencyCheckInput): Promise<ToolResult> {
  const rel = path.relative(root, targetDir) || ".";
  const findings = [];
  let checkedAny = false;

  // --- Node/npm ---
  const pkgPath = path.join(targetDir, "package.json");
  if (await fileExists(pkgPath)) {
    checkedAny = true;
    const raw = await readTextFileSafe(pkgPath);
    const hasLock = (await fileExists(path.join(targetDir, "package-lock.json"))) ||
      (await fileExists(path.join(targetDir, "yarn.lock"))) ||
      (await fileExists(path.join(targetDir, "pnpm-lock.yaml")));

    if (!hasLock) {
      findings.push(warning("dependencies", "medium", "No lockfile found (package-lock.json/yarn.lock/pnpm-lock.yaml) — dependency versions are not pinned reproducibly.", "package.json"));
    } else {
      findings.push(pass("dependencies", "Lockfile present.", "package.json"));
    }

    if (raw) {
      try {
        const pkg = JSON.parse(raw);
        const deps = { ...(pkg.dependencies ?? {}), ...(pkg.devDependencies ?? {}) };
        const wildcards = Object.entries(deps).filter(([, v]) => v === "*" || v === "latest");
        for (const [name] of wildcards) {
          findings.push(warning("dependencies", "medium", `'${name}' has no version constraint ('*'/'latest') — builds are not reproducible.`, "package.json"));
        }
      } catch {
        findings.push(fail("dependencies", "low", "package.json could not be parsed as JSON.", "package.json"));
      }
    }

    if (input.runAudit) {
      const audit = await runCommand("npm", ["audit", "--json"], { cwd: targetDir, timeoutMs: 60_000 });
      try {
        const data = JSON.parse(audit.stdout || "{}");
        const meta = data.metadata?.vulnerabilities;
        if (meta) {
          const critical = meta.critical ?? 0;
          const high = meta.high ?? 0;
          const moderate = meta.moderate ?? 0;
          if (critical > 0 || high > 0) {
            findings.push(fail("dependencies", "critical", `npm audit: ${critical} critical, ${high} high severity vulnerabilities.`));
          } else if (moderate > 0) {
            findings.push(warning("dependencies", "medium", `npm audit: ${moderate} moderate severity vulnerabilities.`));
          } else {
            findings.push(pass("dependencies", "npm audit: no known vulnerabilities."));
          }
        }
      } catch {
        findings.push(info("dependencies", "npm audit ran but its output could not be parsed (or npm audit failed — check network access)."));
      }
    }
  }

  // --- Python/pip ---
  const reqPath = path.join(targetDir, "requirements.txt");
  if (await fileExists(reqPath)) {
    checkedAny = true;
    const raw = (await readTextFileSafe(reqPath)) ?? "";
    const lines = raw.split("\n").map((l) => l.trim()).filter((l) => l && !l.startsWith("#"));
    const unpinned = lines.filter((l) => !/[=<>~]=?/.test(l));
    for (const l of unpinned) {
      findings.push(warning("dependencies", "medium", `'${l}' has no version pin in requirements.txt — builds are not reproducible.`, "requirements.txt"));
    }
    if (unpinned.length === 0 && lines.length > 0) {
      findings.push(pass("dependencies", `All ${lines.length} requirement(s) in requirements.txt are version-pinned.`, "requirements.txt"));
    }
  }

  if (!checkedAny) {
    findings.push(info("dependencies", "No package.json or requirements.txt found — nothing to check."));
  }

  return buildResult("dependency_check", rel, findings);
}
