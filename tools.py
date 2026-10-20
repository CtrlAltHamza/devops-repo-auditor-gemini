import os
import re
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional
from agent_core.logger import get_logger, SecretScrubbingFilter

logger = get_logger("tools")

# File extensions generally considered binary or non-textual
BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".tar", ".gz",
    ".whl", ".pyc", ".pyd", ".so", ".dll", ".exe", ".bin", ".woff", ".woff2",
    ".ttf", ".eot", ".mp4", ".mp3", ".lockb"
}

# Directories to ignore during discovery to save LLM context
IGNORED_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", ".pytest_cache", ".tox"}


def _resolve_safe_path(repo_path: str, target_path: str) -> Path:
    """
    Prevents directory traversal attacks by ensuring the resolved target
    resides strictly inside repo_path.
    """
    repo = Path(repo_path).resolve()
    target = (repo / target_path).resolve()
    if not str(target).startswith(str(repo)):
        raise PermissionError(f"Access denied: Path '{target_path}' attempts to traverse outside repository.")
    return target


def list_files(repo_path: str, sub_dir: str = "", max_depth: int = 4, max_files: int = 250) -> Dict[str, Any]:
    """
    Discovers repository files and directory structure.

    Args:
        repo_path: Path to the root of the cloned repository.
        sub_dir: Optional sub-directory to list relative to root.
        max_depth: Maximum directory recursion depth (default 4).
        max_files: Maximum number of files to return (default 250).

    Returns:
        Dictionary with files list, total count, and structure summary.
    """
    try:
        base_dir = _resolve_safe_path(repo_path, sub_dir)
        if not base_dir.exists():
            return {"error": f"Directory not found: '{sub_dir}'"}

        file_list: List[str] = []
        base_depth = len(base_dir.parts)

        for root, dirs, files in os.walk(base_dir):
            # Prune ignored directories in-place
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]

            current_depth = len(Path(root).parts) - base_depth
            if current_depth >= max_depth:
                dirs.clear()
                continue

            for f in files:
                rel_path = os.path.relpath(os.path.join(root, f), repo_path).replace("\\", "/")
                file_list.append(rel_path)
                if len(file_list) >= max_files:
                    return {
                        "files": file_list,
                        "count": len(file_list),
                        "truncated": True,
                        "message": f"Truncated at {max_files} files."
                    }

        return {
            "files": file_list,
            "count": len(file_list),
            "truncated": False
        }
    except Exception as e:
        logger.error(f"Error listing files: {e}")
        return {"error": str(e)}


def read_file(repo_path: str, file_path: str, start_line: int = 1, end_line: int = 150) -> Dict[str, Any]:
    """
    Reads relevant source code or configuration with line numbers.

    Args:
        repo_path: Root repository directory.
        file_path: Relative path to the file.
        start_line: 1-indexed starting line number (default: 1).
        end_line: 1-indexed ending line number (default: 150).

    Returns:
        Dictionary with line-numbered content and metadata.
    """
    try:
        target = _resolve_safe_path(repo_path, file_path)
        if not target.exists():
            return {"error": f"File does not exist: {file_path}"}
        if target.is_dir():
            return {"error": f"Target is a directory, not a file: {file_path}"}

        if target.suffix.lower() in BINARY_EXTENSIONS:
            return {"error": f"File '{file_path}' is binary and cannot be read as text."}

        # Attempt UTF-8 read, fallback to latin-1
        try:
            with open(target, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except UnicodeDecodeError:
            with open(target, "r", encoding="latin-1") as f:
                lines = f.readlines()

        total_lines = len(lines)
        start_idx = max(1, start_line) - 1
        end_idx = min(total_lines, max(start_line, end_line))

        selected = lines[start_idx:end_idx]
        formatted_lines = [
            f"{i + start_idx + 1:4d} | {SecretScrubbingFilter.scrub(line.rstrip())}"
            for i, line in enumerate(selected)
        ]

        return {
            "file": file_path,
            "total_lines": total_lines,
            "start_line": start_idx + 1,
            "end_line": end_idx,
            "content": "\n".join(formatted_lines)
        }
    except Exception as e:
        logger.error(f"Error reading file {file_path}: {e}")
        return {"error": str(e)}


def search_code(repo_path: str, pattern: str, file_pattern: str = "") -> Dict[str, Any]:
    """
    Searches repository files for suspicious patterns, secrets, or configuration directives.

    Args:
        repo_path: Root repository directory.
        pattern: Regular expression or substring to search for.
        file_pattern: Optional file name glob (e.g. '*.yml', '*.py', 'Dockerfile').

    Returns:
        List of matches with file, line number, and redacted snippet.
    """
    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        return {"error": f"Invalid regex pattern '{pattern}': {e}"}

    matches = []
    base_dir = Path(repo_path).resolve()

    try:
        for root, dirs, files in os.walk(base_dir):
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]

            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in BINARY_EXTENSIONS:
                    continue

                if file_pattern and not re.search(file_pattern.replace("*", ".*"), file, re.IGNORECASE):
                    continue

                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, repo_path).replace("\\", "/")

                try:
                    with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                        for idx, line in enumerate(f, start=1):
                            if regex.search(line):
                                clean_line = SecretScrubbingFilter.scrub(line.strip())
                                matches.append({
                                    "file": rel_path,
                                    "line": idx,
                                    "match": clean_line[:180]
                                })
                                if len(matches) >= 50:
                                    return {
                                        "matches": matches,
                                        "truncated": True,
                                        "message": "Truncated at 50 matches."
                                    }
                except Exception:
                    continue

        return {"matches": matches, "count": len(matches), "truncated": False}
    except Exception as e:
        logger.error(f"Error searching code: {e}")
        return {"error": str(e)}


def git_log(repo_path: str, max_commits: int = 15) -> Dict[str, Any]:
    """
    Inspects recent commit history for commit hygiene, suspicious commit messages,
    or accidental credential leaks.

    Args:
        repo_path: Root repository directory.
        max_commits: Number of recent commits to retrieve (default: 15).

    Returns:
        Formatted commit list with hash, author, date, and commit subject.
    """
    try:
        cmd = [
            "git", "log", f"-n{max_commits}",
            "--pretty=format:%h|||%an|||%ad|||%s",
            "--date=short"
        ]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            return {"error": result.stderr.strip() or "Failed to run git log"}

        commits = []
        for line in result.stdout.strip().splitlines():
            if not line:
                continue
            parts = line.split("|||")
            if len(parts) == 4:
                commits.append({
                    "commit": parts[0],
                    "author": parts[1],
                    "date": parts[2],
                    "message": SecretScrubbingFilter.scrub(parts[3])
                })

        return {"commits": commits, "count": len(commits)}
    except Exception as e:
        logger.error(f"Error getting git log: {e}")
        return {"error": str(e)}


def git_status(repo_path: str) -> Dict[str, Any]:
    """
    Checks git status for untracked artifacts, temporary files, or uncommitted changes.
    """
    try:
        cmd = ["git", "status", "--porcelain"]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, timeout=10)
        lines = result.stdout.strip().splitlines()
        return {
            "untracked_or_modified_count": len(lines),
            "entries": lines[:20]
        }
    except Exception as e:
        logger.error(f"Error getting git status: {e}")
        return {"error": str(e)}
