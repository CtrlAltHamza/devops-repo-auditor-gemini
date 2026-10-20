import pytest
from unittest.mock import MagicMock
from agent_core.loop import dispatch_tool, sanitize_report
from agent_core.schema import AuditReport, Violation


def test_dispatch_tool_list_files(tmp_path):
    (tmp_path / "file1.txt").write_text("hello")
    res = dispatch_tool("list_files", {"max_depth": 2}, str(tmp_path))
    assert not res.get("error")
    assert "file1.txt" in res["files"]


def test_dispatch_tool_unknown(tmp_path):
    res = dispatch_tool("nonexistent_tool", {}, str(tmp_path))
    assert "error" in res
    assert "Unknown tool" in res["error"]


def test_sanitize_report_deduplication():
    v1 = Violation(
        rule_id="SEC-001",
        category="security",
        severity="critical",
        file="app.py",
        line=10,
        description="Hardcoded password",
        evidence="password = '***[REDACTED_SECRET]***'",
        recommendation="Use env var"
    )
    v2 = Violation(
        rule_id="SEC-001",
        category="security",
        severity="critical",
        file="app.py",
        line=10,
        description="Duplicate finding",
        evidence="password = '***[REDACTED_SECRET]***'",
        recommendation="Use env var"
    )
    report = AuditReport(
        repository="https://github.com/test/repo",
        violations=[v1, v2]
    )
    sanitized = sanitize_report(report, "https://github.com/test/repo")
    assert len(sanitized.violations) == 1


def test_sanitize_report_secret_scrubbing():
    v = Violation(
        rule_id="SEC-001",
        category="security",
        severity="critical",
        file="config.py",
        line=5,
        description="Found token ghp_1234567890abcdef1234567890abcdef1234",
        evidence="api_key = 'ghp_1234567890abcdef1234567890abcdef1234'",
        recommendation="Remove credential"
    )
    report = AuditReport(
        repository="https://github.com/test/repo",
        violations=[v]
    )
    sanitized = sanitize_report(report, "https://github.com/test/repo")
    assert "ghp_1234567890abcdef1234567890abcdef1234" not in sanitized.violations[0].description
    assert "ghp_1234567890abcdef1234567890abcdef1234" not in sanitized.violations[0].evidence
    assert "[REDACTED_SECRET]" in sanitized.violations[0].evidence
