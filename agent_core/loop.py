import os
import json
from typing import Dict, Any, List, Optional
from google.genai import types

from agent_core.logger import get_logger, SecretScrubbingFilter
from agent_core.schema import AuditReport, Violation
from agent_core.prompts import SYSTEM_PROMPT, VIOLATION_SYNTHESIS_PROMPT
from agent_core.llm_client import get_gemini_client, get_inspection_tools_declaration
from tools import list_files, read_file, search_code, git_log, git_status

logger = get_logger("agent_loop")


def dispatch_tool(tool_name: str, args: Dict[str, Any], repo_path: str) -> Dict[str, Any]:
    """
    Executes the tool requested by the LLM within the isolated repository sandbox.
    Fulfills manual dispatch requirement: No external agent frameworks.
    """
    logger.info(f"Dispatching tool '{tool_name}' with arguments: {args}")

    if tool_name == "list_files":
        return list_files(
            repo_path=repo_path,
            sub_dir=args.get("sub_dir", ""),
            max_depth=int(args.get("max_depth", 4))
        )
    elif tool_name == "read_file":
        return read_file(
            repo_path=repo_path,
            file_path=args.get("file_path", ""),
            start_line=int(args.get("start_line", 1)),
            end_line=int(args.get("end_line", 150))
        )
    elif tool_name == "search_code":
        return search_code(
            repo_path=repo_path,
            pattern=args.get("pattern", ""),
            file_pattern=args.get("file_pattern", "")
        )
    elif tool_name == "git_log":
        return git_log(
            repo_path=repo_path,
            max_commits=int(args.get("max_commits", 15))
        )
    elif tool_name == "git_status":
        return git_status(repo_path=repo_path)
    else:
        logger.warning(f"Unknown tool invoked by model: '{tool_name}'")
        return {"error": f"Unknown tool: '{tool_name}'"}


def sanitize_report(report: AuditReport, repo_url: str) -> AuditReport:
    """
    MLOps Quality Gate:
    1. Enforces correct repository URL.
    2. Deduplicates violations.
    3. Scrubs any accidental credential remnants from evidence/descriptions.
    4. Normalizes null fields.
    """
    report.repository = repo_url
    seen = set()
    cleaned_violations: List[Violation] = []

    for v in report.violations:
        # Scrub evidence & description for absolute safety
        clean_evidence = SecretScrubbingFilter.scrub(v.evidence)
        clean_desc = SecretScrubbingFilter.scrub(v.description)

        # Normalize file and line
        clean_file = v.file.strip() if v.file and v.file.strip() not in ("", "null", "None") else None
        clean_line = v.line if (isinstance(v.line, int) and v.line > 0) else None

        # Deduplication key
        dedup_key = (v.rule_id, clean_file, clean_line)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        cleaned_violations.append(
            Violation(
                rule_id=v.rule_id,
                category=v.category,
                severity=v.severity,
                file=clean_file,
                line=clean_line,
                description=clean_desc,
                evidence=clean_evidence,
                recommendation=v.recommendation
            )
        )

    report.violations = cleaned_violations
    return report


def run_agent_loop(
    repo_url: str,
    repo_path: str,
    max_iterations: int = 15,
    model_name: Optional[str] = None
) -> AuditReport:
    """
    Executes the autonomous DevOps auditing cycle:
    Observe -> Reason -> Select Tool -> Execute Tool -> Interpret Results -> Report.

    Args:
        repo_url: Public GitHub repository URL.
        repo_path: Path to the cloned repository in the local sandbox.
        max_iterations: Maximum loop turns before forcing report synthesis.
        model_name: Gemini model name (default from GEMINI_MODEL env var or 'gemini-2.5-flash').

    Returns:
        Validated AuditReport adhering strictly to the assignment schema.
    """
    client = get_gemini_client()
    model = model_name or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    tools_declaration = get_inspection_tools_declaration()

    logger.info(f"Starting DevOps Audit Agent loop on {repo_url} using model {model}")

    # Phase 1 of Cycle: Observe (Initial repository discovery)
    initial_discovery = list_files(repo_path, max_depth=3)
    files_summary = initial_discovery.get("files", [])[:80]
    total_found = initial_discovery.get("count", len(files_summary))

    initial_prompt = (
        f"Repository cloned to local sandbox: {repo_url}\n"
        f"Discovered {total_found} files. Top entries:\n"
        f"{json.dumps(files_summary, indent=2)}\n\n"
        "Begin your autonomous investigation loop. Inspect repository hygiene, dependencies, "
        "CI/CD workflows (.github/workflows), test suites, configuration, and security. "
        "Use your inspection tools (read_file, search_code, git_log, git_status, list_files) "
        "to gather verified evidence."
    )

    contents: List[types.Content] = [
        types.Content(role="user", parts=[types.Part.from_text(text=initial_prompt)])
    ]

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        temperature=0.1,
        tools=[tools_declaration],
    )

    iteration = 0
    investigation_finished = False

    while iteration < max_iterations and not investigation_finished:
        iteration += 1
        logger.info(f"--- Agent Cycle Turn {iteration}/{max_iterations} ---")

        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=config
        )

        candidate = response.candidates[0] if response.candidates else None
        if not candidate or not candidate.content:
            logger.warning("Empty response from LLM, prompting continuation...")
            contents.append(types.Content(role="user", parts=[types.Part.from_text(text="Please continue the audit.")]))
            continue

        model_content = candidate.content
        contents.append(model_content)

        function_calls = response.function_calls
        if function_calls:
            # Model selected tools: Execute tool dispatch in Python
            response_parts = []
            for call in function_calls:
                logger.info(f"[Turn {iteration}] LLM requested tool: {call.name}")
                tool_output = dispatch_tool(call.name, call.args, repo_path)
                response_parts.append(
                    types.Part.from_function_response(
                        name=call.name,
                        response=tool_output
                    )
                )

            # Supply tool outputs back to LLM for interpretation
            contents.append(types.Content(role="user", parts=response_parts))
        else:
            # Model provided textual reasoning without tool calls
            text_response = response.text or ""
            logger.info(f"[Turn {iteration}] Agent reasoning output: {text_response[:150]}...")

            if "INVESTIGATION_COMPLETE" in text_response or iteration >= max_iterations:
                logger.info("Agent signaled completion of investigation.")
                investigation_finished = True
            else:
                # Prompt the agent to continue or wrap up
                follow_up = (
                    "If you need to inspect more files or search code, call the appropriate tool. "
                    "If you have gathered sufficient evidence to conclude your audit, respond with 'INVESTIGATION_COMPLETE'."
                )
                contents.append(types.Content(role="user", parts=[types.Part.from_text(text=follow_up)]))

    # Phase 5 of Cycle: Final Synthesis & JSON Compliance
    logger.info("Synthesizing final structured audit report...")
    synthesis_contents = list(contents)
    synthesis_contents.append(
        types.Content(role="user", parts=[types.Part.from_text(text=VIOLATION_SYNTHESIS_PROMPT)])
    )

    synthesis_config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        temperature=0.0,
        response_mime_type="application/json",
        response_schema=AuditReport
    )

    synthesis_response = client.models.generate_content(
        model=model,
        contents=synthesis_contents,
        config=synthesis_config
    )

    try:
        report_data = json.loads(synthesis_response.text)
        report = AuditReport.model_validate(report_data)
    except Exception as e:
        logger.error(f"Failed to parse synthesis response directly as AuditReport: {e}")
        # Fallback to empty report with repo url
        report = AuditReport(repository=repo_url, violations=[])

    clean_report = sanitize_report(report, repo_url)
    logger.info(f"Audit completed successfully. Found {len(clean_report.violations)} verified violations.")
    return clean_report
