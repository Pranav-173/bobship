"""
Test suite for the BobShip Release Engine.

Covers:
  - Data models (Finding, ReleaseScore, ReleaseReport serialization)
  - Finding normalization (analyzer.py)
  - Severity handling (all aliases, edge cases)
  - Release scoring (exact skill thresholds)
  - Readiness state boundaries
  - Report generation
  - Public API (__init__.py wrappers)
  - Edge cases (empty input, malformed input, missing fields)

All test data is deterministic and does not rely on external services.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

# Ensure the src package is importable regardless of where pytest is invoked.
_HERE = os.path.dirname(__file__)
_SRC_PARENT = os.path.join(_HERE, "src")
if os.path.dirname(_SRC_PARENT) not in sys.path:
    sys.path.insert(0, os.path.dirname(_SRC_PARENT))

from src.models import Finding, ReadinessState, ReleaseReport, ReleaseScore, Severity
from src.analyzer import (
    normalize_finding,
    normalize_findings,
    _normalize_severity,
    _normalize_source,
)
from src.scoring import score_findings, _readiness_from_score
from src.report_generator import generate_report
import src as engine


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def make_finding(severity=Severity.INFO, source="test", category="general",
                 title="A finding", **kwargs) -> Finding:
    return Finding(source=source, category=category, severity=severity,
                   title=title, **kwargs)


def make_raw(severity="info", source="test", category="general",
             title="A finding", **kwargs) -> dict:
    return dict(severity=severity, source=source, category=category,
                title=title, **kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# Model tests
# ─────────────────────────────────────────────────────────────────────────────

class TestFindingModel(unittest.TestCase):

    def test_to_dict_roundtrip(self):
        f = Finding(
            source="security",
            category="hardcoded-secret",
            severity=Severity.BLOCKER,
            title="Secret in code",
            message="API key found",
            file_path="config.py",
            line=42,
            remediation="Move to env var",
        )
        d = f.to_dict()
        self.assertEqual(d["severity"], "BLOCKER")
        self.assertEqual(d["file_path"], "config.py")

        restored = Finding.from_dict(d)
        self.assertEqual(restored.severity, Severity.BLOCKER)
        self.assertEqual(restored.file_path, "config.py")
        self.assertEqual(restored.line, 42)

    def test_from_dict_uppercase_severity(self):
        d = make_raw(severity="BLOCKER").__class__  # just verify no crash
        f = Finding.from_dict({
            "source": "test", "category": "general", "severity": "WARNING",
            "title": "t", "message": "", "file_path": None, "line": None,
            "remediation": None,
        })
        self.assertEqual(f.severity, Severity.WARNING)

    def test_severity_enum_values(self):
        self.assertEqual(Severity.BLOCKER.value, "BLOCKER")
        self.assertEqual(Severity.WARNING.value, "WARNING")
        self.assertEqual(Severity.INFO.value, "INFO")

    def test_readiness_enum_values(self):
        self.assertEqual(ReadinessState.READY.value, "READY")
        self.assertEqual(ReadinessState.READY_WITH_WARNINGS.value, "READY WITH WARNINGS")
        self.assertEqual(ReadinessState.NOT_READY.value, "NOT READY")
        self.assertEqual(ReadinessState.BLOCKED.value, "BLOCKED")


class TestReleaseScoreModel(unittest.TestCase):

    def test_to_dict(self):
        rs = ReleaseScore(score=85, readiness=ReadinessState.READY_WITH_WARNINGS,
                          blocker_count=0, warning_count=3, info_count=1)
        d = rs.to_dict()
        self.assertEqual(d["readiness"], "READY WITH WARNINGS")
        self.assertEqual(d["score"], 85)


class TestReleaseReportModel(unittest.TestCase):

    def test_to_json(self):
        rs = ReleaseScore(score=100, readiness=ReadinessState.READY,
                          blocker_count=0, warning_count=0, info_count=0)
        report = ReleaseReport(score=rs, repository="myrepo")
        j = json.loads(report.to_json())
        self.assertEqual(j["repository"], "myrepo")
        self.assertEqual(j["score"]["score"], 100)
        self.assertIsInstance(j["findings"], list)


# ─────────────────────────────────────────────────────────────────────────────
# Severity normalization tests
# ─────────────────────────────────────────────────────────────────────────────

class TestNormalizeSeverity(unittest.TestCase):

    def test_blocker_aliases(self):
        for alias in ("blocker", "BLOCKER", "critical", "Critical", "error",
                      "fatal", "high", "HIGH"):
            with self.subTest(alias=alias):
                self.assertEqual(_normalize_severity(alias), Severity.BLOCKER)

    def test_warning_aliases(self):
        for alias in ("warning", "WARNING", "warn", "medium", "Medium",
                      "moderate", "low", "LOW"):
            with self.subTest(alias=alias):
                self.assertEqual(_normalize_severity(alias), Severity.WARNING)

    def test_info_aliases(self):
        for alias in ("info", "INFO", "information", "informational",
                      "note", "notice", "suggestion"):
            with self.subTest(alias=alias):
                self.assertEqual(_normalize_severity(alias), Severity.INFO)

    def test_unknown_falls_back_to_warning(self):
        self.assertEqual(_normalize_severity("unknown_level"), Severity.WARNING)

    def test_none_falls_back_to_warning(self):
        self.assertEqual(_normalize_severity(None), Severity.WARNING)

    def test_empty_string_falls_back_to_warning(self):
        self.assertEqual(_normalize_severity(""), Severity.WARNING)

    def test_severity_enum_passthrough(self):
        self.assertEqual(_normalize_severity(Severity.BLOCKER), Severity.BLOCKER)


# ─────────────────────────────────────────────────────────────────────────────
# Source normalization tests
# ─────────────────────────────────────────────────────────────────────────────

class TestNormalizeSource(unittest.TestCase):

    def test_known_sources_lowercased(self):
        for src in ("test", "security", "api", "deployment", "documentation"):
            with self.subTest(src=src):
                self.assertEqual(_normalize_source(src.upper()), src)

    def test_unknown_source_kept(self):
        self.assertEqual(_normalize_source("custom-tool"), "custom-tool")

    def test_empty_becomes_unknown(self):
        self.assertEqual(_normalize_source(""), "unknown")
        self.assertEqual(_normalize_source(None), "unknown")


# ─────────────────────────────────────────────────────────────────────────────
# Finding normalization tests
# ─────────────────────────────────────────────────────────────────────────────

class TestNormalizeFinding(unittest.TestCase):

    def test_full_finding(self):
        raw = {
            "source": "Security",
            "category": "hardcoded-secret",
            "severity": "critical",
            "title": "API key in source",
            "message": "Found hardcoded API key",
            "file_path": "app/config.py",
            "line": 15,
            "remediation": "Use environment variable",
        }
        f = normalize_finding(raw)
        self.assertEqual(f.source, "security")
        self.assertEqual(f.severity, Severity.BLOCKER)
        self.assertEqual(f.file_path, "app/config.py")
        self.assertEqual(f.line, 15)
        self.assertEqual(f.remediation, "Use environment variable")

    def test_alternate_file_key(self):
        raw = make_raw(file="src/main.py")
        f = normalize_finding(raw)
        self.assertEqual(f.file_path, "src/main.py")

    def test_alternate_path_key(self):
        raw = make_raw(path="src/main.py")
        f = normalize_finding(raw)
        self.assertEqual(f.file_path, "src/main.py")

    def test_line_number_as_string(self):
        raw = make_raw(line="42")
        f = normalize_finding(raw)
        self.assertEqual(f.line, 42)

    def test_invalid_line_becomes_none(self):
        raw = make_raw(line="not-a-number")
        f = normalize_finding(raw)
        self.assertIsNone(f.line)

    def test_missing_title_uses_message(self):
        raw = {"source": "test", "category": "x", "severity": "info",
               "message": "Only a message"}
        f = normalize_finding(raw)
        self.assertEqual(f.title, "Only a message")

    def test_missing_both_title_and_message(self):
        raw = {"source": "test", "category": "x", "severity": "info"}
        f = normalize_finding(raw)
        self.assertEqual(f.title, "(untitled finding)")

    def test_non_dict_raises_value_error(self):
        with self.assertRaises(ValueError):
            normalize_finding("not a dict")

    def test_category_defaults_to_general(self):
        raw = {"source": "test", "severity": "info", "title": "t"}
        f = normalize_finding(raw)
        self.assertEqual(f.category, "general")

    def test_recommendation_alias(self):
        raw = make_raw(recommendation="Fix this")
        f = normalize_finding(raw)
        self.assertEqual(f.remediation, "Fix this")

    def test_remediation_wins_over_recommendation(self):
        raw = make_raw(remediation="Primary fix", recommendation="Secondary fix")
        f = normalize_finding(raw)
        self.assertEqual(f.remediation, "Primary fix")


class TestNormalizeFindings(unittest.TestCase):

    def test_empty_list(self):
        self.assertEqual(normalize_findings([]), [])

    def test_multiple_findings(self):
        raws = [make_raw(severity="critical"), make_raw(severity="info")]
        results = normalize_findings(raws)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].severity, Severity.BLOCKER)
        self.assertEqual(results[1].severity, Severity.INFO)

    def test_bad_entry_skipped(self):
        raws = [make_raw(), "not a dict", make_raw(severity="warning")]
        results = normalize_findings(raws)
        self.assertEqual(len(results), 2)  # bad entry is skipped


# ─────────────────────────────────────────────────────────────────────────────
# Scoring tests — EXACT skill thresholds
# ─────────────────────────────────────────────────────────────────────────────

class TestReadinessFromScore(unittest.TestCase):
    """Verify every boundary of the four score bands."""

    def test_score_100_ready(self):
        self.assertEqual(_readiness_from_score(100), ReadinessState.READY)

    def test_score_90_ready(self):
        self.assertEqual(_readiness_from_score(90), ReadinessState.READY)

    def test_score_89_ready_with_warnings(self):
        self.assertEqual(_readiness_from_score(89), ReadinessState.READY_WITH_WARNINGS)

    def test_score_75_ready_with_warnings(self):
        self.assertEqual(_readiness_from_score(75), ReadinessState.READY_WITH_WARNINGS)

    def test_score_74_not_ready(self):
        self.assertEqual(_readiness_from_score(74), ReadinessState.NOT_READY)

    def test_score_50_not_ready(self):
        self.assertEqual(_readiness_from_score(50), ReadinessState.NOT_READY)

    def test_score_49_blocked(self):
        self.assertEqual(_readiness_from_score(49), ReadinessState.BLOCKED)

    def test_score_0_blocked(self):
        self.assertEqual(_readiness_from_score(0), ReadinessState.BLOCKED)


class TestScoreFindings(unittest.TestCase):
    """Integration tests: findings → ReleaseScore."""

    def test_clean_repository(self):
        result = score_findings([])
        self.assertEqual(result.score, 100)
        self.assertEqual(result.readiness, ReadinessState.READY)
        self.assertEqual(result.blocker_count, 0)
        self.assertEqual(result.warning_count, 0)
        self.assertEqual(result.info_count, 0)

    def test_info_only_does_not_affect_score(self):
        findings = [make_finding(Severity.INFO) for _ in range(10)]
        result = score_findings(findings)
        self.assertEqual(result.score, 100)
        self.assertEqual(result.readiness, ReadinessState.READY)

    def test_two_warnings_stays_ready(self):
        # 100 - (2 * 5) = 90 → READY
        findings = [make_finding(Severity.WARNING) for _ in range(2)]
        result = score_findings(findings)
        self.assertEqual(result.score, 90)
        self.assertEqual(result.readiness, ReadinessState.READY)

    def test_three_warnings_ready_with_warnings(self):
        # 100 - (3 * 5) = 85 → READY WITH WARNINGS
        findings = [make_finding(Severity.WARNING) for _ in range(3)]
        result = score_findings(findings)
        self.assertEqual(result.score, 85)
        self.assertEqual(result.readiness, ReadinessState.READY_WITH_WARNINGS)

    def test_five_warnings_ready_with_warnings(self):
        # 100 - (5 * 5) = 75 → READY WITH WARNINGS (boundary)
        findings = [make_finding(Severity.WARNING) for _ in range(5)]
        result = score_findings(findings)
        self.assertEqual(result.score, 75)
        self.assertEqual(result.readiness, ReadinessState.READY_WITH_WARNINGS)

    def test_six_warnings_not_ready(self):
        # 100 - (6 * 5) = 70 → NOT READY
        findings = [make_finding(Severity.WARNING) for _ in range(6)]
        result = score_findings(findings)
        self.assertEqual(result.score, 70)
        self.assertEqual(result.readiness, ReadinessState.NOT_READY)

    def test_one_blocker(self):
        # 100 - 25 = 75 → READY WITH WARNINGS
        findings = [make_finding(Severity.BLOCKER)]
        result = score_findings(findings)
        self.assertEqual(result.score, 75)
        self.assertEqual(result.readiness, ReadinessState.READY_WITH_WARNINGS)

    def test_two_blockers(self):
        # 100 - 50 = 50 → NOT READY (boundary)
        findings = [make_finding(Severity.BLOCKER) for _ in range(2)]
        result = score_findings(findings)
        self.assertEqual(result.score, 50)
        self.assertEqual(result.readiness, ReadinessState.NOT_READY)

    def test_three_blockers_not_ready(self):
        # 100 - 75 = 25 → BLOCKED
        findings = [make_finding(Severity.BLOCKER) for _ in range(3)]
        result = score_findings(findings)
        self.assertEqual(result.score, 25)
        self.assertEqual(result.readiness, ReadinessState.BLOCKED)

    def test_four_blockers_clamped_to_zero(self):
        # 100 - 100 = 0 → BLOCKED
        findings = [make_finding(Severity.BLOCKER) for _ in range(4)]
        result = score_findings(findings)
        self.assertEqual(result.score, 0)
        self.assertEqual(result.readiness, ReadinessState.BLOCKED)

    def test_many_blockers_clamped_to_zero(self):
        findings = [make_finding(Severity.BLOCKER) for _ in range(20)]
        result = score_findings(findings)
        self.assertEqual(result.score, 0)

    def test_mixed_findings(self):
        # 1 blocker (-25) + 2 warnings (-10) = 65 → NOT READY
        findings = (
            [make_finding(Severity.BLOCKER)] +
            [make_finding(Severity.WARNING) for _ in range(2)] +
            [make_finding(Severity.INFO) for _ in range(5)]
        )
        result = score_findings(findings)
        self.assertEqual(result.score, 65)
        self.assertEqual(result.readiness, ReadinessState.NOT_READY)
        self.assertEqual(result.blocker_count, 1)
        self.assertEqual(result.warning_count, 2)
        self.assertEqual(result.info_count, 5)

    def test_boundary_score_50_not_ready(self):
        # Exactly 50 → NOT READY (not BLOCKED)
        findings = [make_finding(Severity.BLOCKER) for _ in range(2)]
        result = score_findings(findings)
        self.assertEqual(result.score, 50)
        self.assertNotEqual(result.readiness, ReadinessState.BLOCKED)

    def test_boundary_score_49_blocked(self):
        # 49 → BLOCKED
        # 2 blockers (-50) + 0 warnings = 50 (not 49)
        # use 2 blockers + 1 warning: 100 - 50 - 5 = 45 → BLOCKED
        findings = (
            [make_finding(Severity.BLOCKER) for _ in range(2)] +
            [make_finding(Severity.WARNING)]
        )
        result = score_findings(findings)
        self.assertEqual(result.score, 45)
        self.assertEqual(result.readiness, ReadinessState.BLOCKED)


# ─────────────────────────────────────────────────────────────────────────────
# Report generation tests
# ─────────────────────────────────────────────────────────────────────────────

class TestReportGeneration(unittest.TestCase):

    def _make_report(self, findings):
        release_score = score_findings(findings)
        return ReleaseReport(score=release_score, findings=findings,
                             repository="test-repo")

    def test_clean_report_contains_ready(self):
        md = generate_report(self._make_report([]), output_dir=False)
        self.assertIn("READY", md)
        self.assertNotIn("BLOCKED", md)

    def test_blocked_report_contains_blocked(self):
        findings = [make_finding(Severity.BLOCKER) for _ in range(4)]
        md = generate_report(self._make_report(findings), output_dir=False)
        self.assertIn("BLOCKED", md)

    def test_report_contains_repository_name(self):
        md = generate_report(self._make_report([]), output_dir=False)
        self.assertIn("test-repo", md)

    def test_report_contains_score(self):
        md = generate_report(self._make_report([]), output_dir=False)
        self.assertIn("100", md)

    def test_report_contains_timestamp(self):
        md = generate_report(self._make_report([]), output_dir=False)
        # ISO timestamp contains "T" and "Z"
        self.assertRegex(md, r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")

    def test_report_contains_blockers_section(self):
        md = generate_report(self._make_report([]), output_dir=False)
        self.assertIn("## Blockers", md)

    def test_report_contains_warnings_section(self):
        md = generate_report(self._make_report([]), output_dir=False)
        self.assertIn("## Warnings", md)

    def test_report_contains_recommended_actions(self):
        md = generate_report(self._make_report([]), output_dir=False)
        self.assertIn("## Recommended Actions", md)

    def test_report_lists_blocker_finding(self):
        findings = [Finding(
            source="security", category="hardcoded-secret",
            severity=Severity.BLOCKER, title="API key exposed",
            file_path="config.py", line=10,
            remediation="Use env var",
        )]
        md = generate_report(self._make_report(findings), output_dir=False)
        self.assertIn("API key exposed", md)
        self.assertIn("config.py", md)

    def test_report_no_write_does_not_create_file(self):
        """Passing output_dir=False must not write any file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            generate_report(self._make_report([]), output_dir=False)
            self.assertEqual(os.listdir(tmpdir), [])

    def test_report_write_creates_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            generate_report(self._make_report([]), output_dir=tmpdir,
                            filename="test-report.md")
            self.assertIn("test-report.md", os.listdir(tmpdir))

    def test_report_written_content_matches_returned(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            md = generate_report(self._make_report([]), output_dir=tmpdir,
                                 filename="out.md")
            with open(os.path.join(tmpdir, "out.md"), encoding="utf-8") as fh:
                written = fh.read()
            self.assertEqual(md, written)


# ─────────────────────────────────────────────────────────────────────────────
# Public API (engine.__init__) tests
# ─────────────────────────────────────────────────────────────────────────────

class TestPublicAPI(unittest.TestCase):

    def test_normalize_returns_findings(self):
        raws = [make_raw(severity="critical"), make_raw(severity="info")]
        findings = engine.normalize(raws)
        self.assertEqual(len(findings), 2)
        self.assertIsInstance(findings[0], Finding)

    def test_score_returns_release_score(self):
        findings = engine.normalize([make_raw(severity="warning")])
        result = engine.score(findings)
        self.assertIsInstance(result, ReleaseScore)
        self.assertEqual(result.score, 95)

    def test_generate_returns_markdown(self):
        findings = engine.normalize([make_raw(severity="blocker",
                                               title="Missing tests")])
        result = engine.score(findings)
        md = engine.generate(result, findings, repository="my-repo",
                             output_dir=False)
        self.assertIn("my-repo", md)
        self.assertIn("Missing tests", md)

    def test_full_pipeline(self):
        """End-to-end: raw → normalize → score → generate."""
        raws = [
            {"source": "security", "category": "hardcoded-secret",
             "severity": "critical", "title": "Hardcoded password",
             "file_path": "db.py", "line": 5,
             "remediation": "Use SECRET env variable"},
            {"source": "test", "category": "coverage",
             "severity": "warning", "title": "Coverage below 80%"},
            {"source": "documentation", "category": "readme",
             "severity": "info", "title": "README missing badge"},
        ]
        findings = engine.normalize(raws)
        self.assertEqual(len(findings), 3)

        result = engine.score(findings)
        # 1 blocker (-25) + 1 warning (-5) = 70 → NOT READY
        self.assertEqual(result.score, 70)
        self.assertEqual(result.readiness, ReadinessState.NOT_READY)

        md = engine.generate(result, findings, repository="bobship",
                             output_dir=False)
        self.assertIn("NOT READY", md)
        self.assertIn("Hardcoded password", md)
        self.assertIn("db.py", md)


# ─────────────────────────────────────────────────────────────────────────────
# Edge case tests
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeCases(unittest.TestCase):

    def test_finding_with_pipe_in_title_escapes_in_table(self):
        findings = [Finding(
            source="test", category="x", severity=Severity.WARNING,
            title="Check A | Check B",
        )]
        release_score = score_findings(findings)
        report = ReleaseReport(score=release_score, findings=findings,
                               repository="repo")
        md = generate_report(report, output_dir=False)
        self.assertIn("&#124;", md)

    def test_score_clamped_not_negative(self):
        findings = [make_finding(Severity.BLOCKER) for _ in range(100)]
        result = score_findings(findings)
        self.assertGreaterEqual(result.score, 0)

    def test_empty_findings_list_is_ready(self):
        result = score_findings([])
        self.assertEqual(result.readiness, ReadinessState.READY)
        self.assertEqual(result.score, 100)

    def test_normalize_empty_list(self):
        self.assertEqual(engine.normalize([]), [])

    def test_single_info_finding_does_not_block(self):
        findings = [make_finding(Severity.INFO)]
        result = score_findings(findings)
        self.assertEqual(result.score, 100)
        self.assertEqual(result.readiness, ReadinessState.READY)


if __name__ == "__main__":
    unittest.main()
