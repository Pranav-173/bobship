"""
MCP → Release Engine integration tests.

Uses real MCP JSON shapes (static in-process fixtures — no live server
required) to verify the full pipeline:

    MCP ToolResult / ReleaseSnapshot
            ↓  findings_from_tool_result / findings_from_snapshot
    raw finding dicts
            ↓  normalize_findings   (analyzer.py)
    List[Finding]
            ↓  score_findings       (scoring.py)
    ReleaseScore
            ↓  generate_report      (report_generator.py via __init__.py)
    Markdown

Tests are grouped by scenario:
    - MCP finding field mapping
    - Source injection (category → source mapping table)
    - Blocker/critical findings → BLOCKED score
    - Warning/medium/low findings → READY WITH WARNINGS
    - Pass/info-only findings → READY
    - release_snapshot (multi-tool, merged findings)
    - Malformed / unknown fields handled safely
    - Full end-to-end pipeline integration

STRICT rules honoured:
    * No existing Release Engine tests are touched.
    * No MCP files are touched.
    * No new external dependencies.
    * Scoring rules from SKILL.md are not changed.
"""

from __future__ import annotations

import os
import sys
import unittest
from typing import Any, Dict, List

# Allow running from repo root or from release-engine/
_HERE = os.path.dirname(__file__)
_ENGINE_ROOT = os.path.dirname(_HERE)  # release-engine/
if _ENGINE_ROOT not in sys.path:
    sys.path.insert(0, _ENGINE_ROOT)

from src.mcp_adapter import findings_from_tool_result, findings_from_snapshot, _map_source
from src.analyzer import normalize_findings
from src.scoring import score_findings
from src.models import Severity, ReadinessState
import src as engine


# ---------------------------------------------------------------------------
# Fixture helpers — produce dicts that match the real MCP ToolResult schema
# ---------------------------------------------------------------------------

def _mcp_finding(
    status: str = "pass",
    severity: str = "info",
    category: str = "testing",
    message: str = "A finding",
    file: str | None = None,
    line: int | None = None,
) -> Dict[str, Any]:
    """Minimal MCP Finding dict (matches findings.ts interface)."""
    f: Dict[str, Any] = {
        "status": status,
        "severity": severity,
        "category": category,
        "message": message,
    }
    if file is not None:
        f["file"] = file
    if line is not None:
        f["line"] = line
    return f


def _tool_result(
    tool: str,
    target: str,
    findings: List[Dict[str, Any]],
    summary: str = "auto",
) -> Dict[str, Any]:
    """Minimal MCP ToolResult dict (matches findings.ts ToolResult interface)."""
    counts = {"pass": 0, "warning": 0, "fail": 0, "info": 0}
    for f in findings:
        s = f.get("status", "info")
        if s in counts:
            counts[s] += 1
    return {
        "tool": tool,
        "target": target,
        "summary": summary,
        "findings": findings,
        "counts": counts,
    }


def _snapshot(
    target: str,
    findings: List[Dict[str, Any]],
    tools_run: List[str] | None = None,
) -> Dict[str, Any]:
    """Minimal ReleaseSnapshot dict (matches release-tools.ts interface)."""
    counts = {"pass": 0, "warning": 0, "fail": 0, "info": 0}
    for f in findings:
        s = f.get("status", "info")
        if s in counts:
            counts[s] += 1
    return {
        "tool": "release_snapshot",
        "target": target,
        "generatedAt": "2024-01-01T00:00:00.000Z",
        "findings": findings,
        "counts": counts,
        "toolsRun": tools_run or [],
        "summary": "test snapshot",
    }


# ===========================================================================
# 1.  MCP finding field mapping
# ===========================================================================

class TestFindingFieldMapping(unittest.TestCase):
    """Verify individual MCP Finding fields are correctly forwarded."""

    def test_message_copied_to_title(self):
        """MCP uses 'message'; engine prefers 'title' → adapter copies it."""
        tr = _tool_result("scan_secrets", ".", [
            _mcp_finding(status="fail", severity="critical",
                         category="security",
                         message="AWS key detected",
                         file="config.py", line=12),
        ])
        raw = findings_from_tool_result(tr)
        self.assertEqual(len(raw), 1)
        self.assertEqual(raw[0]["title"], "AWS key detected")
        self.assertEqual(raw[0]["message"], "AWS key detected")

    def test_file_field_preserved(self):
        tr = _tool_result("scan_secrets", ".", [
            _mcp_finding(file="backend/main.py", line=7),
        ])
        raw = findings_from_tool_result(tr)
        self.assertEqual(raw[0]["file"], "backend/main.py")
        self.assertEqual(raw[0]["line"], 7)

    def test_severity_preserved_exactly(self):
        """Severity must not be altered by the adapter."""
        for sev in ("critical", "high", "medium", "low", "info"):
            with self.subTest(severity=sev):
                tr = _tool_result("run_tests", ".", [_mcp_finding(severity=sev)])
                raw = findings_from_tool_result(tr)
                self.assertEqual(raw[0]["severity"], sev)

    def test_status_field_preserved(self):
        """status (pass/fail/warning/info) should pass through unchanged."""
        for st in ("pass", "fail", "warning", "info"):
            with self.subTest(status=st):
                tr = _tool_result("run_tests", ".", [_mcp_finding(status=st)])
                raw = findings_from_tool_result(tr)
                self.assertEqual(raw[0]["status"], st)

    def test_category_field_preserved(self):
        tr = _tool_result("inspect_docker", ".", [
            _mcp_finding(category="deployment"),
        ])
        raw = findings_from_tool_result(tr)
        self.assertEqual(raw[0]["category"], "deployment")

    def test_existing_title_not_overwritten(self):
        """If a finding already has a 'title' key, adapter must not touch it."""
        f = _mcp_finding(message="msg")
        f["title"] = "original title"
        tr = _tool_result("scan_secrets", ".", [f])
        raw = findings_from_tool_result(tr)
        self.assertEqual(raw[0]["title"], "original title")


# ===========================================================================
# 2.  Source injection via category → source mapping
# ===========================================================================

class TestSourceMapping(unittest.TestCase):
    """Verify the explicit category → source mapping table."""

    def test_testing_maps_to_test(self):
        self.assertEqual(_map_source("testing", "run_tests"), "test")

    def test_security_maps_to_security(self):
        self.assertEqual(_map_source("security", "scan_secrets"), "security")

    def test_api_maps_to_api(self):
        self.assertEqual(_map_source("api", "validate_openapi"), "api")

    def test_deployment_maps_to_deployment(self):
        self.assertEqual(_map_source("deployment", "inspect_docker"), "deployment")

    def test_documentation_maps_to_documentation(self):
        self.assertEqual(_map_source("documentation", "project_structure"), "documentation")

    def test_dependencies_maps_to_deployment(self):
        self.assertEqual(_map_source("dependencies", "dependency_check"), "deployment")

    def test_git_maps_to_deployment(self):
        self.assertEqual(_map_source("git", "git_diff"), "deployment")

    def test_structure_maps_to_documentation(self):
        self.assertEqual(_map_source("structure", "project_structure"), "documentation")

    def test_unknown_category_kept_verbatim(self):
        self.assertEqual(_map_source("custom-check", "some_tool"), "custom-check")

    def test_missing_category_falls_back_to_tool_name(self):
        self.assertEqual(_map_source(None, "my_tool"), "my_tool")
        self.assertEqual(_map_source("", "my_tool"), "my_tool")

    def test_missing_both_falls_back_to_unknown(self):
        self.assertEqual(_map_source(None, None), "unknown")
        self.assertEqual(_map_source("", ""), "unknown")

    def test_source_injected_in_adapted_finding(self):
        tr = _tool_result("inspect_docker", ".", [
            _mcp_finding(category="deployment"),
        ])
        raw = findings_from_tool_result(tr)
        self.assertEqual(raw[0]["source"], "deployment")

    def test_source_injected_for_security_category(self):
        tr = _tool_result("scan_secrets", ".", [
            _mcp_finding(category="security", severity="critical"),
        ])
        raw = findings_from_tool_result(tr)
        self.assertEqual(raw[0]["source"], "security")


# ===========================================================================
# 3.  Blocker / critical → BLOCKED score
# ===========================================================================

class TestBlockerFindings(unittest.TestCase):
    """Critical/high MCP findings must score as BLOCKED when enough pile up."""

    def _pipeline(self, tool_result_dict):
        raw = findings_from_tool_result(tool_result_dict)
        findings = normalize_findings(raw)
        return score_findings(findings)

    def test_critical_secret_produces_blocker_severity(self):
        tr = _tool_result("scan_secrets", ".", [
            _mcp_finding(status="fail", severity="critical",
                         category="security",
                         message="AWS Access Key ID detected",
                         file="backend/config.py", line=3),
        ])
        raw = findings_from_tool_result(tr)
        normalized = normalize_findings(raw)
        self.assertEqual(len(normalized), 1)
        self.assertEqual(normalized[0].severity, Severity.BLOCKER)

    def test_four_critical_findings_blocked(self):
        """4 BLOCKER findings → score 0 → BLOCKED (4 × 25 = 100 deducted)."""
        findings_list = [
            _mcp_finding(status="fail", severity="critical",
                         category="security", message=f"Secret #{i}")
            for i in range(4)
        ]
        tr = _tool_result("scan_secrets", ".", findings_list)
        result = self._pipeline(tr)
        self.assertEqual(result.score, 0)
        self.assertEqual(result.readiness, ReadinessState.BLOCKED)

    def test_three_critical_findings_blocked(self):
        """3 BLOCKERs → score 25 → BLOCKED (0–49 band)."""
        findings_list = [
            _mcp_finding(status="fail", severity="critical",
                         category="security", message=f"Critical #{i}")
            for i in range(3)
        ]
        tr = _tool_result("scan_secrets", ".", findings_list)
        result = self._pipeline(tr)
        self.assertEqual(result.score, 25)
        self.assertEqual(result.readiness, ReadinessState.BLOCKED)

    def test_high_severity_also_maps_to_blocker(self):
        """MCP 'high' → BLOCKER via alias map in analyzer.py."""
        tr = _tool_result("run_tests", ".", [
            _mcp_finding(status="fail", severity="high",
                         category="testing",
                         message="pytest: 3 failed, 1 passed"),
        ])
        raw = findings_from_tool_result(tr)
        normalized = normalize_findings(raw)
        self.assertEqual(normalized[0].severity, Severity.BLOCKER)

    def test_test_failure_critical_reduces_score(self):
        """
        Test suite failure (critical severity) maps to BLOCKER.
        1 BLOCKER → score 75 → READY WITH WARNINGS (not yet BLOCKED; BLOCKED
        requires score ≤ 49, i.e. ≥ 3 blockers with no warnings).
        """
        tr = _tool_result("run_tests", ".", [
            _mcp_finding(status="fail", severity="critical",
                         category="testing",
                         message="pytest: 5 passed, 2 failed"),
        ])
        result = self._pipeline(tr)
        self.assertEqual(result.blocker_count, 1)
        self.assertEqual(result.score, 75)
        self.assertEqual(result.readiness, ReadinessState.READY_WITH_WARNINGS)


# ===========================================================================
# 4.  Warning / medium / low → READY WITH WARNINGS
# ===========================================================================

class TestWarningFindings(unittest.TestCase):
    """Medium/low findings should produce READY WITH WARNINGS, not BLOCKED."""

    def _pipeline(self, tool_result_dict):
        raw = findings_from_tool_result(tool_result_dict)
        findings = normalize_findings(raw)
        return score_findings(findings)

    def test_medium_severity_maps_to_warning(self):
        tr = _tool_result("inspect_docker", ".", [
            _mcp_finding(status="warning", severity="medium",
                         category="deployment",
                         message="Dockerfile has no HEALTHCHECK instruction.",
                         file="Dockerfile"),
        ])
        raw = findings_from_tool_result(tr)
        normalized = normalize_findings(raw)
        self.assertEqual(normalized[0].severity, Severity.WARNING)

    def test_low_severity_maps_to_warning(self):
        tr = _tool_result("inspect_docker", ".", [
            _mcp_finding(status="warning", severity="low",
                         category="deployment",
                         message="Base image uses ':latest'.",
                         file="Dockerfile"),
        ])
        raw = findings_from_tool_result(tr)
        normalized = normalize_findings(raw)
        self.assertEqual(normalized[0].severity, Severity.WARNING)

    def test_three_medium_warnings_ready_with_warnings(self):
        """3 warnings → score 85 → READY WITH WARNINGS."""
        findings_list = [
            _mcp_finding(status="warning", severity="medium",
                         category="deployment", message=f"Warning #{i}")
            for i in range(3)
        ]
        tr = _tool_result("inspect_docker", ".", findings_list)
        result = self._pipeline(tr)
        self.assertEqual(result.score, 85)
        self.assertEqual(result.readiness, ReadinessState.READY_WITH_WARNINGS)

    def test_one_blocker_is_ready_with_warnings(self):
        """1 BLOCKER → score 75 → READY WITH WARNINGS (boundary)."""
        tr = _tool_result("scan_secrets", ".", [
            _mcp_finding(status="fail", severity="critical",
                         category="security",
                         message="Stripe live key detected"),
        ])
        result = self._pipeline(tr)
        self.assertEqual(result.score, 75)
        self.assertEqual(result.readiness, ReadinessState.READY_WITH_WARNINGS)

    def test_docker_warnings_ready_with_warnings(self):
        """Typical Docker inspection result (2 medium + 1 low) → READY WITH WARNINGS."""
        findings_list = [
            _mcp_finding(status="warning", severity="medium",
                         category="deployment",
                         message="Dockerfile has no HEALTHCHECK instruction.",
                         file="Dockerfile"),
            _mcp_finding(status="warning", severity="medium",
                         category="deployment",
                         message="Dockerfile does not set a non-root USER.",
                         file="Dockerfile"),
            _mcp_finding(status="warning", severity="low",
                         category="deployment",
                         message="Base image uses ':latest'.",
                         file="Dockerfile"),
        ]
        tr = _tool_result("inspect_docker", ".", findings_list)
        result = self._pipeline(tr)
        # 3 warnings × −5 = 85 → READY WITH WARNINGS
        self.assertEqual(result.score, 85)
        self.assertEqual(result.readiness, ReadinessState.READY_WITH_WARNINGS)

    def test_dependency_warnings(self):
        tr = _tool_result("dependency_check", ".", [
            _mcp_finding(status="warning", severity="medium",
                         category="dependencies",
                         message="No lockfile found.",
                         file="package.json"),
            _mcp_finding(status="warning", severity="medium",
                         category="dependencies",
                         message="'requests' has no version pin.",
                         file="requirements.txt"),
        ])
        result = self._pipeline(tr)
        self.assertEqual(result.warning_count, 2)
        # 2 warnings × −5 = 90 → READY (boundary)
        self.assertEqual(result.score, 90)
        self.assertEqual(result.readiness, ReadinessState.READY)


# ===========================================================================
# 5.  Clean / pass / info-only → READY
# ===========================================================================

class TestCleanFindings(unittest.TestCase):
    """Pass and info-only findings must not degrade the score below 100."""

    def _pipeline(self, tool_result_dict):
        raw = findings_from_tool_result(tool_result_dict)
        findings = normalize_findings(raw)
        return score_findings(findings)

    def test_pass_finding_does_not_affect_score(self):
        tr = _tool_result("scan_secrets", ".", [
            _mcp_finding(status="pass", severity="info",
                         category="security",
                         message="No obvious hardcoded secrets found."),
        ])
        result = self._pipeline(tr)
        self.assertEqual(result.score, 100)
        self.assertEqual(result.readiness, ReadinessState.READY)

    def test_info_finding_does_not_affect_score(self):
        tr = _tool_result("validate_openapi", ".", [
            _mcp_finding(status="info", severity="info",
                         category="api",
                         message="No OpenAPI spec file found — skipping."),
        ])
        result = self._pipeline(tr)
        self.assertEqual(result.score, 100)
        self.assertEqual(result.readiness, ReadinessState.READY)

    def test_mix_of_pass_and_info_is_ready(self):
        tr = _tool_result("run_tests", ".", [
            _mcp_finding(status="pass", severity="info",
                         category="testing",
                         message="pytest: 47 passed"),
            _mcp_finding(status="info", severity="info",
                         category="testing",
                         message="No coverage report found."),
        ])
        result = self._pipeline(tr)
        self.assertEqual(result.score, 100)
        self.assertEqual(result.readiness, ReadinessState.READY)

    def test_empty_findings_list_is_ready(self):
        tr = _tool_result("scan_secrets", ".", [])
        result = self._pipeline(tr)
        self.assertEqual(result.score, 100)
        self.assertEqual(result.readiness, ReadinessState.READY)


# ===========================================================================
# 6.  release_snapshot — multi-tool merged findings
# ===========================================================================

class TestReleaseSnapshot(unittest.TestCase):
    """
    Verify findings_from_snapshot correctly handles the ReleaseSnapshot
    envelope produced by the MCP release_snapshot tool, which merges
    findings from scan_secrets, inspect_docker, inspect_environment,
    validate_openapi, dependency_check, git_diff, and run_tests.
    """

    def _pipeline(self, snapshot_dict):
        raw = findings_from_snapshot(snapshot_dict)
        findings = normalize_findings(raw)
        return score_findings(findings)

    def test_clean_snapshot_is_ready(self):
        snap = _snapshot(".", [
            _mcp_finding(status="pass", severity="info",
                         category="security", message="No secrets found."),
            _mcp_finding(status="pass", severity="info",
                         category="deployment", message="HEALTHCHECK present."),
            _mcp_finding(status="pass", severity="info",
                         category="testing", message="pytest: 10 passed"),
        ], tools_run=["scan_secrets", "inspect_docker", "run_tests"])
        result = self._pipeline(snap)
        self.assertEqual(result.score, 100)
        self.assertEqual(result.readiness, ReadinessState.READY)

    def test_snapshot_with_blocker_is_blocked(self):
        snap = _snapshot(".", [
            _mcp_finding(status="fail", severity="critical",
                         category="security",
                         message="AWS Access Key ID detected",
                         file="backend/config.py", line=3),
            _mcp_finding(status="fail", severity="critical",
                         category="security",
                         message="Generic private key header detected",
                         file="certs/key.pem", line=1),
            _mcp_finding(status="fail", severity="critical",
                         category="security",
                         message="Stripe live secret key detected",
                         file="payments.py", line=9),
            _mcp_finding(status="fail", severity="critical",
                         category="testing",
                         message="pytest: 1 passed, 3 failed"),
        ], tools_run=["scan_secrets", "run_tests"])
        result = self._pipeline(snap)
        self.assertEqual(result.blocker_count, 4)
        self.assertEqual(result.score, 0)
        self.assertEqual(result.readiness, ReadinessState.BLOCKED)

    def test_snapshot_with_warnings_only(self):
        snap = _snapshot(".", [
            _mcp_finding(status="warning", severity="medium",
                         category="deployment",
                         message="No HEALTHCHECK in Dockerfile.", file="Dockerfile"),
            _mcp_finding(status="warning", severity="medium",
                         category="deployment",
                         message="Container runs as root.", file="Dockerfile"),
            _mcp_finding(status="warning", severity="low",
                         category="deployment",
                         message="Base image uses ':latest'.", file="Dockerfile"),
            _mcp_finding(status="warning", severity="medium",
                         category="dependencies",
                         message="No lockfile found.", file="package.json"),
        ], tools_run=["inspect_docker", "dependency_check"])
        result = self._pipeline(snap)
        self.assertEqual(result.warning_count, 4)
        # 4 × −5 = 80 → READY WITH WARNINGS
        self.assertEqual(result.score, 80)
        self.assertEqual(result.readiness, ReadinessState.READY_WITH_WARNINGS)

    def test_snapshot_multiple_tools_mixed_severity(self):
        """
        Realistic snapshot: 1 critical secret + 2 docker warnings + 3 info.
        Expected: 1 blocker (−25) + 2 warnings (−10) = 65 → NOT READY.
        """
        snap = _snapshot("sample-app", [
            # scan_secrets
            _mcp_finding(status="fail", severity="critical",
                         category="security",
                         message="Hardcoded secret/password/token assignment",
                         file="backend/config.py", line=8),
            # inspect_docker
            _mcp_finding(status="warning", severity="medium",
                         category="deployment",
                         message="Dockerfile has no HEALTHCHECK instruction.",
                         file="Dockerfile"),
            _mcp_finding(status="warning", severity="medium",
                         category="deployment",
                         message="Dockerfile does not set a non-root USER.",
                         file="Dockerfile"),
            # inspect_environment
            _mcp_finding(status="pass", severity="info",
                         category="deployment",
                         message="All referenced env vars are documented."),
            # validate_openapi
            _mcp_finding(status="info", severity="info",
                         category="api",
                         message="No OpenAPI spec found — skipping."),
            # run_tests
            _mcp_finding(status="pass", severity="info",
                         category="testing",
                         message="pytest: 12 passed"),
        ], tools_run=["scan_secrets", "inspect_docker", "inspect_environment",
                      "validate_openapi", "run_tests"])
        result = self._pipeline(snap)
        self.assertEqual(result.blocker_count, 1)
        self.assertEqual(result.warning_count, 2)
        self.assertEqual(result.score, 65)
        self.assertEqual(result.readiness, ReadinessState.NOT_READY)

    def test_snapshot_source_derived_from_category(self):
        """Source field must be injected from category for snapshot findings."""
        snap = _snapshot(".", [
            _mcp_finding(status="fail", severity="critical",
                         category="security",
                         message="Secret detected"),
            _mcp_finding(status="warning", severity="medium",
                         category="deployment",
                         message="No healthcheck"),
            _mcp_finding(status="pass", severity="info",
                         category="testing",
                         message="Tests passed"),
        ])
        raw = findings_from_snapshot(snap)
        sources = [r["source"] for r in raw]
        self.assertIn("security", sources)
        self.assertIn("deployment", sources)
        self.assertIn("test", sources)

    def test_snapshot_timedout_field_ignored_safely(self):
        """Extra ToolResult fields (timedOut, error) must not break parsing."""
        snap = _snapshot(".", [
            _mcp_finding(status="fail", severity="high",
                         category="testing",
                         message="pytest timed out"),
        ])
        snap["timedOut"] = True
        snap["error"] = "Process killed after 90000ms"
        # Should not raise
        raw = findings_from_snapshot(snap)
        self.assertEqual(len(raw), 1)

    def test_findings_from_snapshot_equals_findings_from_tool_result(self):
        """
        findings_from_snapshot is a thin wrapper — its output must equal
        findings_from_tool_result for the same payload.
        """
        snap = _snapshot(".", [
            _mcp_finding(status="warning", severity="medium",
                         category="dependencies", message="No lockfile."),
        ])
        from_snap = findings_from_snapshot(snap)
        from_tr = findings_from_tool_result(snap)
        self.assertEqual(from_snap, from_tr)


# ===========================================================================
# 7.  Malformed / unknown fields handled safely
# ===========================================================================

class TestMalformedInput(unittest.TestCase):
    """Adapter must never raise; it returns an empty list or skips bad entries."""

    def test_none_input_returns_empty(self):
        self.assertEqual(findings_from_tool_result(None), [])
        self.assertEqual(findings_from_snapshot(None), [])

    def test_string_input_returns_empty(self):
        self.assertEqual(findings_from_tool_result("not a dict"), [])
        self.assertEqual(findings_from_snapshot("not a dict"), [])

    def test_list_input_returns_empty(self):
        self.assertEqual(findings_from_tool_result([]), [])
        self.assertEqual(findings_from_snapshot([]), [])

    def test_missing_findings_key_returns_empty(self):
        tr = {"tool": "scan_secrets", "target": "."}  # no 'findings' key
        self.assertEqual(findings_from_tool_result(tr), [])

    def test_findings_not_a_list_returns_empty(self):
        tr = {"tool": "scan_secrets", "target": ".", "findings": "bad"}
        self.assertEqual(findings_from_tool_result(tr), [])

    def test_non_dict_finding_skipped(self):
        tr = _tool_result("scan_secrets", ".", [])
        tr["findings"] = [
            _mcp_finding(severity="critical", message="valid"),
            "this is not a dict",
            42,
            None,
            _mcp_finding(severity="medium", message="also valid"),
        ]
        raw = findings_from_tool_result(tr)
        # Only the two dict findings survive
        self.assertEqual(len(raw), 2)

    def test_unknown_severity_survives_normalization(self):
        """Unknown severity must not crash normalize_findings() — falls back to WARNING."""
        tr = _tool_result("scan_secrets", ".", [
            _mcp_finding(status="fail", severity="XYZZY",
                         category="security",
                         message="Unknown severity level finding"),
        ])
        raw = findings_from_tool_result(tr)
        normalized = normalize_findings(raw)
        self.assertEqual(len(normalized), 1)
        self.assertEqual(normalized[0].severity, Severity.WARNING)

    def test_missing_severity_falls_back_to_warning(self):
        f = _mcp_finding(message="no severity")
        del f["severity"]
        tr = _tool_result("scan_secrets", ".", [f])
        raw = findings_from_tool_result(tr)
        normalized = normalize_findings(raw)
        self.assertEqual(normalized[0].severity, Severity.WARNING)

    def test_missing_message_produces_untitled_finding(self):
        f: Dict[str, Any] = {"status": "fail", "severity": "high", "category": "security"}
        tr = _tool_result("scan_secrets", ".", [f])
        raw = findings_from_tool_result(tr)
        normalized = normalize_findings(raw)
        self.assertEqual(len(normalized), 1)
        self.assertEqual(normalized[0].title, "(untitled finding)")

    def test_unknown_extra_fields_are_harmless(self):
        """Extra keys in a finding must not affect normalization."""
        f = _mcp_finding(severity="critical", message="secret found")
        f["unknownFieldFromFutureVersion"] = "some value"
        f["another_extra"] = 99
        tr = _tool_result("scan_secrets", ".", [f])
        raw = findings_from_tool_result(tr)
        normalized = normalize_findings(raw)
        self.assertEqual(len(normalized), 1)
        self.assertEqual(normalized[0].severity, Severity.BLOCKER)

    def test_empty_tool_name_in_result(self):
        tr = {"tool": "", "target": ".", "findings": [
            _mcp_finding(severity="medium", category="deployment",
                         message="something"),
        ]}
        raw = findings_from_tool_result(tr)
        self.assertEqual(len(raw), 1)
        # source derived from category since tool name is empty
        self.assertEqual(raw[0]["source"], "deployment")

    def test_missing_tool_name_in_result(self):
        tr = {"target": ".", "findings": [
            _mcp_finding(severity="medium", category="api", message="something"),
        ]}
        raw = findings_from_tool_result(tr)
        self.assertEqual(raw[0]["source"], "api")


# ===========================================================================
# 8.  Full end-to-end pipeline integration
# ===========================================================================

class TestEndToEndPipeline(unittest.TestCase):
    """
    Verify the complete pipeline:
        MCP JSON → adapter → normalize → score → generate report
    for representative scenarios.
    """

    def _run(self, snapshot_dict):
        raw = findings_from_snapshot(snapshot_dict)
        findings = engine.normalize(raw)
        release_score = engine.score(findings)
        md = engine.generate(release_score, findings,
                             repository="test-repo", output_dir=False)
        return release_score, findings, md

    def test_clean_snapshot_end_to_end(self):
        snap = _snapshot(".", [
            _mcp_finding(status="pass", severity="info",
                         category="security", message="No secrets found."),
            _mcp_finding(status="pass", severity="info",
                         category="testing", message="pytest: 5 passed"),
        ])
        result, findings, md = self._run(snap)
        self.assertEqual(result.readiness, ReadinessState.READY)
        self.assertEqual(result.score, 100)
        self.assertIn("READY", md)
        self.assertNotIn("BLOCKED", md)
        self.assertIn("test-repo", md)

    def test_blocked_snapshot_end_to_end(self):
        """Critical secrets + test failures → BLOCKED report."""
        snap = _snapshot(".", [
            _mcp_finding(status="fail", severity="critical",
                         category="security",
                         message="AWS Access Key ID detected",
                         file="backend/config.py", line=3),
            _mcp_finding(status="fail", severity="critical",
                         category="security",
                         message="Private key header detected",
                         file="certs/key.pem", line=1),
            _mcp_finding(status="fail", severity="critical",
                         category="testing",
                         message="pytest: 2 failed"),
            _mcp_finding(status="fail", severity="critical",
                         category="testing",
                         message="npm test: 1 failed"),
        ])
        result, findings, md = self._run(snap)
        self.assertEqual(result.readiness, ReadinessState.BLOCKED)
        self.assertIn("BLOCKED", md)
        self.assertIn("## Blockers", md)
        self.assertIn("backend/config.py", md)

    def test_warnings_snapshot_end_to_end(self):
        """Warnings-only snapshot should produce READY WITH WARNINGS."""
        snap = _snapshot(".", [
            _mcp_finding(status="warning", severity="medium",
                         category="deployment",
                         message="No HEALTHCHECK in Dockerfile.", file="Dockerfile"),
            _mcp_finding(status="warning", severity="medium",
                         category="deployment",
                         message="Container runs as root.", file="Dockerfile"),
            _mcp_finding(status="warning", severity="low",
                         category="dependencies",
                         message="Base image uses ':latest'."),
        ])
        result, findings, md = self._run(snap)
        self.assertEqual(result.readiness, ReadinessState.READY_WITH_WARNINGS)
        self.assertIn("READY WITH WARNINGS", md)
        self.assertIn("## Warnings", md)

    def test_report_contains_file_path_from_mcp_finding(self):
        snap = _snapshot(".", [
            _mcp_finding(status="fail", severity="critical",
                         category="security",
                         message="Hardcoded secret assignment",
                         file="src/db.py", line=22),
        ])
        _, _, md = self._run(snap)
        self.assertIn("src/db.py", md)

    def test_multi_source_report_has_source_labels(self):
        snap = _snapshot(".", [
            _mcp_finding(status="fail", severity="critical",
                         category="security", message="Secret in code",
                         file="config.py"),
            _mcp_finding(status="warning", severity="medium",
                         category="deployment", message="No healthcheck"),
            _mcp_finding(status="warning", severity="medium",
                         category="testing", message="Coverage below 80%"),
        ])
        _, findings, md = self._run(snap)
        sources = {f.source for f in findings}
        self.assertIn("security", sources)
        self.assertIn("deployment", sources)
        self.assertIn("test", sources)

    def test_score_not_ready_scenario(self):
        """1 blocker + 2 warnings = 65 → NOT READY."""
        snap = _snapshot(".", [
            _mcp_finding(status="fail", severity="critical",
                         category="security", message="Secret detected"),
            _mcp_finding(status="warning", severity="medium",
                         category="deployment", message="No healthcheck"),
            _mcp_finding(status="warning", severity="medium",
                         category="deployment", message="Runs as root"),
        ])
        result, _, _ = self._run(snap)
        self.assertEqual(result.score, 65)
        self.assertEqual(result.readiness, ReadinessState.NOT_READY)


if __name__ == "__main__":
    unittest.main()
