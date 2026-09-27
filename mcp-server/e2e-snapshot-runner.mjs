/**
 * E2E helper: runs release_snapshot against a target dir and prints
 * the JSON output to stdout so the release-engine can consume it.
 * Usage: node e2e-snapshot-runner.mjs [targetDir]
 */
import path from "node:path";
import { fileURLToPath } from "node:url";
import { releaseSnapshot } from "./dist/tools/release-tools.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const targetArg = process.argv[2];
const REPO_ROOT = targetArg
  ? path.resolve(targetArg)
  : path.resolve(__dirname, "fixtures/sample-repo");

const snapshot = await releaseSnapshot(REPO_ROOT, REPO_ROOT, { skipTests: false });
process.stdout.write(JSON.stringify(snapshot, null, 2) + "\n");
