"""
Finding normalization for the BobShip Release Engine.

Converts raw, heterogeneous finding dicts (produced by subagents or MCP tools)
into the canonical :class:`Finding` dataclass.

Design principles
-----------------
* Deterministic – no LLM calls, no randomness.
* Non-lossy    – malformed fields are handled gracefully; the finding is kept
                  with a fallback value rather than silently dropped.
* Strict input – unknown severity strings are mapped to WARNING so the finding
                  is still visible and actionable.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .models import Finding, Severity

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Severity normalisation map
# ---------------------------------------------------------------------------

# Maps any reasonable variation a subagent might use to a canonical Severity.
_SEVERITY_ALIASES: Dict[str, Severity] = {
    # BLOCKER synonyms
    "blocker": Severity.BLOCKER,
    "critical": Severity.BLOCKER,
    "error": Severity.BLOCKER,
    "fatal": Severity.BLOCKER,
    "high": Severity.BLOCKER,
    # WARNING synonyms
    "warning": Severity.WARNING,
    "warn": Severity.WARNING,
    "medium": Severity.WARNING,
    "moderate": Severity.WARNING,
    "low": Severity.WARNING,
    # INFO synonyms
    "info": Severity.INFO,
    "information": Severity.INFO,
    "informational": Severity.INFO,
    "note": Severity.INFO,
    "notice": Severity.INFO,
    "suggestion": Severity.INFO,
}

# Known analysis source domains (used for normalisation of source field)
_KNOWN_SOURCES = {"test", "security", "api", "deployment", "documentation"}


def _normalize_severity(raw: Any) -> Severity:
    """
    Convert a raw severity value to a canonical :class:`Severity`.

    Falls back to WARNING (rather than dropping the finding) if the value
    cannot be mapped, and logs a warning for observability.
    """
    if isinstance(raw, Severity):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        logger.warning("Missing or non-string severity %r; defaulting to WARNING", raw)
        return Severity.WARNING
    mapped = _SEVERITY_ALIASES.get(raw.strip().lower())
    if mapped is None:
        logger.warning("Unknown severity %r; defaulting to WARNING", raw)
        return Severity.WARNING
    return mapped


def _normalize_source(raw: Any) -> str:
    """Lowercase and strip the source; keep it even if not in the known list."""
    if not isinstance(raw, str) or not raw.strip():
        return "unknown"
    normalized = raw.strip().lower()
    if normalized not in _KNOWN_SOURCES:
        logger.debug("Source %r is not a standard analysis domain", normalized)
    return normalized


def _safe_str(value: Any, field_name: str, fallback: str = "") -> str:
    """Return str(value) stripped, or fallback if missing/blank."""
    if value is None:
        return fallback
    result = str(value).strip()
    if not result:
        logger.debug("Empty value for field %r; using fallback %r", field_name, fallback)
        return fallback
    return result


def _safe_int_or_none(value: Any, field_name: str) -> Optional[int]:
    """Parse an integer (e.g. line number) or return None."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        logger.debug("Non-integer value %r for field %r; ignoring", value, field_name)
        return None


def normalize_finding(raw: Dict[str, Any]) -> Finding:
    """
    Normalize a single raw finding dict into a :class:`Finding`.

    Required raw keys
    -----------------
    At least one of ``title`` or ``message`` must be non-empty; everything
    else has a safe fallback.

    Parameters
    ----------
    raw : dict
        Raw finding as produced by a subagent or MCP tool.

    Returns
    -------
    Finding
        Canonical finding ready for scoring.

    Raises
    ------
    ValueError
        If the input is not a dict.
    """
    if not isinstance(raw, dict):
        raise ValueError(f"Expected a dict for raw finding, got {type(raw).__name__!r}")

    title = _safe_str(raw.get("title"), "title")
    message = _safe_str(raw.get("message"), "message", fallback=title)

    # If title is empty but message is not, copy message into title
    if not title and message:
        title = message

    if not title and not message:
        # Keep the finding but mark it as incomplete
        title = "(untitled finding)"
        logger.warning("Finding has neither title nor message: %r", raw)

    return Finding(
        source=_normalize_source(raw.get("source")),
        category=_safe_str(raw.get("category"), "category", fallback="general"),
        severity=_normalize_severity(raw.get("severity")),
        title=title,
        message=message,
        file_path=_safe_str(raw.get("file_path") or raw.get("file") or raw.get("path"), "file_path") or None,
        line=_safe_int_or_none(raw.get("line") or raw.get("line_number"), "line"),
        remediation=_safe_str(raw.get("remediation") or raw.get("recommendation"), "remediation") or None,
    )


def normalize_findings(raw_findings: List[Dict[str, Any]]) -> List[Finding]:
    """
    Normalize a list of raw finding dicts.

    Invalid entries are skipped with a logged error so that one bad finding
    does not abort the entire normalization pass.

    Parameters
    ----------
    raw_findings : list of dict
        Raw findings as returned by subagents or MCP tools.

    Returns
    -------
    list of Finding
        Normalized findings in the same order (excluding any that raised).
    """
    results: List[Finding] = []
    for i, raw in enumerate(raw_findings):
        try:
            results.append(normalize_finding(raw))
        except Exception as exc:  # noqa: BLE001
            logger.error("Skipping finding at index %d: %s", i, exc)
    return results
