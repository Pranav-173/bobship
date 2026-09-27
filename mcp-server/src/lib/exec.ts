import { spawn } from "node:child_process";

export interface ExecResult {
  stdout: string;
  stderr: string;
  code: number | null;
  timedOut: boolean;
}

/**
 * Runs a command with a hard timeout. Never throws on non-zero exit —
 * callers inspect `code`/`stderr` themselves, since a non-zero exit is
 * often the actual signal a tool is checking for (e.g. failing tests).
 */
export function runCommand(
  command: string,
  args: string[],
  options: { cwd: string; timeoutMs?: number; env?: NodeJS.ProcessEnv }
): Promise<ExecResult> {
  const timeoutMs = options.timeoutMs ?? 60_000;

  return new Promise((resolve) => {
    let stdout = "";
    let stderr = "";
    let timedOut = false;

    let child;
    try {
      child = spawn(command, args, {
        cwd: options.cwd,
        env: options.env ?? process.env,
        shell: false,
      });
    } catch (err) {
      resolve({ stdout: "", stderr: `Failed to spawn ${command}: ${(err as Error).message}`, code: -1, timedOut: false });
      return;
    }

    const timer = setTimeout(() => {
      timedOut = true;
      child.kill("SIGKILL");
    }, timeoutMs);

    child.stdout?.on("data", (d) => {
      stdout += d.toString();
      if (stdout.length > 500_000) child.kill("SIGKILL"); // guard against runaway output
    });
    child.stderr?.on("data", (d) => {
      stderr += d.toString();
      if (stderr.length > 200_000) child.kill("SIGKILL");
    });

    child.on("error", (err) => {
      clearTimeout(timer);
      resolve({ stdout, stderr: stderr + `\n${err.message}`, code: -1, timedOut });
    });

    child.on("close", (code) => {
      clearTimeout(timer);
      resolve({ stdout, stderr, code, timedOut });
    });
  });
}

/** True if a command exists on PATH (best-effort, POSIX `which`). */
export async function commandExists(command: string, cwd: string): Promise<boolean> {
  const result = await runCommand("which", [command], { cwd, timeoutMs: 5_000 });
  return result.code === 0 && result.stdout.trim().length > 0;
}
