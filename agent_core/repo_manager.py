import os
import re
import stat
import shutil
import tempfile
import subprocess
from contextlib import contextmanager
from typing import Generator
from agent_core.logger import get_logger

logger = get_logger("repo_manager")

GITHUB_URL_REGEX = re.compile(
    r"^https://github\.com/[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+(?:\.git)?/?$"
)


def validate_repo_url(url: str) -> str:
    """
    Validates that the input is a valid public GitHub repository URL.
    Defends against command/argument injection.
    """
    cleaned_url = url.strip()
    if not GITHUB_URL_REGEX.match(cleaned_url):
        raise ValueError(
            f"Invalid GitHub repository URL: '{url}'. "
            "Expected format: 'https://github.com/owner/repository'"
        )
    return cleaned_url


def _remove_readonly(func, path, exc_info):
    """
    Error handler for shutil.rmtree on Windows systems where
    Git creates read-only files in .git/objects.
    """
    os.chmod(path, stat.S_IWRITE)
    func(path)


@contextmanager
def clone_repository(repo_url: str, depth: int = 50) -> Generator[str, None, None]:
    """
    Context manager that:
    1. Validates the repo URL.
    2. Creates a sandboxed temporary directory.
    3. Shallow-clones the target repo (improving MLOps efficiency and speed).
    4. Yields the path to the cloned repository.
    5. Cleans up securely upon completion, leaving host system clean.
    """
    validated_url = validate_repo_url(repo_url)
    temp_dir = tempfile.mkdtemp(prefix="devops_audit_")
    logger.info(f"Created isolated sandbox at {temp_dir}")

    try:
        logger.info(f"Cloning {validated_url} (depth={depth})...")
        cmd = ["git", "clone", "--depth", str(depth), "--quiet", validated_url, temp_dir]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        
        if result.returncode != 0:
            error_msg = result.stderr.strip() or "Unknown git error"
            raise RuntimeError(f"Failed to clone repository: {error_msg}")

        logger.info(f"Successfully cloned repository into {temp_dir}")
        yield temp_dir

    finally:
        logger.info(f"Cleaning up sandbox at {temp_dir}...")
        try:
            shutil.rmtree(temp_dir, onerror=_remove_readonly)
            logger.info("Sandbox cleaned up successfully.")
        except Exception as e:
            logger.warning(f"Error cleaning up sandbox directory {temp_dir}: {e}")
