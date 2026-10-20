#!/usr/bin/env python3
"""
DevOps Repository Auditing Agent
CLI Entry point adhering to assignment execution contract:
python agent.py --repo <github_repository_url> --output report.json
"""

import sys
import argparse
import json
from pathlib import Path
from dotenv import load_dotenv

# Load local environment variables from .env if present
load_dotenv()

from agent_core.logger import get_logger
from agent_core.repo_manager import clone_repository, validate_repo_url
from agent_core.loop import run_agent_loop
from agent_core.schema import AuditReport

logger = get_logger("agent_cli")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Autonomous AI Agent for DevOps Repository Auditing"
    )
    parser.add_argument(
        "--repo",
        type=str,
        required=True,
        help="Public GitHub repository URL to inspect (e.g. https://github.com/owner/repo)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="report.json",
        help="Path where the output JSON report will be saved (default: report.json)"
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=15,
        help="Maximum inspection turns for agent reasoning loop (default: 15)"
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Gemini model to use (default: gemini-2.5-flash or from GEMINI_MODEL env)"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    logger.info("DevOps Auditing Agent initialized.")
    logger.info(f"Target repository: {args.repo}")
    logger.info(f"Target report destination: {args.output}")

    try:
        # Validate repository URL
        validated_url = validate_repo_url(args.repo)

        # Execute inspection in sandboxed temporary workspace
        with clone_repository(validated_url) as sandbox_path:
            report = run_agent_loop(
                repo_url=validated_url,
                repo_path=sandbox_path,
                max_iterations=args.max_iterations,
                model_name=args.model
            )

        # Write output report adhering strictly to schema contract
        out_path = Path(args.output).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(report.model_dump_json(indent=2))

        logger.info(f"Report successfully saved to {out_path}")
        print(f"Audit completed successfully. Report written to {out_path}")
        sys.exit(0)

    except ValueError as ve:
        logger.error(f"Configuration or validation error: {ve}")
        sys.stderr.write(f"Error: {ve}\n")
        sys.exit(1)
    except RuntimeError as re:
        logger.error(f"Runtime error during inspection: {re}")
        sys.stderr.write(f"Runtime Error: {re}\n")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Unexpected fatal error: {e}")
        sys.stderr.write(f"Fatal Error: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
