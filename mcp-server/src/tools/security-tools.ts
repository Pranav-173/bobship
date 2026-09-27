import path from "node:path";
import { walkFiles, readTextFileSafe, TEXT_EXTENSIONS } from "../lib/fsutils.js";
import { buildResult, fail, pass, type ToolResult } from "../lib/findings.js";

export interface ScanSecretsInput {
  path?: string;
}

interface SecretPattern {
  name: string;
  regex: RegExp;
  severity: "critical" | "high" | "medium";
}

// Best-effort heuristics — false positives are expected and acceptable for a
// hackathon-scope scanner; the goal is to catch the obvious, common cases.
const PATTERNS: SecretPattern[] = [
  { name: "AWS Access Key ID", regex: /\bAKIA[0-9A-Z]{16}\b/, severity: "critical" },
  { name: "Generic private key header", regex: /-----BEGIN (RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----/, severity: "critical" },
  { name: "Stripe live secret key", regex: /\bsk_live_[0-9a-zA-Z]{16,}\b/, severity: "critical" },
  { name: "Slack token", regex: /\bxox[baprs]-[0-9a-zA-Z-]{10,}\b/, severity: "high" },
  { name: "GitHub token", regex: /\bgh[pousr]_[0-9A-Za-z]{20,}\b/, severity: "high" },
  { name: "Generic JWT", regex: /\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b/, severity: "medium" },
  {
    name: "Hardcoded secret/password/token assignment",
    regex: /\b(secret|password|passwd|api[_-]?key|access[_-]?key|token)\s*[:=]\s*["'][^"'\s]{6,}["']/i,
    severity: "high",
  },
  {
    name: "Hardcoded database connection string with credentials",
    regex: /\b(postgres|postgresql|mysql|mongodb):\/\/[^:\s]+:[^@\s]+@/i,
    severity: "high",
  },
];

// Lines that are almost certainly placeholders, not real secrets.
const PLACEHOLDER_HINT = /(your[-_ ]?|example|placeholder|xxxx|changeme|<.*>|\$\{|%\{|dummy|test[-_ ]?value|fake)/i;

const SKIP_FILE_SUFFIXES = [".lock", ".map", ".min.js", ".svg", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2"];

export async function scanSecrets(root: string, targetDir: string, _input: ScanSecretsInput): Promise<ToolResult> {
  const rel = path.relative(root, targetDir) || ".";
  const files = await walkFiles(targetDir, { maxDepth: 14 });
  const findings = [];
  let filesScanned = 0;

  for (const file of files) {
    if (SKIP_FILE_SUFFIXES.some((s) => file.relPath.endsWith(s))) continue;
    if (!TEXT_EXTENSIONS.has(file.ext) && file.ext !== "") continue;

    const content = await readTextFileSafe(file.absPath);
    if (content === null) continue;
    filesScanned++;

    const lines = content.split("\n");
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      if (line.trim().startsWith("//") || line.trim().startsWith("#")) continue; // skip comments (reduces noise)

      for (const pattern of PATTERNS) {
        if (pattern.regex.test(line)) {
          const looksLikePlaceholder = PLACEHOLDER_HINT.test(line);
          findings.push(
            fail(
              "security",
              looksLikePlaceholder ? "medium" : pattern.severity,
              `${pattern.name} detected${looksLikePlaceholder ? " (looks like a placeholder — verify manually)" : ""}`,
              file.relPath,
              i + 1
            )
          );
          break; // one finding per line is enough
        }
      }
    }
  }

  if (findings.length === 0) {
    findings.push(pass("security", `No obvious hardcoded secrets found across ${filesScanned} text file(s) scanned.`));
  }

  return buildResult("scan_secrets", rel, findings);
}
