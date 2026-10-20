import os
import pytest
import subprocess
from pathlib import Path
from tools import list_files, read_file, search_code, git_log, git_status, _resolve_safe_path


@pytest.fixture
def mock_repo(tmp_path):
    """
    Creates a temporary mock Git repository with realistic DevOps files.
    """
    repo = tmp_path / "mock_repo"
    repo.mkdir()

    # Create dummy files
    (repo / "README.md").write_text("# Mock Project\nWelcome to mock project.\n")
    (repo / ".gitignore").write_text("*.pyc\n__pycache__/\n")
    
    src = repo / "src"
    src.mkdir()
    (src / "app.py").write_text("import os\n\nAPI_KEY = 'secret123'\nprint('Hello world')\n")
    (src / "data.bin").write_bytes(b"\x00\x01\x02\x03\x04\xff")

    # Initialize git repo so git_log and git_status work
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit with app and readme"], cwd=repo, capture_output=True, check=True)

    return repo


def test_list_files(mock_repo):
    res = list_files(str(mock_repo))
    assert not res.get("error")
    assert "README.md" in res["files"]
    assert "src/app.py" in res["files"]
    assert res["count"] >= 3


def test_read_file(mock_repo):
    res = read_file(str(mock_repo), "src/app.py", start_line=1, end_line=4)
    assert not res.get("error")
    assert res["file"] == "src/app.py"
    assert "   1 | import os" in res["content"]
    assert "API_KEY" in res["content"]


def test_read_file_binary(mock_repo):
    res = read_file(str(mock_repo), "src/data.bin")
    assert "error" in res
    assert "binary" in res["error"]


def test_read_file_nonexistent(mock_repo):
    res = read_file(str(mock_repo), "does_not_exist.txt")
    assert "error" in res
    assert "does not exist" in res["error"]


def test_path_traversal_protection(mock_repo):
    with pytest.raises(PermissionError):
        _resolve_safe_path(str(mock_repo), "../../etc/passwd")


def test_search_code(mock_repo):
    res = search_code(str(mock_repo), r"API_KEY\s*=")
    assert not res.get("error")
    assert len(res["matches"]) >= 1
    match = res["matches"][0]
    assert match["file"] == "src/app.py"
    assert match["line"] == 3


def test_git_log(mock_repo):
    res = git_log(str(mock_repo), max_commits=5)
    assert not res.get("error")
    assert res["count"] >= 1
    assert "Initial commit" in res["commits"][0]["message"]


def test_git_status(mock_repo):
    res = git_status(str(mock_repo))
    assert not res.get("error")
    assert res["untracked_or_modified_count"] == 0
