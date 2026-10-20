"""
DevOps Audit Agent — Inspection Tools
All tools are pure‑Python, read‑only, sandboxed, and safe for use
with untrusted repository clones.
"""

import os
import re
import subprocess
from typing import Any
from agent_core.logger import get_logger
from agent_core.utils import safe_path_join

logger = get_logger("tools")


# ──────────────────────────────────────────────────────────────────
# 1. list_repo_files
# ──────────────────────────────────────────────────────────────────
def list_repo_files(repo_path: str, max_files: int = 500) -> dict[str, Any]:
    """Recursively list all non‑hidden files in *repo_path* (excluding .git/).

    Returns a dict with:
      - files: list of relative file paths
      - total: number of files found
    """
    logger.info(f"[tool] list_repo_files: scanning {repo_path}")
    result = []
    for dirpath, dirnames, filenames in os.walk(repo_path):
        # Skip hidden directories and .git
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fname in filenames:
            if fname.startswith("."):
                continue  # skip hidden files
            full = os.path.join(dirpath, fname)
            rel  = os.path.relpath(full, repo_path)
            result.append(rel)
            if len(result) >= max_files:
                logger.warning("max_files limit reached; truncating file list")
                return {"files": result, "total": len(result), "truncated": True}
    logger.debug(f"[tool] list_repo_files: found {len(result)} files")
    return {"files": result, "total": len(result), "truncated": False}


# ──────────────────────────────────────────────────────────────────
# 2. read_file_content
# ──────────────────────────────────────────────────────────────────
def read_file_content(
    repo_path: str,
    relative_path: str,
    max_bytes: int = 32_768,
) -> dict[str, Any]:
    """Read a file from the sandboxed repo and return its content.

    Returns a dict with:
      - path: the relative file path
      - content: file text (or a truncation notice)
      - truncated: True if the file exceeded max_bytes
      - error: error message if the file could not be read
    """
    logger.info(f"[tool] read_file_content: {relative_path}")
    try:
        full_path = safe_path_join(repo_path, relative_path)
    except ValueError as exc:
        return {"path": relative_path, "content": "", "error": str(exc)}

    if not os.path.isfile(full_path):
        return {"path": relative_path, "content": "", "error": "File not found"}

    try:
        with open(full_path, "r", encoding="utf-8", errors="replace") as fh:
            raw = fh.read(max_bytes + 1)
        truncated = len(raw) > max_bytes
        return {
            "path": relative_path,
            "content": raw[:max_bytes],
            "truncated": truncated,
            "error": None,
        }
    except Exception as exc:
        logger.error(f"read_file_content error: {exc}")
        return {"path": relative_path, "content": "", "error": str(exc)}


# ──────────────────────────────────────────────────────────────────
# 3. search_code
# ──────────────────────────────────────────────────────────────────
def search_code(
    repo_path: str,
    pattern: str,
    file_glob: str = "*.py",
    max_results: int = 50,
) -> dict[str, Any]:
    """Search for a regex *pattern* across files matching *file_glob*.

    Returns a dict with:
      - matches: list of {file, line, content} dicts
      - total: total number of matches
    """
    logger.info(f"[tool] search_code: pattern={pattern!r} glob={file_glob!r}")
    matches = []
    try:
        regex = re.compile(pattern)
    except re.error as exc:
        return {"matches": [], "total": 0, "error": f"Invalid regex: {exc}"}

    for dirpath, dirnames, filenames in os.walk(repo_path):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fname in filenames:
            # Simple glob matching on extension
            if file_glob != "*" and not fname.endswith(file_glob.lstrip("*")):
                continue
            full_path = os.path.join(dirpath, fname)
            rel_path  = os.path.relpath(full_path, repo_path)
            try:
                with open(full_path, "r", encoding="utf-8", errors="replace") as fh:
                    for lineno, line in enumerate(fh, 1):
                        if regex.search(line):
                            matches.append({
                                "file": rel_path,
                                "line": lineno,
                                "content": line.rstrip(),
                            })
                            if len(matches) >= max_results:
                                return {"matches": matches, "total": len(matches), "truncated": True}
            except Exception:
                pass

    return {"matches": matches, "total": len(matches), "truncated": False}


# ──────────────────────────────────────────────────────────────────
# 4. list_commits
# ──────────────────────────────────────────────────────────────────
def list_commits(repo_path: str, max_count: int = 30) -> dict[str, Any]:
    """Return the last *max_count* commits from the cloned repository.

    Returns a dict with:
      - commits: list of {hash, author, date, message} dicts
      - total: number of commits returned
    """
    logger.info(f"[tool] list_commits: repo={repo_path} max={max_count}")
    try:
        cmd = [
            "git", "log",
            f"--max-count={max_count}",
            "--pretty=format:%H|%an|%ad|%s",
            "--date=short",
        ]
        result = subprocess.run(
            cmd, cwd=repo_path, capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            return {"commits": [], "total": 0, "error": result.stderr.strip()}

        commits = []
        for line in result.stdout.strip().splitlines():
            parts = line.split("|", 3)
            if len(parts) == 4:
                commits.append({
                    "hash":    parts[0],
                    "author":  parts[1],
                    "date":    parts[2],
                    "message": parts[3],
                })
        logger.debug(f"[tool] list_commits: returned {len(commits)} commits")
        return {"commits": commits, "total": len(commits)}
    except Exception as exc:
        logger.error(f"list_commits error: {exc}")
        return {"commits": [], "total": 0, "error": str(exc)}


# ──────────────────────────────────────────────────────────────────
# 5. check_file_exists
# ──────────────────────────────────────────────────────────────────
def check_file_exists(repo_path: str, relative_path: str) -> dict[str, Any]:
    """Check whether a specific file exists in the repository.

    Useful for verifying the presence of important DevOps files like
    .gitignore, requirements.txt, Dockerfile, etc.
    """
    logger.info(f"[tool] check_file_exists: {relative_path}")
    try:
        full_path = safe_path_join(repo_path, relative_path)
    except ValueError as exc:
        return {"exists": False, "error": str(exc)}

    exists = os.path.isfile(full_path)
    logger.debug(f"[tool] check_file_exists: {relative_path} -> {exists}")
    return {"path": relative_path, "exists": exists}


# ──────────────────────────────────────────────────────────────────
# 6. git_status
# ──────────────────────────────────────────────────────────────────
def git_status(repo_path: str) -> dict[str, Any]:
    """Inspect working tree status of the cloned repository.

    Identifies untracked, modified, or staged files, helping detect
    improper repository hygiene or untracked generated artifacts.
    """
    logger.info(f"[tool] git_status: repo={repo_path}")
    try:
        cmd = ["git", "status", "--porcelain"]
        result = subprocess.run(
            cmd, cwd=repo_path, capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            return {"clean": False, "changes": [], "error": result.stderr.strip()}

        changes = [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]
        return {"clean": len(changes) == 0, "changes": changes, "total_changes": len(changes)}
    except Exception as exc:
        logger.error(f"git_status error: {exc}")
        return {"clean": False, "changes": [], "error": str(exc)}


# ──────────────────────────────────────────────────────────────────
# Direct Specification Aliases
# ──────────────────────────────────────────────────────────────────
list_files = list_repo_files
read_file = read_file_content
git_log = list_commits

