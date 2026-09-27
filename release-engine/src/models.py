"""
Data models for the BobShip Release Engine.

All models use plain dataclasses so they are lightweight and easily serializable
to/from dicts (e.g. for JSON exchange with the MCP server layer).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import List, Optional


class Severity(str, Enum):
    """
    Canonical severity levels recognised by the Release Engine.

    BLOCKER  – must be resolved before release (counts against score heavily).
    WARNING  – should be resolved; release possible with acknowledgement.
    INFO     – informational; does not affect the release score.
    """

    BLOCKER = "BLOCKER"
    WARNING = "WARNING"
    INFO = "INFO"


class ReadinessState(str, Enum):
    """
    Release-readiness states as defined in
    .bob/skills/release-engineer/SKILL.md.

    Score bands:
        90–100  → READY
        75–89   → READY_WITH_WARNINGS
        50–74   → NOT_READY
        0–49    → BLOCKED
    """

    READY = "READY"
    READY_WITH_WARNINGS = "READY WITH WARNINGS"
    NOT_READY = "NOT READY"
    BLOCKED = "BLOCKED"


@dataclass
class Finding:
    """
    A single normalized release finding produced by any analysis source.

    Attributes
    ----------
    source      : Analysis source / subagent domain (e.g. "security", "test").
    category    : Sub-category within the source (e.g. "hardcoded-secret").
    severity    : Canonical severity level (BLOCKER | WARNING | INFO).
    title       : Short human-readable description of the finding.
    message     : Detailed explanation (may equal title if no extra detail).
    file_path   : Repository-relative file path where the issue was found.
    line        : Line number within the file (1-based, None if not applicable).
    remediation : Recommended action to resolve the finding.
    """

    source: str
    category: str
    severity: Severity
    title: str
    message: str = ""
    file_path: Optional[str] = None
    line: Optional[int] = None
    remediation: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["severity"] = self.severity.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Finding":
        data = dict(data)
        data["severity"] = Severity(data["severity"].upper())
        return cls(**data)


@dataclass
class ReleaseScore:
    """Computed scoring result for a set of findings."""

    score: int
    readiness: ReadinessState
    blocker_count: int
    warning_count: int
    info_count: int

    def to_dict(self) -> dict:
        d = asdict(self)
        d["readiness"] = self.readiness.value
        return d


@dataclass
class ReleaseReport:
    """Complete release report passed to the report generator."""

    score: ReleaseScore
    findings: List[Finding] = field(default_factory=list)
    repository: str = "unknown"
    generated_at: str = ""  # ISO-8601 UTC timestamp; populated by generator

    def to_dict(self) -> dict:
        return {
            "repository": self.repository,
            "generated_at": self.generated_at,
            "score": self.score.to_dict(),
            "findings": [f.to_dict() for f in self.findings],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)
