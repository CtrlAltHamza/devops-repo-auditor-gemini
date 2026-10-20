import pytest

from agent_core.utils import safe_path_join


def test_safe_path_join_valid():
    import os
    import tempfile
    with tempfile.TemporaryDirectory() as base:
        result = safe_path_join(base, "subdir", "file.txt")
        assert result.startswith(os.path.abspath(base))


def test_safe_path_join_traversal_raises():
    import tempfile
    with tempfile.TemporaryDirectory() as base, pytest.raises(ValueError, match="Attempted path escape"):
        safe_path_join(base, "..", "secret.txt")
