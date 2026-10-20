"""End-to-end tests for the DevOps auditing agent and CLI invocation."""

import json
from unittest.mock import MagicMock, patch

from agent_core.loop import run_audit
from agent_core.schema import AuditReport


def test_audit_loop_observe_reason_report(tmp_path):
    """Simulate complete agent loop with mock Gemini client and tool execution."""
    # Create fake repository files
    (tmp_path / "README.md").write_text("# Test Repository")
    (tmp_path / ".gitignore").write_text("*.pyc\n__pycache__/")
    (tmp_path / "app.py").write_text("print('safe code')")

    mock_client = MagicMock()

    # Step 1: Model issues a tool call to list_repo_files
    tool_call_mock = MagicMock()
    tool_call_mock.name = "list_repo_files"
    tool_call_mock.args = {"repo_path": str(tmp_path)}

    part_mock = MagicMock()
    part_mock.__dict__ = {"text": "Listing files first"}
    cand_mock = MagicMock()
    cand_mock.content.parts = [part_mock]

    resp_tool_call = MagicMock()
    resp_tool_call.candidates = [cand_mock]

    # Step 2: Model returns final compliant JSON
    resp_final = MagicMock()
    final_json = {
        "repository": "https://github.com/mock/repo",
        "violations": [
            {
                "rule_id": "TEST-001",
                "category": "testing",
                "severity": "high",
                "file": None,
                "line": None,
                "description": "Missing test suite in repository",
                "evidence": "No tests/ directory discovered",
                "recommendation": "Add pytest test suite and CI validation",
            }
        ],
    }

    mock_client.generate.side_effect = [resp_tool_call, resp_final]
    mock_client.extract_tool_calls.side_effect = [[tool_call_mock], []]
    mock_client.parse_json_response.return_value = final_json

    with patch("agent_core.loop.GeminiClient", return_value=mock_client):
        report = run_audit("https://github.com/mock/repo", str(tmp_path))

    assert isinstance(report, AuditReport)
    assert report.repository == "https://github.com/mock/repo"
    assert len(report.violations) == 1
    assert report.violations[0].rule_id == "TEST-001"
    assert report.violations[0].category == "testing"


def test_cli_execution_with_flags(tmp_path, monkeypatch):
    """Test CLI execution using --repo and --output flags."""
    import agent

    output_file = tmp_path / "test_report.json"
    dummy_report = AuditReport(
        repository="https://github.com/mock/repo",
        violations=[],
    )

    monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")
    monkeypatch.setattr(
        "sys.argv",
        [
            "agent.py",
            "--repo",
            "https://github.com/mock/repo",
            "--output",
            str(output_file),
        ],
    )

    with (
        patch("agent.clone_repository") as mock_clone,
        patch("agent.run_audit", return_value=dummy_report),
    ):
        mock_clone.return_value.__enter__.return_value = str(tmp_path)
        exit_code = agent.main()

    assert exit_code == 0
    assert output_file.exists()
    saved = json.loads(output_file.read_text())
    assert saved["repository"] == "https://github.com/mock/repo"
    assert saved["violations"] == []
