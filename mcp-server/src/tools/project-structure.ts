import path from "node:path";
import { walkFiles } from "../lib/fsutils.js";
import { buildResult, info, type ToolResult } from "../lib/findings.js";

export interface ProjectStructureInput {
  path?: string;
  maxDepth?: number;
}

interface TreeNode {
  name: string;
  type: "dir" | "file";
  children?: TreeNode[];
}

function buildTree(relPaths: string[]): TreeNode[] {
  const root: TreeNode & { childMap?: Map<string, any> } = { name: "", type: "dir", children: [] };
  const map = new Map<string, any>();
  map.set("", root);

  for (const rel of relPaths) {
    const parts = rel.split(path.sep);
    let currentPath = "";
    let parent = root;
    for (let i = 0; i < parts.length; i++) {
      const isFile = i === parts.length - 1;
      currentPath = currentPath ? `${currentPath}/${parts[i]}` : parts[i];
      if (isFile) {
        parent.children!.push({ name: parts[i], type: "file" });
      } else {
        let node = map.get(currentPath);
        if (!node) {
          node = { name: parts[i], type: "dir", children: [] };
          map.set(currentPath, node);
          parent.children!.push(node);
        }
        parent = node;
      }
    }
  }
  return root.children ?? [];
}

export async function projectStructure(root: string, targetDir: string, input: ProjectStructureInput): Promise<ToolResult> {
  const maxDepth = input.maxDepth ?? 4;
  const files = await walkFiles(targetDir, { maxDepth });

  const byExt = new Map<string, number>();
  for (const f of files) {
    const key = f.ext || "(no extension)";
    byExt.set(key, (byExt.get(key) ?? 0) + 1);
  }

  const topExts = [...byExt.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 15)
    .map(([ext, count]) => `${ext}: ${count}`)
    .join(", ");

  const tree = buildTree(files.map((f) => f.relPath).sort());

  const findings = [
    info("structure", `${files.length} files scanned (depth <= ${maxDepth}). Top extensions: ${topExts || "none"}`),
  ];

  const result = buildResult("project_structure", path.relative(root, targetDir) || ".", findings);
  return { ...result, ...{ tree, fileCount: files.length } } as ToolResult & { tree: TreeNode[]; fileCount: number };
}
