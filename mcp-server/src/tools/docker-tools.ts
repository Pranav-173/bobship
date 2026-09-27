import path from "node:path";
import * as yaml from "js-yaml";
import { findFirstExisting, readTextFileSafe, walkFiles } from "../lib/fsutils.js";
import { buildResult, fail, pass, warning, type ToolResult } from "../lib/findings.js";

export interface InspectDockerInput {
  path?: string;
}

export async function inspectDocker(root: string, targetDir: string, _input: InspectDockerInput): Promise<ToolResult> {
  const rel = path.relative(root, targetDir) || ".";
  const findings = [];

  const allFiles = await walkFiles(targetDir, { maxDepth: 6 });
  const dockerfiles = allFiles.filter((f) => path.basename(f.relPath) === "Dockerfile" || f.relPath.match(/Dockerfile\.\w+$/));
  const composePath = await findFirstExisting(targetDir, ["docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"]);

  if (dockerfiles.length === 0 && !composePath) {
    findings.push(warning("deployment", "medium", "No Dockerfile or docker-compose file found in the project."));
    return buildResult("inspect_docker", rel, findings);
  }

  for (const df of dockerfiles) {
    const content = (await readTextFileSafe(df.absPath)) ?? "";
    const hasHealthcheck = /^\s*HEALTHCHECK\b/im.test(content);
    const runsAsRoot = !/^\s*USER\s+\S+/im.test(content);
    const hasExpose = /^\s*EXPOSE\b/im.test(content);
    const pinnedBase = /^\s*FROM\s+\S+:(?!latest)\S+/im.test(content);
    const usesLatestTag = /^\s*FROM\s+\S+:latest\b/im.test(content) || /^\s*FROM\s+[^:\s]+\s*$/im.test(content);

    if (!hasHealthcheck) {
      findings.push(warning("deployment", "medium", "Dockerfile has no HEALTHCHECK instruction.", df.relPath));
    } else {
      findings.push(pass("deployment", "HEALTHCHECK instruction present.", df.relPath));
    }

    if (runsAsRoot) {
      findings.push(warning("deployment", "medium", "Dockerfile does not set a non-root USER; container will run as root.", df.relPath));
    } else {
      findings.push(pass("deployment", "Container runs as a non-root user.", df.relPath));
    }

    if (usesLatestTag) {
      findings.push(warning("deployment", "low", "Base image uses ':latest' (or no tag), which is not reproducible.", df.relPath));
    } else if (pinnedBase) {
      findings.push(pass("deployment", "Base image is pinned to a specific tag.", df.relPath));
    }

    if (!hasExpose) {
      findings.push(warning("deployment", "low", "No EXPOSE instruction found; port intent is undocumented.", df.relPath));
    }
  }

  if (composePath) {
    const composeRel = path.relative(targetDir, composePath);
    const raw = (await readTextFileSafe(composePath)) ?? "";
    try {
      const doc = yaml.load(raw) as any;
      const services = doc?.services ?? {};
      const serviceNames = Object.keys(services);
      if (serviceNames.length === 0) {
        findings.push(warning("deployment", "medium", "docker-compose file has no services defined.", composeRel));
      }
      for (const name of serviceNames) {
        const svc = services[name];
        if (!svc.healthcheck) {
          findings.push(warning("deployment", "medium", `Service '${name}' has no healthcheck defined.`, composeRel));
        } else {
          findings.push(pass("deployment", `Service '${name}' defines a healthcheck.`, composeRel));
        }
        if (!svc.restart) {
          findings.push(warning("deployment", "low", `Service '${name}' has no restart policy set.`, composeRel));
        }
      }
    } catch (err) {
      findings.push(fail("deployment", "medium", `Failed to parse docker-compose YAML: ${(err as Error).message}`, composeRel));
    }
  } else {
    findings.push(warning("deployment", "low", "No docker-compose file found (may be intentional for single-container apps)."));
  }

  return buildResult("inspect_docker", rel, findings);
}
