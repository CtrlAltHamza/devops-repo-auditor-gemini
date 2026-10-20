#!/usr/bin/env python3
"""
devops-audit-agent — CLI entry point.

Usage:
    python agent.py <github_repo_url> [--output report.json]

Example:
    python agent.py https://github.com/pallets/flask --output flask_audit.json
"""

import argparse
import json
import sys
import os

from dotenv import load_dotenv

load_dotenv()  # Load .env file (GEMINI_API_KEY, etc.)

from agent_core.logger       import get_logger
from agent_core.repo_manager import clone_repository
from agent_core.loop         import run_audit

logger = get_logger("agent")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="devops-audit-agent",
        description="Autonomous DevOps Repository Auditing Agent powered by Google Gemini.",
    )
    parser.add_argument(
        "repo_url",
        help="GitHub repository URL to audit (e.g. https://github.com/owner/repo)",
    )
    parser.add_argument(
        "--output", "-o",
        default="audit_report.json",
        help="Path to write the JSON audit report (default: audit_report.json)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not os.environ.get("GEMINI_API_KEY"):
        logger.error("GEMINI_API_KEY environment variable is not set. Please add it to your .env file.")
        return 1

    logger.info(f"Starting DevOps audit for: {args.repo_url}")

    try:
        with clone_repository(args.repo_url) as repo_path:
            report = run_audit(args.repo_url, repo_path)

        # Write JSON report
        report_dict = report.model_dump()
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(report_dict, fh, indent=2, default=str)

        logger.info(f"Audit complete! Report saved to: {args.output}")
        logger.info(f"Overall score: {report.overall_score}/100")
        logger.info(f"Total violations: {len(report.violations)}")

        return 0

    except ValueError as exc:
        logger.error(f"Invalid input: {exc}")
        return 1
    except RuntimeError as exc:
        logger.error(f"Audit failed: {exc}")
        return 2
    except Exception as exc:
        logger.exception(f"Unexpected error: {exc}")
        return 3


if __name__ == "__main__":
    sys.exit(main())
