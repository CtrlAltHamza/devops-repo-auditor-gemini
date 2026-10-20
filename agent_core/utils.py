import os


def safe_path_join(base_dir: str, *paths: str) -> str:
    """Join *paths* to *base_dir* and ensure the result stays inside *base_dir*.

    Prevents directory-traversal attacks when the agent reads files from a
    sandboxed repository clone. Raises ValueError if the resulting path
    would escape the base directory.
    """
    final_path = os.path.abspath(os.path.join(base_dir, *paths))
    base_abs = os.path.abspath(base_dir)
    if not final_path.startswith(base_abs + os.sep):
        raise ValueError(
            f"Attempted path escape: {final_path} is outside {base_abs}"
        )
    return final_path
