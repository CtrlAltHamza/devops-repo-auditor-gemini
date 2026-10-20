import logging
import os
import re

# Regular expression patterns for common sensitive tokens/secrets
CREDENTIAL_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)((?:api[_-]?key|password|secret|token|auth[_-]?token)\s*[:=]\s*['\"])([^'\"]+)(['\"])"
)

TOKEN_PATTERNS = [
    re.compile(r"ghp_[a-zA-Z0-9]{36}"),                         # GitHub Personal Access Token
    re.compile(r"gho_[a-zA-Z0-9]{36}"),                         # GitHub OAuth Token
    re.compile(r"glpat-[a-zA-Z0-9\-_]{20,}"),                   # GitLab Personal Access Token
    re.compile(r"AKIA[0-9A-Z]{16}"),                             # AWS Access Key ID
    re.compile(r"AIzaSy[0-9A-Za-z\-_]{35}"),                     # Google API Key
    re.compile(r"xox[baprs]-[0-9a-zA-Z]{10,48}"),               # Slack Token
    re.compile(r"-----BEGIN (?:RSA|DSA|EC|OPENSSH|PRIVATE) KEY-----[\s\S]*?-----END (?:RSA|DSA|EC|OPENSSH|PRIVATE) KEY-----"),
]


class SecretScrubbingFilter(logging.Filter):
    """
    MLOps Safety Guardrail:
    Prevents secrets and credentials from being written to logs.
    Fulfills constraint: 'Never expose secrets in logs or output.'
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self.scrub(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: self.scrub(str(v)) for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(self.scrub(str(a)) for a in record.args)
        return True

    @staticmethod
    def scrub(text: str) -> str:
        # First scrub credential assignments: preserve variable name, redact value
        text = CREDENTIAL_ASSIGNMENT_PATTERN.sub(r"\g<1>***[REDACTED_SECRET]***\g<3>", text)

        # Next scrub raw standalone tokens
        for pattern in TOKEN_PATTERNS:
            def replacer(match):
                matched = match.group(0)
                if len(matched) > 8:
                    return matched[:4] + "***[REDACTED_SECRET]***" + matched[-4:]
                return "***[REDACTED_SECRET]***"
            text = pattern.sub(replacer, text)

        return text


def get_logger(name: str = "devops_auditor", level: str | None = None) -> logging.Logger:
    """
    Configures and returns a structured logger with security filters.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        log_level_name = level or os.getenv("LOG_LEVEL", "INFO").upper()
        log_level = getattr(logging, log_level_name, logging.INFO)
        logger.setLevel(log_level)

        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        console_handler.addFilter(SecretScrubbingFilter())
        logger.addHandler(console_handler)

        # Persistent local file handler (safely ignored by git in .gitignore)
        try:
            log_dir = "logs"
            os.makedirs(log_dir, exist_ok=True)
            file_handler = logging.FileHandler(
                os.path.join(log_dir, "audit.log"),
                encoding="utf-8",
            )
            file_handler.setLevel(log_level)
            file_handler.setFormatter(formatter)
            file_handler.addFilter(SecretScrubbingFilter())
            logger.addHandler(file_handler)
        except OSError:
            pass  # noqa: S110 - Fall back cleanly to console logging if disk write is restricted

        logger.propagate = False
    return logger
