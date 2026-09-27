"""
Release scoring for the BobShip Release Engine.

Scoring rules are implemented EXACTLY as specified in
.bob/skills/release-engineer/SKILL.md:

    90–100  → READY
    75–89   → READY WITH WARNINGS
    50–74   → NOT READY
    0–49    → BLOCKED

Score formula
-------------
    score = max(0, 100 - (blockers * 25) - (warnings * 5))

Rationale
~~~~~~~~~
* One BLOCKER deducts 25 points → three blockers push a clean repo into
  NOT READY (100 - 75 = 25) and four into BLOCKED (100 - 100 = 0).
* One WARNING deducts 5 points  → up to two warnings keep the repo in READY
  (100 - 10 = 90); three or more land in READY WITH WARNINGS.
* INFO findings do not affect the score — they are purely informational.
* The score is clamped to [0, 100] and truncated to an integer.
"""

from __future__ import annotations

from typing import List

from .models import Finding, ReadinessState, ReleaseScore, Severity

# Deduction constants
_BLOCKER_DEDUCTION: int = 25
_WARNING_DEDUCTION: int = 5


def _readiness_from_score(score: int) -> ReadinessState:
    """
    Map a numeric score to the canonical readiness state.

    Bands as defined in .bob/skills/release-engineer/SKILL.md:
        90–100  → READY
        75–89   → READY WITH WARNINGS
        50–74   → NOT READY
        0–49    → BLOCKED
    """
    if score >= 90:
        return ReadinessState.READY
    if score >= 75:
        return ReadinessState.READY_WITH_WARNINGS
    if score >= 50:
        return ReadinessState.NOT_READY
    return ReadinessState.BLOCKED


def score_findings(findings: List[Finding]) -> ReleaseScore:
    """
    Calculate the release score and readiness state for a list of findings.

    Parameters
    ----------
    findings : list of Finding
        Normalized findings (may be empty for a clean repository).

    Returns
    -------
    ReleaseScore
        Computed score, readiness state, and finding counts.
    """
    blocker_count = sum(1 for f in findings if f.severity == Severity.BLOCKER)
    warning_count = sum(1 for f in findings if f.severity == Severity.WARNING)
    info_count = sum(1 for f in findings if f.severity == Severity.INFO)

    raw_score = 100 - (blocker_count * _BLOCKER_DEDUCTION) - (warning_count * _WARNING_DEDUCTION)
    score = max(0, min(100, raw_score))

    return ReleaseScore(
        score=score,
        readiness=_readiness_from_score(score),
        blocker_count=blocker_count,
        warning_count=warning_count,
        info_count=info_count,
    )
