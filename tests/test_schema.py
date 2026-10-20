import pytest
from pydantic import ValidationError

from agent_core.schema import AuditReport, Violation


def test_valid_violation_and_report():
    raw_data = {
        "repository": "https://github.com/example/demo-project",
        "violations": [
            {
                "rule_id": "SEC-001",
                "category": "security",
                "severity": "critical",
                "file": "config.py",
                "line": 17,
                "description": "Hardcoded API credential",
                "evidence": "Credential assigned directly in source code",
                "recommendation": "Use a secrets manager or environment variable"
            }
        ]
    }
    report = AuditReport.model_validate(raw_data)
    assert report.repository == "https://github.com/example/demo-project"
    assert len(report.violations) == 1
    v = report.violations[0]
    assert v.rule_id == "SEC-001"
    assert v.severity == "critical"
    assert v.line == 17


def test_empty_violations_report():
    raw_data = {
        "repository": "https://github.com/example/healthy-project",
        "violations": []
    }
    report = AuditReport.model_validate(raw_data)
    assert len(report.violations) == 0


def test_violation_null_fields():
    raw_data = {
        "rule_id": "CI-001",
        "category": "github_actions_ci",
        "severity": "high",
        "file": None,
        "line": None,
        "description": "Missing automated CI test pipeline",
        "evidence": "No .github/workflows directory or CI configuration found",
        "recommendation": "Add a GitHub Actions workflow to run tests on push and PR"
    }
    v = Violation.model_validate(raw_data)
    assert v.file is None
    assert v.line is None


def test_invalid_severity():
    raw_data = {
        "rule_id": "HYG-001",
        "category": "repository_hygiene",
        "severity": "extreme",  # Invalid! Allowed: critical, high, medium, low
        "file": "README.md",
        "line": 1,
        "description": "Empty README",
        "evidence": "File has 0 bytes",
        "recommendation": "Add README"
    }
    with pytest.raises(ValidationError):
        Violation.model_validate(raw_data)


def test_violation_secret_scrubbing():
    """Ensure secrets in evidence, description, and recommendation are automatically masked."""
    raw_data = {
        "rule_id": "SEC-001",
        "category": "security",
        "severity": "critical",
        "file": "config.py",
        "line": 10,
        "description": "Found key",
        "evidence": "api_key = 'AIzaSyAH9hJmMgY19omF_SH7F5tispAWCIN2ync'",
        "recommendation": "Remove ghp_111122223333444455556666777788889999",
    }
    v = Violation.model_validate(raw_data)
    assert "AIzaSyAH9hJmMgY19omF_SH7F5tispAWCIN2ync" not in v.evidence
    assert "REDACTED_SECRET" in v.evidence
    assert "ghp_111122223333444455556666777788889999" not in v.recommendation
    assert "REDACTED_SECRET" in v.recommendation


def test_audit_report_deduplication():
    """Ensure duplicate findings with identical rule_id, file, and line are merged."""
    v1 = {
        "rule_id": "SEC-001",
        "category": "security",
        "severity": "critical",
        "file": "config.py",
        "line": 10,
        "description": "First instance",
        "evidence": "evidence 1",
        "recommendation": "rec 1",
    }
    v2 = {
        "rule_id": "SEC-001",
        "category": "security",
        "severity": "critical",
        "file": "config.py",
        "line": 10,
        "description": "Duplicate instance",
        "evidence": "evidence 2",
        "recommendation": "rec 2",
    }
    v3 = {
        "rule_id": "SEC-001",
        "category": "security",
        "severity": "critical",
        "file": "config.py",
        "line": 25,
        "description": "Different line instance",
        "evidence": "evidence 3",
        "recommendation": "rec 3",
    }
    report = AuditReport.model_validate({
        "repository": "https://github.com/example/repo",
        "violations": [v1, v2, v3],
    })
    assert len(report.violations) == 2

