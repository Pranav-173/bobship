import { promises as fs } from "node:fs";
import path from "node:path";

export const DEFAULT_IGNORE_DIRS = new Set([
  ".git",
  "node_modules",
  "dist",
  "build",
  "out",
  "__pycache__",
  ".venv",
  "venv",
  ".next",
  ".mypy_cache",
  ".pytest_cache",
  "coverage",
  ".turbo",
  ".cache",
  "target", // rust/java build dirs
]);

// Extensions we treat as text and safe to scan line-by-line.
export const TEXT_EXTENSIONS = new Set([
  ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
  ".py", ".rb", ".go", ".java", ".kt", ".rs", ".php",
  ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
  ".env", ".example", ".sample",
  ".md", ".txt",
  ".html", ".css", ".sql",
  ".sh", ".bash",
  "", // extensionless files like Dockerfile, .env
]);

const MAX_FILE_BYTES = 1_000_000; // 1MB — skip anything bigger when scanning line-by-line

export interface WalkedFile {
  absPath: string;
  relPath: string;
  ext: string;
}

/**
 * Recursively walks a directory, skipping noise dirs and (by default)
 * dotfiles/dotdirs other than a small allowlist relevant to release checks.
 */
export async function walkFiles(
  root: string,
  opts: { maxDepth?: number; includeHidden?: boolean } = {}
): Promise<WalkedFile[]> {
  const maxDepth = opts.maxDepth ?? 12;
  const results: WalkedFile[] = [];

  async function recurse(dir: string, depth: number) {
    if (depth > maxDepth) return;
    let entries;
    try {
      entries = await fs.readdir(dir, { withFileTypes: true });
    } catch {
      return; // unreadable dir (permissions, symlink loop, etc.) — skip silently
    }

    for (const entry of entries) {
      const isHiddenDir = entry.name.startsWith(".") && entry.name !== ".env" && !entry.name.startsWith(".env.");
      if (entry.isDirectory()) {
        if (DEFAULT_IGNORE_DIRS.has(entry.name)) continue;
        if (isHiddenDir && !opts.includeHidden) continue;
        await recurse(path.join(dir, entry.name), depth + 1);
      } else if (entry.isFile()) {
        const abs = path.join(dir, entry.name);
        results.push({ absPath: abs, relPath: path.relative(root, abs), ext: path.extname(entry.name) });
      }
    }
  }

  await recurse(root, 0);
  return results;
}

/** Reads a file as UTF-8 text, returning null if it's binary, missing, or too large. */
export async function readTextFileSafe(absPath: string): Promise<string | null> {
  try {
    const stat = await fs.stat(absPath);
    if (stat.size > MAX_FILE_BYTES) return null;
    const buf = await fs.readFile(absPath);
    // crude binary sniff: presence of a NUL byte in the first 8KB
    const sample = buf.subarray(0, 8192);
    if (sample.includes(0)) return null;
    return buf.toString("utf-8");
  } catch {
    return null;
  }
}

export async function fileExists(absPath: string): Promise<boolean> {
  try {
    await fs.access(absPath);
    return true;
  } catch {
    return false;
  }
}

/** Finds the first file (relative to root) matching any of the given candidate names. */
export async function findFirstExisting(root: string, candidates: string[]): Promise<string | null> {
  for (const c of candidates) {
    const abs = path.join(root, c);
    if (await fileExists(abs)) return abs;
  }
  return null;
}

/** Resolves a user-supplied relative path against the server's working directory, rejecting escapes. */
export function resolveTarget(root: string, userPath: string | undefined): string {
  const base = path.resolve(root);
  const resolved = path.resolve(base, userPath ?? ".");
  if (!resolved.startsWith(base)) {
    throw new Error(`Path '${userPath}' escapes the allowed project root.`);
  }
  return resolved;
}
