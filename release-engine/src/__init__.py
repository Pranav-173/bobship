"""
BobShip Release Engine — public API.

This package provides three primary entry points that IBM Bob (via MCP tools
or subagent orchestration) uses to drive the release-engineering workflow:

    normalize(raw_findings)          → list[Finding]
    score(findings)                  → ReleaseScore
    generate(score, findings, ...)   → str  (Markdown)

Typical usage (orchestrated by IBM Bob)
----------------------------------------
    import release_engine as engine

    findings = engine.normalize(raw_findings_from_subagents)
    result   = engine.score(findings)
    report   = engine.generate(result, findings, repository="my-repo")
"""

from .analyzer import normalize_finding, normalize_findings as normalize
from .models import Finding, ReadinessState, ReleaseReport, ReleaseScore, Severity
from .report_generator import generate_report
from .scoring import score_findings as score


def generate(
    release_score: ReleaseScore,
    findings: list,
    repository: str = "unknown",
    output_dir=None,
    filename=None,
) -> str:
    """
    Convenience wrapper: build a :class:`ReleaseReport` and generate Markdown.

    Parameters
    ----------
    release_score : ReleaseScore
        The computed score (from :func:`score`).
    findings      : list of Finding
        Normalized findings (from :func:`normalize`).
    repository    : str
        Human-readable repository name included in the report header.
    output_dir    : str or None
        Directory to write the report into (``reports/`` by default).
    filename      : str or None
        Override the report filename.

    Returns
    -------
    str
        Markdown report content.
    """
    report = ReleaseReport(
        score=release_score,
        findings=findings,
        repository=repository,
    )
    return generate_report(report, output_dir=output_dir, filename=filename)


__all__ = [
    # Primary API
    "normalize",
    "normalize_finding",
    "score",
    "generate",
    # Models (consumers may need these for type hints)
    "Finding",
    "ReleaseScore",
    "ReleaseReport",
    "ReadinessState",
    "Severity",
]
