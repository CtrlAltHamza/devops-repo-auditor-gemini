import json
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
