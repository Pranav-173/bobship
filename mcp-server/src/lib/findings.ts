/**
 * Shared finding schema used by every tool in this server.
 *
 * This matches the response format specified in the BobShip execution plan
 * so the release-engine (scoring/report generator) can consume output from
 * every tool identically, regardless of which check produced it.
 */

export type FindingStatus = "pass" | "warning" | "fail" | "info";
export type FindingSeverity = "critical" | "high" | "medium" | "low" | "info";
export type FindingCategory =
  | "testing"
  | "security"
  | "api"
  | "deployment"
  | "documentation"
  | "dependencies"
  | "git"
  | "structure";

export interface Finding {
  status: FindingStatus;
  severity: FindingSeverity;
  category: FindingCategory;
  file?: string;
  line?: number;
  message: string;
}

export function pass(category: FindingCategory, message: string, file?: string): Finding {
  return { status: "pass", severity: "info", category, message, ...(file ? { file } : {}) };
}

export function info(category: FindingCategory, message: string, file?: string): Finding {
  return { status: "info", severity: "info", category, message, ...(file ? { file } : {}) };
}

export function warning(
  category: FindingCategory,
  severity: Exclude<FindingSeverity, "info">,
  message: string,
  file?: string,
  line?: number
): Finding {
  return {
    status: "warning",
    severity,
    category,
    message,
    ...(file ? { file } : {}),
    ...(line !== undefined ? { line } : {}),
  };
}

export function fail(
  category: FindingCategory,
  severity: Exclude<FindingSeverity, "info">,
  message: string,
  file?: string,
  line?: number
): Finding {
  return {
    status: "fail",
    severity,
    category,
    message,
    ...(file ? { file } : {}),
    ...(line !== undefined ? { line } : {}),
  };
}

/** Standard envelope every tool returns, in addition to individual findings. */
export interface ToolResult {
  tool: string;
  target: string;
  summary: string;
  findings: Finding[];
  counts: Record<FindingStatus, number>;
  timedOut?: boolean;
  error?: string;
}

export function buildResult(tool: string, target: string, findings: Finding[], summary?: string): ToolResult {
  const counts: Record<FindingStatus, number> = { pass: 0, warning: 0, fail: 0, info: 0 };
  for (const f of findings) counts[f.status]++;
  const autoSummary =
    counts.fail > 0
      ? `${counts.fail} failing check(s), ${counts.warning} warning(s)`
      : counts.warning > 0
      ? `${counts.warning} warning(s), no failures`
      : `all checks passed (${counts.pass} pass)`;
  return {
    tool,
    target,
    summary: summary ?? autoSummary,
    findings,
    counts,
  };
}
