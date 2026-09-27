import path from "node:path";
import { walkFiles, readTextFileSafe, findFirstExisting } from "../lib/fsutils.js";
import { buildResult, fail, pass, warning, type ToolResult } from "../lib/findings.js";

export interface InspectEnvironmentInput {
  path?: string;
  envExampleFile?: string;
}

const ENV_VAR_PATTERNS: RegExp[] = [
  /process\.env\.([A-Z0-9_]+)/g, // Node/TS
  /process\.env\[["']([A-Z0-9_]+)["']\]/g, // Node/TS bracket access
  /os\.environ\[["']([A-Z0-9_]+)["']\]/g, // Python
  /os\.environ\.get\(["']([A-Z0-9_]+)["']/g, // Python
  /os\.getenv\(["']([A-Z0-9_]+)["']/g, // Python
];

function parseEnvExampleKeys(content: string): Set<string> {
  const keys = new Set<string>();
  for (const line of content.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const match = trimmed.match(/^([A-Z0-9_]+)\s*=/);
    if (match) keys.add(match[1]);
  }
  return keys;
}

export async function inspectEnvironment(
  root: string,
  targetDir: string,
  input: InspectEnvironmentInput
): Promise<ToolResult> {
  const rel = path.relative(root, targetDir) || ".";
  const findings = [];

  const envExamplePath =
    input.envExampleFile !== undefined
      ? path.join(targetDir, input.envExampleFile)
      : await findFirstExisting(targetDir, [".env.example", ".env.sample", "env.example", ".env.template"]);

  const files = await walkFiles(targetDir, { maxDepth: 14 });
  const usedVars = new Map<string, { file: string; line: number }>();

  for (const file of files) {
    if (![".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py"].includes(file.ext)) continue;
    const content = await readTextFileSafe(file.absPath);
    if (content === null) continue;
    const lines = content.split("\n");
    for (let i = 0; i < lines.length; i++) {
      for (const pattern of ENV_VAR_PATTERNS) {
        pattern.lastIndex = 0;
        let match;
        while ((match = pattern.exec(lines[i])) !== null) {
          if (!usedVars.has(match[1])) usedVars.set(match[1], { file: file.relPath, line: i + 1 });
        }
      }
    }
  }

  if (!envExamplePath) {
    if (usedVars.size > 0) {
      findings.push(
        fail(
          "documentation",
          "medium",
          `No .env.example (or similar) file found, but ${usedVars.size} environment variable(s) are referenced in code. New contributors have no documented list of required config.`
        )
      );
    } else {
      findings.push(pass("documentation", "No environment variables referenced in code, and no .env.example needed."));
    }
    return buildResult("inspect_environment", rel, findings);
  }

  const exampleContent = (await readTextFileSafe(envExamplePath)) ?? "";
  const documentedVars = parseEnvExampleKeys(exampleContent);
  const exampleRel = path.relative(targetDir, envExamplePath);

  const undocumented = [...usedVars.entries()].filter(([name]) => !documentedVars.has(name));
  const unused = [...documentedVars].filter((name) => !usedVars.has(name));

  for (const [name, loc] of undocumented) {
    findings.push(
      warning(
        "documentation",
        "high",
        `Environment variable '${name}' is used in code but missing from ${exampleRel}`,
        loc.file,
        loc.line
      )
    );
  }
  for (const name of unused) {
    findings.push(
      warning("documentation", "low", `'${name}' is documented in ${exampleRel} but never referenced in code (may be stale).`, exampleRel)
    );
  }
  if (undocumented.length === 0 && unused.length === 0) {
    findings.push(pass("documentation", `${exampleRel} matches environment variable usage (${documentedVars.size} vars).`));
  }

  return buildResult("inspect_environment", rel, findings);
}
