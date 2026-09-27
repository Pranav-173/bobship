"""
BobShip End-to-End Integration Script.

Reads a ReleaseSnapshot JSON file (produced by the real MCP server), passes it
through the full Release Engine pipeline, and writes a Markdown report to
reports/.

Usage:
    python e2e_pipeline.py <snapshot_json_file> [--repository NAME] [--output-dir DIR]
"""

from __future__ import annotations

import json
import os
import sys
import argparse

# Allow running from repo root
_REPO_ROOT = os.path.dirname(__file__)
_ENGINE_DIR = os.path.join(_REPO_ROOT, "release-engine")
if _ENGINE_DIR not in sys.path:
    sys.path.insert(0, _ENGINE_DIR)

from src.mcp_adapter import findings_from_snapshot
from src.analyzer import normalize_findings
from src.scoring import score_findings
from src.models import ReleaseReport
from src.report_generator import generate_report


def main() -> int:
    parser = argparse.ArgumentParser(description="BobShip E2E pipeline: MCP snapshot → Release Engine → Markdown report")
    parser.add_argument("snapshot_file", help="Path to MCP ReleaseSnapshot JSON file")
    parser.add_argument("--repository", default="BobShip/fixtures/sample-repo", help="Repository name for the report")
    parser.add_argument("--output-dir", default=None, dest="output_dir", help="Output directory for the report")
    parser.add_argument("--no-write", action="store_true", dest="no_write", help="Print to stdout only, do not write file")
    args = parser.parse_args()

    # 1. Load the real MCP snapshot
    with open(args.snapshot_file, encoding="utf-8-sig") as fh:
        snapshot = json.load(fh)

    print(f"[E2E] Loaded snapshot: tool={snapshot.get('tool')}, target={snapshot.get('target')}", file=sys.stderr)
    print(f"[E2E] MCP findings count: {len(snapshot.get('findings', []))}", file=sys.stderr)
    print(f"[E2E] MCP tools run: {snapshot.get('toolsRun', [])}", file=sys.stderr)
    print(f"[E2E] MCP counts: {snapshot.get('counts', {})}", file=sys.stderr)

    # 2. Adapter: MCP snapshot → raw finding dicts
    raw_findings = findings_from_snapshot(snapshot)
    print(f"\n[E2E] Adapter produced {len(raw_findings)} raw findings", file=sys.stderr)

    # 3. Normalize
    findings = normalize_findings(raw_findings)
    print(f"[E2E] Normalized findings: {len(findings)}", file=sys.stderr)

    # 4. Score
    release_score = score_findings(findings)
    print(f"\n[E2E] --- Release Engine Result ---", file=sys.stderr)
    print(f"[E2E] Score:       {release_score.score} / 100", file=sys.stderr)
    print(f"[E2E] Readiness:   {release_score.readiness.value}", file=sys.stderr)
    print(f"[E2E] Blockers:    {release_score.blocker_count}", file=sys.stderr)
    print(f"[E2E] Warnings:    {release_score.warning_count}", file=sys.stderr)
    print(f"[E2E] Info:        {release_score.info_count}", file=sys.stderr)

    # Severity breakdown
    from src.models import Severity
    by_severity = {}
    for f in findings:
        by_severity.setdefault(f.severity.value, []).append(f)
    for sev, items in sorted(by_severity.items()):
        print(f"[E2E]   {sev}: {len(items)} finding(s)", file=sys.stderr)
        for item in items:
            loc = f" [{item.file_path}:{item.line}]" if item.file_path else ""
            print(f"[E2E]     - [{item.source}] {item.title}{loc}", file=sys.stderr)

    # 5. Generate report
    output_dir = None if args.no_write else (args.output_dir or os.path.join(_REPO_ROOT, "reports"))
    report = ReleaseReport(score=release_score, findings=findings, repository=args.repository)

    import datetime
    ts = datetime.datetime.utcnow()
    filename = f"e2e-release-report-{ts.strftime('%Y%m%d-%H%M%S')}.md"

    markdown = generate_report(report, output_dir=output_dir, filename=filename)

    if args.no_write:
        print(markdown)
    else:
        report_path = os.path.join(output_dir, filename)
        print(f"\n[E2E] Report written to: {report_path}", file=sys.stderr)
        print(f"[E2E] Report path (absolute): {os.path.abspath(report_path)}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
