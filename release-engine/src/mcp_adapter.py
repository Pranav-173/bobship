"""
MCP → Release Engine adapter.

Converts a ``ToolResult`` or ``ReleaseSnapshot`` JSON dict produced by the
BobShip MCP server into the list of raw finding dicts that
``normalize_findings()`` (analyzer.py) already consumes.

Design rules
------------
* Stateless and deterministic — no side effects, no randomness.
* No new dependencies — only the Python standard library.
* MCP severity values are preserved exactly; the existing alias map in
  analyzer.py handles the translation (critical/high → BLOCKER, etc.).
* ``source`` is injected using an explicit mapping from the MCP
  ``category`` field, falling back to the MCP tool name, then to
  ``"unknown"``.
* ``status: "pass"`` and ``status: "info"`` findings are included so the
  engine can count them as INFO (zero score impact) — no promotion logic.
* Only ``findings`` from the payload are extracted; ``counts`` and
  ``toolsRun`` metadata are ignored (the engine re-derives everything).
* Malformed or unexpected structures are handled gracefully; the adapter
  never raises for invalid input — it returns an empty list and logs a
  warning via the standard ``logging`` module.

Public API
----------
    from src.mcp_adapter import findings_from_tool_result
    from src.mcp_adapter import findings_from_snapshot

    raw = findings_from_tool_result(tool_result_dict)
    raw = findings_from_snapshot(snapshot_dict)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Explicit MCP category → Release Engine source mapping.
#
# MCP ``category`` values (from findings.ts):
#   "testing" | "security" | "api" | "deployment" |
#   "documentation" | "dependencies" | "git" | "structure"
#
# Release Engine ``source`` values (known in analyzer.py):
#   "test" | "security" | "api" | "deployment" | "documentation"
#
# Categories that have no exact engine counterpart are kept as-is so they
# remain visible in reports (the engine accepts any string as source).
# ---------------------------------------------------------------------------
_CATEGORY_TO_SOURCE: Dict[str, str] = {
    "testing": "test",
    "security": "security",
    "api": "api",
    "deployment": "deployment",
    "documentation": "documentation",
    "dependencies": "deployment",   # treated as a deployment concern
    "git": "deployment",            # git state is a deployment-readiness signal
    "structure": "documentation",   # project structure is a docs/quality signal
}


def _map_source(category: Any, tool_name: Any) -> str:
    """
    Derive the Release Engine ``source`` field from a finding's ``category``
    and the containing tool's name.

    Priority
    --------
    1. Explicit mapping from ``category`` via ``_CATEGORY_TO_SOURCE``.
    2. Lowercased tool name (stripped of underscores/hyphens) as a fallback.
    3. ``"unknown"`` if neither is usable.
    """
    if isinstance(category, str) and category.strip():
        mapped = _CATEGORY_TO_SOURCE.get(category.strip().lower())
        if mapped:
            return mapped
        # category present but not in the table — keep it verbatim
        return category.strip().lower()

    if isinstance(tool_name, str) and tool_name.strip():
        return tool_name.strip().lower()

    return "unknown"


def _adapt_finding(raw_finding: Any, tool_name: Optional[str]) -> Optional[Dict[str, Any]]:
    """
    Convert a single MCP Finding dict into a raw dict suitable for
    ``normalize_finding()``.

    Returns ``None`` (and logs a warning) if the input is not a dict.
    """
    if not isinstance(raw_finding, dict):
        logger.warning("Skipping non-dict MCP finding: %r", raw_finding)
        return None

    adapted: Dict[str, Any] = {}

    # Preserve all original fields so normalize_finding() can pick up
    # anything it already knows (file, line, category, severity, message …).
    adapted.update(raw_finding)

    # Inject ``source`` — the engine needs this; MCP findings don't have it.
    adapted["source"] = _map_source(raw_finding.get("category"), tool_name)

    # MCP uses ``message``; the engine looks for ``title`` first, then
    # ``message``.  Copy ``message`` → ``title`` if ``title`` is absent so
    # the report shows a meaningful one-liner.
    if not adapted.get("title") and adapted.get("message"):
        adapted["title"] = adapted["message"]

    return adapted


def findings_from_tool_result(tool_result: Any) -> List[Dict[str, Any]]:
    """
    Extract and adapt findings from a single MCP ``ToolResult`` dict.

    Parameters
    ----------
    tool_result : dict
        The JSON-decoded payload returned by any individual MCP tool
        (scan_secrets, inspect_docker, run_tests, etc.).

    Returns
    -------
    list of dict
        Raw finding dicts ready for ``normalize_findings()``.
        Returns an empty list if the input is missing or malformed.
    """
    if not isinstance(tool_result, dict):
        logger.warning("findings_from_tool_result: expected dict, got %s", type(tool_result).__name__)
        return []

    tool_name: Optional[str] = tool_result.get("tool")
    raw_findings = tool_result.get("findings")

    if not isinstance(raw_findings, list):
        logger.warning("findings_from_tool_result: 'findings' key missing or not a list in tool=%r", tool_name)
        return []

    adapted = []
    for item in raw_findings:
        result = _adapt_finding(item, tool_name)
        if result is not None:
            adapted.append(result)

    return adapted


def findings_from_snapshot(snapshot: Any) -> List[Dict[str, Any]]:
    """
    Extract and adapt findings from a ``ReleaseSnapshot`` dict — the output
    of the MCP ``release_snapshot`` tool.

    The snapshot already merges findings from every sub-tool into a single
    ``findings`` array.  The individual tool name is not preserved per
    finding in the snapshot, so ``source`` is derived purely from each
    finding's ``category``.

    Parameters
    ----------
    snapshot : dict
        The JSON-decoded payload returned by the ``release_snapshot`` MCP
        tool.

    Returns
    -------
    list of dict
        Raw finding dicts ready for ``normalize_findings()``.
        Returns an empty list if the input is missing or malformed.
    """
    if not isinstance(snapshot, dict):
        logger.warning("findings_from_snapshot: expected dict, got %s", type(snapshot).__name__)
        return []

    # Treat the snapshot like a ToolResult — same shape for the fields we use.
    return findings_from_tool_result(snapshot)
