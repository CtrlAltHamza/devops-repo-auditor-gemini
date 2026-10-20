"""Updated tests for the agent loop — aligned with the current loop.py API."""

import pytest
from unittest.mock import patch, MagicMock

from agent_core.loop import TOOL_REGISTRY


def test_tool_registry_contains_all_tools():
    """All required inspection tools must be registered in TOOL_REGISTRY."""
    expected = {
        "list_repo_files",
        "read_file_content",
        "search_code",
        "list_commits",
        "check_file_exists",
    }
    assert expected.issubset(set(TOOL_REGISTRY.keys()))



def test_tool_registry_callables():
    """Every registered tool must be callable."""
    for name, fn in TOOL_REGISTRY.items():
        assert callable(fn), f"Tool '{name}' is not callable"


def test_list_repo_files_via_registry(tmp_path):
    """list_repo_files should return a non-empty file list for a non-empty dir."""
    (tmp_path / "main.py").write_text("print('hello')")
    result = TOOL_REGISTRY["list_repo_files"](repo_path=str(tmp_path))
    assert result["total"] >= 1
    assert any("main.py" in f for f in result["files"])


def test_check_file_exists_via_registry(tmp_path):
    """check_file_exists should detect a file that exists."""
    (tmp_path / ".gitignore").write_text("*.pyc")
    result = TOOL_REGISTRY["check_file_exists"](
        repo_path=str(tmp_path), relative_path=".gitignore"
    )
    assert result["exists"] is True


def test_check_file_missing_via_registry(tmp_path):
    """check_file_exists should return exists=False for missing files."""
    result = TOOL_REGISTRY["check_file_exists"](
        repo_path=str(tmp_path), relative_path="Dockerfile"
    )
    assert result["exists"] is False
