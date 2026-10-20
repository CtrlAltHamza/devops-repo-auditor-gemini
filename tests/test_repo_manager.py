import pytest

from agent_core.repo_manager import validate_repo_url


def test_validate_repo_url_valid():
    valid_urls = [
        "https://github.com/torvalds/linux",
        "https://github.com/pallets/flask.git",
        "https://github.com/psf/requests/",
    ]
    for url in valid_urls:
        validated = validate_repo_url(url)
        assert validated.startswith("https://github.com/")


def test_validate_repo_url_invalid():
    invalid_urls = [
        "http://github.com/user/repo",           # Insecure HTTP
        "https://gitlab.com/user/repo",          # Non-GitHub
        "--upload-pack=exploit",                 # Command argument injection
        "https://github.com/user/repo; rm -rf",  # Shell injection
        "ftp://github.com/user/repo",
    ]
    for url in invalid_urls:
        with pytest.raises(ValueError):
            validate_repo_url(url)
