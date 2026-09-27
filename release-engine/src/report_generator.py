"""
Markdown report generation for the BobShip Release Engine.

Produces a human-readable Markdown release report from a :class:`ReleaseReport`
and writes it to the ``reports/`` directory.

The report is generated entirely from the Release Engine's own computed data —
no hard-coded text, no fake findings.
"""

from __future__ import annotations

import datetime
import os
from typing import List, Optional

from .models import Finding, ReleaseReport, ReleaseScore, ReadinessState, Severity

# Status badge symbols used in the report header
_STATUS_BADGE: dict = {
    ReadinessState.READY: "✅",
    ReadinessState.READY_WITH_WARNINGS: "⚠️",
    ReadinessState.NOT_READY: "🚫",
    ReadinessState.BLOCKED: "🔴",
}

# Default output directory (relative to the repo root when run via Bob)
_DEFAULT_REPORTS_DIR = os.path.join(
    os.path.dirname(__file__),   # release-engine/src/
    "..", "..", "reports"         # → reports/
)


def _section(title: str, level: int = 2) -> str:
    return f"\n{'#' * level} {title}\n"


def _findings_table(findings: List[Finding]) -> str:
    """Render a Markdown table of findings."""
    if not findings:
        return "_No findings._\n"

    lines = [
        "| Severity | Source | Category | Title | File | Line | Remediation |",
        "|----------|--------|----------|-------|------|------|-------------|",
    ]
    for f in findings:
        file_part = f.file_path or "—"
        line_part = str(f.line) if f.line is not None else "—"
        remediation = (f.remediation or "—").replace("|", "&#124;")
        title = f.title.replace("|", "&#124;")
        lines.append(
            f"| `{f.severity.value}` | {f.source} | {f.category} "
            f"| {title} | `{file_part}` | {line_part} | {remediation} |"
        )
    return "\n".join(lines) + "\n"


def _recommended_actions(score: ReleaseScore, blockers: List[Finding]) -> str:
    """Generate a recommended-actions section from the score and blockers."""
    actions: List[str] = []

    if blockers:
        actions.append(
            f"- **Resolve all {score.blocker_count} blocker(s)** before attempting a release."
        )
        for b in blockers:
            loc = f" in `{b.file_path}`" if b.file_path else ""
            rem = f" — {b.remediation}" if b.remediation else ""
            actions.append(f"  - [{b.source}] {b.title}{loc}{rem}")

    if score.warning_count > 0:
        actions.append(
            f"- Review and address {score.warning_count} warning(s) before the next release cycle."
        )

    if not actions:
        actions.append("- No required actions. Repository is release-ready.")

    return "\n".join(actions) + "\n"


def generate_report(
    report: ReleaseReport,
    output_dir: Optional[str] = None,
    filename: Optional[str] = None,
) -> str:
    """
    Generate a Markdown release report and optionally write it to disk.

    Parameters
    ----------
    report     : ReleaseReport
        Computed release report (score + normalized findings).
    output_dir : str, optional
        Directory to write the report into. Defaults to ``reports/``.
        Pass ``None`` to skip writing to disk.
    filename   : str, optional
        Report filename. Defaults to ``release-report-<timestamp>.md``.

    Returns
    -------
    str
        Full Markdown report content.
    """
    now = datetime.datetime.utcnow()
    timestamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Populate generated_at on the report object so it appears in JSON too
    report.generated_at = timestamp

    score = report.score
    badge = _STATUS_BADGE.get(score.readiness, "")
    blockers = [f for f in report.findings if f.severity == Severity.BLOCKER]
    warnings = [f for f in report.findings if f.severity == Severity.WARNING]
    infos = [f for f in report.findings if f.severity == Severity.INFO]

    lines: List[str] = []

    # ── Header ────────────────────────────────────────────────────────────────
    lines.append("# Release Readiness Report\n")
    lines.append(f"**Repository:** {report.repository}  ")
    lines.append(f"**Generated:** {timestamp}  ")
    lines.append(f"**Status:** {badge} `{score.readiness.value}`  ")
    lines.append(f"**Score:** {score.score} / 100  \n")

    # ── Summary ───────────────────────────────────────────────────────────────
    lines.append(_section("Summary"))
    lines.append(
        f"| Metric | Value |\n"
        f"|--------|-------|\n"
        f"| Release Score | **{score.score}** |\n"
        f"| Readiness | **{score.readiness.value}** |\n"
        f"| Blockers | {score.blocker_count} |\n"
        f"| Warnings | {score.warning_count} |\n"
        f"| Info | {score.info_count} |\n"
        f"| Total Findings | {len(report.findings)} |\n"
    )

    # ── Blockers ──────────────────────────────────────────────────────────────
    lines.append(_section("Blockers"))
    if blockers:
        lines.append(
            "> ⚠️ The following issues **must be resolved** before this repository can be released.\n"
        )
        lines.append(_findings_table(blockers))
    else:
        lines.append("_No blockers detected._\n")

    # ── Warnings ──────────────────────────────────────────────────────────────
    lines.append(_section("Warnings"))
    if warnings:
        lines.append(
            "> The following issues are non-blocking but should be addressed.\n"
        )
        lines.append(_findings_table(warnings))
    else:
        lines.append("_No warnings detected._\n")

    # ── Informational ─────────────────────────────────────────────────────────
    if infos:
        lines.append(_section("Informational Findings"))
        lines.append(_findings_table(infos))

    # ── Recommended Actions ───────────────────────────────────────────────────
    lines.append(_section("Recommended Actions"))
    lines.append(_recommended_actions(score, blockers))

    # ── Footer ────────────────────────────────────────────────────────────────
    lines.append("\n---\n")
    lines.append(
        "_This report was generated by the BobShip Release Engine "
        "and orchestrated by IBM Bob._\n"
    )

    markdown = "\n".join(lines)

    # ── Write to disk (optional) ───────────────────────────────────────────────
    if output_dir is not False:  # None triggers default path
        _write_report(markdown, output_dir=output_dir, filename=filename, timestamp=now)

    return markdown


def _write_report(
    content: str,
    output_dir: Optional[str],
    filename: Optional[str],
    timestamp: datetime.datetime,
) -> str:
    """Write the report to ``output_dir`` and return the absolute path."""
    if output_dir is None:
        output_dir = os.path.normpath(_DEFAULT_REPORTS_DIR)

    os.makedirs(output_dir, exist_ok=True)

    if filename is None:
        filename = f"release-report-{timestamp.strftime('%Y%m%d-%H%M%S')}.md"

    path = os.path.join(output_dir, filename)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)

    return path
