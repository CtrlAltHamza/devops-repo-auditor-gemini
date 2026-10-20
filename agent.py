#!/usr/bin/env python3
"""
devops-audit-agent — CLI entry point.

Execution Contract:
    python agent.py --repo <github_repository_url> --output report.json

Supports both --repo flag and positional repo URL for maximum compatibility.
"""

import argparse
import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()  # Load .env file (GEMINI_API_KEY, etc.)

from agent_core.logger import get_logger
from agent_core.loop import run_audit
from agent_core.repo_manager import clone_repository

logger = get_logger("agent")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="devops-audit-agent",
        description="Autonomous DevOps Repository Auditing Agent powered by Google Gemini.",
    )
    # Support both --repo flag (assignment specification) and positional fallback
    parser.add_argument(
        "--repo", "-r",
        dest="repo_url",
        default=None,
        help="GitHub repository URL to audit (e.g. https://github.com/owner/repo)",
    )
    parser.add_argument(
        "positional_repo_url",
        nargs="?",
        default=None,
        help="Positional repository URL fallback",
    )
    parser.add_argument(
        "--output", "-o",
        default="report.json",
        help="Path to write the JSON audit report (default: report.json)",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=None,
        help="Maximum agent reasoning iterations before termination",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_url = args.repo_url or args.positional_repo_url

    if not repo_url:
        logger.error("A repository URL must be provided via --repo <url> or as the first argument.")
        return 1

    if args.max_iterations:
        os.environ["MAX_AGENT_ITERATIONS"] = str(args.max_iterations)

    if not os.environ.get("GEMINI_API_KEY"):
        logger.error("GEMINI_API_KEY environment variable is not set. Please add it to your .env file.")
        return 1

    logger.info(f"Starting DevOps audit for: {repo_url}")

    try:
        with clone_repository(repo_url) as repo_path:
            report = run_audit(repo_url, repo_path)

        # Write compliant JSON report
        report_dict = report.model_dump()
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(report_dict, fh, indent=2, default=str)

        logger.info(f"Audit complete! Report saved to: {args.output}")
        logger.info(f"Total violations detected: {len(report.violations)}")

        return 0

    except ValueError as exc:
        logger.error(f"Invalid input: {exc}")
        return 1
    except RuntimeError as exc:
        logger.error(f"Audit failed: {exc}")
        return 2
    except Exception:
        logger.exception("Unexpected error during audit")
        return 3


if __name__ == "__main__":
    sys.exit(main())

