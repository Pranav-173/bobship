import path from "node:path";
import * as yaml from "js-yaml";
import { findFirstExisting, readTextFileSafe, walkFiles } from "../lib/fsutils.js";
import { buildResult, fail, info, pass, warning, type ToolResult } from "../lib/findings.js";

export interface ValidateOpenapiInput {
  path?: string;
  specFile?: string;
  backendDir?: string;
}

interface RouteRef {
  method: string;
  route: string;
  file: string;
  line: number;
}

// Best-effort route extraction. Covers the two stacks named in the BobShip
// sample app (FastAPI) plus common Express/Flask patterns. This is a
// heuristic, not a real static analyzer — false negatives are possible for
// dynamically constructed routes.
const ROUTE_PATTERNS: { framework: string; regex: RegExp }[] = [
  // FastAPI / Flask: @app.get("/path"), @router.post('/path')
  { framework: "fastapi/flask", regex: /@(?:app|router)\.(get|post|put|patch|delete)\(\s*["']([^"']+)["']/gi },
  // Express: app.get('/path', ...), router.post("/path", ...)
  { framework: "express", regex: /(?:app|router)\.(get|post|put|patch|delete)\(\s*["']([^"']+)["']/gi },
];

function normalizeRoute(route: string): string {
  // collapse {param} and :param styles to a common token so /users/{id} == /users/:id
  return route.replace(/\{[^}]+\}/g, ":param").replace(/:[A-Za-z0-9_]+/g, ":param").replace(/\/+$/, "") || "/";
}

async function extractSpecRoutes(specPath: string): Promise<{ method: string; route: string }[] | null> {
  const raw = await readTextFileSafe(specPath);
  if (raw === null) return null;
  let doc: any;
  try {
    doc = specPath.endsWith(".json") ? JSON.parse(raw) : yaml.load(raw);
  } catch {
    return null;
  }
  const paths = doc?.paths ?? {};
  const routes: { method: string; route: string }[] = [];
  for (const [route, methods] of Object.entries<any>(paths)) {
    for (const method of Object.keys(methods)) {
      if (["get", "post", "put", "patch", "delete"].includes(method.toLowerCase())) {
        routes.push({ method: method.toLowerCase(), route: normalizeRoute(route) });
      }
    }
  }
  return routes;
}

async function extractCodeRoutes(targetDir: string, backendSubdir: string | undefined): Promise<RouteRef[]> {
  const scanRoot = backendSubdir ? path.join(targetDir, backendSubdir) : targetDir;
  const files = await walkFiles(scanRoot, { maxDepth: 12 });
  const routes: RouteRef[] = [];

  for (const file of files) {
    if (![".py", ".ts", ".js", ".mjs", ".cjs"].includes(file.ext)) continue;
    const content = await readTextFileSafe(file.absPath);
    if (content === null) continue;
    const lines = content.split("\n");

    for (let i = 0; i < lines.length; i++) {
      for (const { regex } of ROUTE_PATTERNS) {
        regex.lastIndex = 0;
        let match;
        while ((match = regex.exec(lines[i])) !== null) {
          routes.push({
            method: match[1].toLowerCase(),
            route: normalizeRoute(match[2]),
            file: path.relative(targetDir, file.absPath),
            line: i + 1,
          });
        }
      }
    }
  }
  return routes;
}

export async function validateOpenapi(root: string, targetDir: string, input: ValidateOpenapiInput): Promise<ToolResult> {
  const rel = path.relative(root, targetDir) || ".";
  const findings = [];

  const specAbs =
    input.specFile !== undefined
      ? path.join(targetDir, input.specFile)
      : await findFirstExisting(targetDir, ["openapi.yaml", "openapi.yml", "openapi.json", "swagger.yaml", "swagger.json"]);

  if (!specAbs) {
    findings.push(info("api", "No OpenAPI spec file found (looked for openapi.yaml/json, swagger.yaml/json) — skipping API contract check."));
    return buildResult("validate_openapi", rel, findings);
  }
  const specRel = path.relative(targetDir, specAbs);

  const specRoutes = await extractSpecRoutes(specAbs);
  if (specRoutes === null) {
    findings.push(fail("api", "medium", `Could not parse OpenAPI spec at ${specRel} (invalid YAML/JSON).`, specRel));
    return buildResult("validate_openapi", rel, findings);
  }
  if (specRoutes.length === 0) {
    findings.push(warning("api", "medium", `${specRel} has no 'paths' defined.`, specRel));
    return buildResult("validate_openapi", rel, findings);
  }

  const codeRoutes = await extractCodeRoutes(targetDir, input.backendDir);
  const specKeys = new Set(specRoutes.map((r) => `${r.method} ${r.route}`));
  const codeKeys = new Map<string, RouteRef>();
  for (const r of codeRoutes) codeKeys.set(`${r.method} ${r.route}`, r);

  const missingInCode = specRoutes.filter((r) => !codeKeys.has(`${r.method} ${r.route}`));
  const undocumented = [...codeKeys.entries()].filter(([key]) => !specKeys.has(key));

  for (const r of missingInCode) {
    findings.push(
      warning(
        "api",
        "high",
        `${r.method.toUpperCase()} ${r.route} is defined in ${specRel} but no matching route was found in the backend code (heuristic match — verify manually).`,
        specRel
      )
    );
  }
  for (const [key, ref] of undocumented) {
    findings.push(
      warning("api", "medium", `${key.toUpperCase()} implemented in code but not documented in ${specRel}.`, ref.file, ref.line)
    );
  }
  if (missingInCode.length === 0 && undocumented.length === 0) {
    findings.push(pass("api", `${specRoutes.length} route(s) in ${specRel} match implemented backend routes.`, specRel));
  }

  findings.push(info("api", `Compared ${specRoutes.length} spec route(s) against ${codeRoutes.length} route(s) found in code. This is a heuristic text match, not a schema-level contract check.`));

  return buildResult("validate_openapi", rel, findings);
}
