"""
CLI entry point for the BobShip Release Engine.

PURPOSE
-------
This CLI is a LOCAL DEVELOPMENT / INTEGRATION helper that lets engineers feed
structured findings into the Release Engine and preview the Markdown report
without requiring a full IBM Bob session.

It does NOT replace IBM Bob as the orchestrator.  Bob calls the Release Engine
as a library (via the MCP server layer).  This CLI exists only so that:
  • contributors can test the engine locally,
  • CI pipelines can run a smoke-test without Bob,
  • the MCP tool can shell out to it if needed in the future.

USAGE
-----
    python -m release_engine [OPTIONS] [FINDINGS_FILE]

    FINDINGS_FILE   Path to a JSON file containing a list of raw finding dicts.
                    Reads from stdin if omitted or if "-" is given.

OPTIONS
    --repository    Human-readable repository name (default: "unknown").
    --output-dir    Directory to write the Markdown report (default: reports/).
    --no-write      Print the report to stdout only; do not write to disk.
    --json          Also print the ReleaseReport as JSON to stdout.
    --help          Show this message and exit.

EXAMPLE
-------
    echo '[{"source":"security","category":"hardcoded-secret",
            "severity":"blocker","title":"Secret in source code",
            "file_path":"config.py","line":42,
            "remediation":"Move to environment variable"}]' |
    python -m release_engine --repository myrepo --no-write
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import os

# Allow running as `python -m release_engine` from the repo root or from
# release-engine/ by adding the src directory to the path if needed.
_SRC_DIR = os.path.dirname(__file__)
if _SRC_DIR not in sys.path:
    sys.path.insert(0, os.path.dirname(_SRC_DIR))

from src import normalize, score, generate  # noqa: E402  (after path setup)
from src.models import ReleaseReport  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="release_engine",
        description=(
            "BobShip Release Engine — normalize findings, score release "
            "readiness, and generate a Markdown report.\n\n"
            "NOTE: IBM Bob is the production orchestrator; this CLI is a "
            "local development / integration helper only."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "findings_file",
        nargs="?",
        default="-",
        metavar="FINDINGS_FILE",
        help="JSON file of raw findings (use '-' or omit for stdin).",
    )
    p.add_argument(
        "--repository",
        default="unknown",
        help="Repository name to embed in the report (default: unknown).",
    )
    p.add_argument(
        "--output-dir",
        default=None,
        dest="output_dir",
        help="Directory to write the report into (default: reports/).",
    )
    p.add_argument(
        "--no-write",
        action="store_true",
        dest="no_write",
        help="Do not write the report to disk; print to stdout only.",
    )
    p.add_argument(
        "--json",
        action="store_true",
        dest="emit_json",
        help="Also emit the structured ReleaseReport JSON to stdout.",
    )
    return p


def main(argv=None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    # ── Read raw findings ─────────────────────────────────────────────────────
    try:
        if args.findings_file == "-":
            raw_text = sys.stdin.read()
        else:
            with open(args.findings_file, encoding="utf-8") as fh:
                raw_text = fh.read()
    except OSError as exc:
        print(f"ERROR: Could not read findings: {exc}", file=sys.stderr)
        return 1

    try:
        raw_findings = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        print(f"ERROR: Invalid JSON: {exc}", file=sys.stderr)
        return 1

    if not isinstance(raw_findings, list):
        print("ERROR: Findings JSON must be a list of objects.", file=sys.stderr)
        return 1

    # ── Normalize → Score → Generate ─────────────────────────────────────────
    findings = normalize(raw_findings)
    release_score = score(findings)

    output_dir = None if args.no_write else args.output_dir

    markdown = generate(
        release_score,
        findings,
        repository=args.repository,
        output_dir=output_dir,
    )

    # ── Output ────────────────────────────────────────────────────────────────
    # Use UTF-8 so emoji/unicode in the report renders on Windows consoles
    # that default to a legacy code page.
    safe_out = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    safe_out.write(markdown + "\n")
    safe_out.flush()
    safe_out.detach()

    if args.emit_json:
        report_obj = ReleaseReport(
            score=release_score,
            findings=findings,
            repository=args.repository,
        )
        print("\n--- JSON ---")
        print(report_obj.to_json())

    if not args.no_write:
        effective_dir = output_dir or os.path.normpath(
            os.path.join(_SRC_DIR, "..", "..", "reports")
        )
        print(f"\nReport written to: {effective_dir}/", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
