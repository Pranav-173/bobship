import path from "node:path";
import { runCommand } from "../lib/exec.js";
import { buildResult, fail, info, pass, warning, type ToolResult } from "../lib/findings.js";

export interface GitDiffInput {
  path?: string;
  against?: string; // base ref, default HEAD
  includeStaged?: boolean;
}

export async function gitDiff(root: string, targetDir: string, input: GitDiffInput): Promise<ToolResult> {
  const against = input.against ?? "HEAD";
  const rel = path.relative(root, targetDir) || ".";

  const isRepo = await runCommand("git", ["rev-parse", "--is-inside-work-tree"], { cwd: targetDir, timeoutMs: 10_000 });
  if (isRepo.code !== 0) {
    return buildResult("git_diff", rel, [fail("git", "medium", "Not a git repository (or git is not installed).")]);
  }

  const branch = await runCommand("git", ["rev-parse", "--abbrev-ref", "HEAD"], { cwd: targetDir, timeoutMs: 10_000 });
  const status = await runCommand("git", ["status", "--porcelain=v1"], { cwd: targetDir, timeoutMs: 15_000 });
  const diffStat = await runCommand("git", ["diff", "--stat", against], { cwd: targetDir, timeoutMs: 15_000 });
  const lastCommit = await runCommand("git", ["log", "-1", "--pretty=format:%h %s (%an, %ar)"], {
    cwd: targetDir,
    timeoutMs: 10_000,
  });

  const changedLines = status.stdout.split("\n").filter((l) => l.trim().length > 0);
  const findings = [];

  if (changedLines.length === 0) {
    findings.push(pass("git", `Working tree is clean on branch '${branch.stdout.trim()}'.`));
  } else {
    findings.push(
      info(
        "git",
        `${changedLines.length} file(s) changed on branch '${branch.stdout.trim()}' vs working tree.`
      )
    );
    for (const line of changedLines.slice(0, 50)) {
      const statusCode = line.slice(0, 2).trim();
      const file = line.slice(3).trim();
      const label =
        statusCode === "??" ? "untracked" : statusCode === "M" ? "modified" : statusCode === "D" ? "deleted" : statusCode === "A" ? "added" : statusCode;
      findings.push(warning("git", "low", `${label}: ${file}`, file));
    }
    if (changedLines.length > 50) {
      findings.push(info("git", `...and ${changedLines.length - 50} more changed file(s) (truncated).`));
    }
  }

  const result = buildResult("git_diff", rel, findings);
  return {
    ...result,
    ...{
      branch: branch.stdout.trim(),
      lastCommit: lastCommit.stdout.trim() || null,
      diffStat: diffStat.stdout.trim() || "(no diff against " + against + ")",
    },
  } as ToolResult & { branch: string; lastCommit: string | null; diffStat: string };
}
