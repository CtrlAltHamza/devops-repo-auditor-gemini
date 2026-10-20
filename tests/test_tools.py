"""Unit tests for the inspection tools module."""
import os
import tempfile
import pytest

from tools import (
    list_repo_files,
    read_file_content,
    search_code,
    list_commits,
    check_file_exists,
)


@pytest.fixture()
def sample_repo(tmp_path):
    """Create a minimal fake repository for testing."""
    # Create some files
    (tmp_path / "README.md").write_text("# Test Repo")
    (tmp_path / "main.py").write_text("import os\npassword = \'hardcoded\'\nprint(\'hello\')")
    (tmp_path / "requirements.txt").write_text("requests==2.31.0")
    subdir = tmp_path / "src"
    subdir.mkdir()
    (subdir / "app.py").write_text("# app module")
    return tmp_path


class TestListRepoFiles:
    def test_returns_files(self, sample_repo):
        result = list_repo_files(str(sample_repo))
        assert result["total"] >= 3
        assert any("README.md" in f for f in result["files"])

    def test_excludes_hidden(self, sample_repo):
        (sample_repo / ".secret").write_text("hidden")
        result = list_repo_files(str(sample_repo))
        assert not any(".secret" in f for f in result["files"])


class TestReadFileContent:
    def test_reads_file(self, sample_repo):
        result = read_file_content(str(sample_repo), "README.md")
        assert result["error"] is None
        assert "Test Repo" in result["content"]

    def test_missing_file(self, sample_repo):
        result = read_file_content(str(sample_repo), "nonexistent.txt")
        assert result["error"] == "File not found"

    def test_path_traversal_blocked(self, sample_repo):
        result = read_file_content(str(sample_repo), "../secret.txt")
        assert result["error"] is not None


class TestSearchCode:
    def test_finds_pattern(self, sample_repo):
        result = search_code(str(sample_repo), "password", "*.py")
        assert result["total"] >= 1
        assert any("main.py" in m["file"] for m in result["matches"])

    def test_no_match(self, sample_repo):
        result = search_code(str(sample_repo), "XYZNOTFOUND", "*.py")
        assert result["total"] == 0

    def test_invalid_regex(self, sample_repo):
        result = search_code(str(sample_repo), "[invalid")
        assert "error" in result


class TestCheckFileExists:
    def test_existing_file(self, sample_repo):
        result = check_file_exists(str(sample_repo), "requirements.txt")
        assert result["exists"] is True

    def test_missing_file(self, sample_repo):
        result = check_file_exists(str(sample_repo), "Dockerfile")
        assert result["exists"] is False
