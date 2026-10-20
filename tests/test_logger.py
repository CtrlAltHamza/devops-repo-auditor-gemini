import logging
from agent_core.logger import get_logger, SecretScrubbingFilter


def test_secret_scrubbing_github_token():
    filter_ = SecretScrubbingFilter()
    raw_msg = "Discovered token ghp_1234567890abcdef1234567890abcdef1234 in config"
    scrubbed = filter_.scrub(raw_msg)
    assert "ghp_1234567890abcdef1234567890abcdef1234" not in scrubbed
    assert "[REDACTED_SECRET]" in scrubbed


def test_secret_scrubbing_aws_key():
    filter_ = SecretScrubbingFilter()
    raw_msg = "Connecting with AKIAIOSFODNN7EXAMPLE credentials"
    scrubbed = filter_.scrub(raw_msg)
    assert "AKIAIOSFODNN7EXAMPLE" not in scrubbed
    assert "[REDACTED_SECRET]" in scrubbed


def test_logger_creation():
    logger = get_logger("test_auditor")
    assert logger.name == "test_auditor"
    assert any(isinstance(f, SecretScrubbingFilter) for f in logger.handlers[0].filters)
