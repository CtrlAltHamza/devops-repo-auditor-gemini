"""
Agentic Loop — Observe → Reason → Act → Repeat until done.
The loop drives the DevOps audit by letting the Gemini model
decide which tool to call next and when the audit is complete.
"""

import os
from typing import Any

from google.genai import types
from pydantic import ValidationError

from agent_core.llm_client import GeminiClient
from agent_core.logger import get_logger
from agent_core.prompts import SYSTEM_PROMPT
from agent_core.schema import AuditReport
from tools import (
    check_file_exists,
    git_log,
    git_status,
    inspect_github_actions,
    list_commits,
    list_files,
    list_repo_files,
    read_file,
    read_file_content,
    search_code,
)

logger = get_logger("loop")

# Maximum number of reasoning iterations before we force‑stop
DEFAULT_MAX_ITERATIONS = int(
    os.environ.get("MAX_ITERATIONS", os.environ.get("MAX_AGENT_ITERATIONS", "15"))
)
MAX_ITERATIONS = DEFAULT_MAX_ITERATIONS


# ─────────────────────────────────────────────────────────────
# Tool registry — maps name → callable
# ─────────────────────────────────────────────────────────────
TOOL_REGISTRY: dict[str, Any] = {
    # Primary canonical implementations
    "list_repo_files":        list_repo_files,
    "read_file_content":      read_file_content,
    "search_code":            search_code,
    "list_commits":           list_commits,
    "check_file_exists":      check_file_exists,
    "git_status":             git_status,
    "inspect_github_actions": inspect_github_actions,
    # Direct specification aliases
    "list_files":             list_files,
    "read_file":              read_file,
    "git_log":                git_log,
}


# ─────────────────────────────────────────────────────────────
# Gemini function declarations
# ─────────────────────────────────────────────────────────────
TOOL_DECLARATIONS = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="list_repo_files",
            description="List all files in the cloned repository (excludes .git/).",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "repo_path": types.Schema(type=types.Type.STRING, description="Absolute path to the repository root"),
                    "max_files": types.Schema(type=types.Type.INTEGER, description="Maximum number of files to return (default 500)"),
                },
                required=["repo_path"],
            ),
        ),
        types.FunctionDeclaration(
            name="read_file_content",
            description="Read the content of a specific file from the repository.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "repo_path":     types.Schema(type=types.Type.STRING, description="Absolute path to the repository root"),
                    "relative_path": types.Schema(type=types.Type.STRING, description="File path relative to the repo root"),
                    "max_bytes":     types.Schema(type=types.Type.INTEGER, description="Maximum bytes to read (default 32768)"),
                },
                required=["repo_path", "relative_path"],
            ),
        ),
        types.FunctionDeclaration(
            name="search_code",
            description="Search for a regex pattern across source files in the repository.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "repo_path":   types.Schema(type=types.Type.STRING, description="Absolute path to the repository root"),
                    "pattern":     types.Schema(type=types.Type.STRING, description="Regex pattern to search for"),
                    "file_glob":   types.Schema(type=types.Type.STRING, description="File extension glob (e.g. *.py, *.yml)"),
                    "max_results": types.Schema(type=types.Type.INTEGER, description="Max matches to return"),
                },
                required=["repo_path", "pattern"],
            ),
        ),
        types.FunctionDeclaration(
            name="list_commits",
            description="List recent Git commits from the repository.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "repo_path":  types.Schema(type=types.Type.STRING, description="Absolute path to the repository root"),
                    "max_count":  types.Schema(type=types.Type.INTEGER, description="Max number of commits to return"),
                },
                required=["repo_path"],
            ),
        ),
        types.FunctionDeclaration(
            name="check_file_exists",
            description="Check whether a specific file (e.g. .gitignore, Dockerfile) exists in the repository.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "repo_path":     types.Schema(type=types.Type.STRING, description="Absolute path to the repository root"),
                    "relative_path": types.Schema(type=types.Type.STRING, description="File path relative to the repo root"),
                },
                required=["repo_path", "relative_path"],
            ),
        ),
        types.FunctionDeclaration(
            name="git_status",
            description="Inspect git working tree status to check for untracked artifacts or uncommitted changes.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "repo_path": types.Schema(type=types.Type.STRING, description="Absolute path to the repository root"),
                },
                required=["repo_path"],
            ),
        ),
        types.FunctionDeclaration(
            name="inspect_github_actions",
            description="Inspect CI/CD workflows in .github/workflows for triggers, security permissions, and test/lint gates.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "repo_path": types.Schema(type=types.Type.STRING, description="Absolute path to the repository root"),
                },
                required=["repo_path"],
            ),
        ),
    ]
)



# ─────────────────────────────────────────────────────────────
# Main loop
# ─────────────────────────────────────────────────────────────
def run_audit(
    repo_url: str,
    repo_path: str,
    model: str | None = None,
    max_iterations: int | None = None,
) -> AuditReport:
    """Run the full DevOps audit loop on a cloned repository.

    Args:
        repo_url:       The original GitHub URL (for the report).
        repo_path:      The local path to the cloned repository.
        model:          Optional Gemini model name override.
        max_iterations: Optional max iterations override (defaults to MAX_ITERATIONS).

    Returns:
        A validated AuditReport Pydantic model instance.
    """
    client = GeminiClient(model=model)
    limit = max_iterations or DEFAULT_MAX_ITERATIONS

    # Conversation history
    contents: list[types.ContentUnionDict] = [
        {
            "role": "user",
            "parts": [
                {
                    "text": (
                        f"Please audit the DevOps repository at URL: {repo_url}\n"
                        f"The repository has been cloned locally to: {repo_path}\n"
                        "Use the provided tools to inspect the repository systematically, "
                        "then produce the final JSON audit report."
                    )
                }
            ],
        }
    ]

    logger.info(f"Starting audit loop for {repo_url} (max_iterations={limit}, model={client._model})")
    repairing_report = False

    for iteration in range(1, limit + 1):
        logger.info(f"─── Iteration {iteration}/{limit} ───")
        if iteration > 1:
            import time
            time.sleep(2)  # Polite pacing to respect free-tier quota limits

        if iteration == limit:
            logger.info("Final iteration reached: instructing model to synthesize report without further tools.")
            contents.append(
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(
                            text=(
                                "Investigation concluded. Do NOT call any tools. "
                                f"Synthesize all facts gathered into the final JSON audit report for {repo_url} now. "
                                'Adhere strictly to the JSON schema: {"repository": "' + repo_url + '", "violations": [...]}. '
                                "Output ONLY the JSON object, enclosed in a ```json code fence."
                            )
                        )
                    ],
                )
            )
            tools_for_step = None
        elif repairing_report:
            tools_for_step = None
        elif iteration == limit - 1:
            contents.append(
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(
                            text="Notice: Only 1 tool iteration remains. Conclude any pending checks."
                        )
                    ],
                )
            )
            tools_for_step = [TOOL_DECLARATIONS]
        else:
            tools_for_step = [TOOL_DECLARATIONS]

        response = client.generate(
            contents          = contents,
            tools             = tools_for_step,
            system_instruction = SYSTEM_PROMPT,
        )

        # Check for tool calls
        tool_calls = client.extract_tool_calls(response)

        if tool_calls and iteration < limit:
            # Append the model's response directly to history (preserves function_calls and SDK structures)
            contents.append(response.candidates[0].content)

            # Execute each requested tool
            tool_results = []
            for call in tool_calls:
                fn_name = call.name
                fn_args = dict(call.args) if call.args else {}
                logger.info(f"[call] {fn_name}({fn_args})")

                if fn_name not in TOOL_REGISTRY:
                    result = {"error": f"Unknown tool: {fn_name}"}
                else:
                    try:
                        result = TOOL_REGISTRY[fn_name](**fn_args)
                    except Exception as exc:
                        result = {"error": str(exc)}
                        logger.error(f"Tool error in {fn_name}: {exc}")

                logger.debug(f"[result] {fn_name} => {str(result)[:200]}")
                response_dict = result if isinstance(result, dict) else {"result": result}
                tool_results.append(
                    types.Part.from_function_response(
                        name=fn_name,
                        response=response_dict,
                    )
                )

            # Add tool results to conversation history
            contents.append(types.Content(role="user", parts=tool_results))

        else:
            # No tool calls (or final iteration) → model has finished; parse the JSON report
            logger.info("Parsing audit report from model response")
            raw_json = client.parse_json_response(response)
            if raw_json is None:
                text = client.extract_text(response) or ""
                logger.warning(f"Could not parse JSON from model response (iteration {iteration}/{limit}): {text[:300]!r}")
                if iteration < limit and response.candidates and response.candidates[0].content:
                    contents.append(response.candidates[0].content)
                    contents.append(
                        types.Content(
                            role="user",
                            parts=[
                                types.Part.from_text(
                                    text=(
                                        "Do not call any tools. Please produce the final JSON audit report now according to the required schema: "
                                        '{"repository": "' + repo_url + '", "violations": [...]}. '
                                        "Output ONLY the JSON object, enclosed in a ```json code fence."
                                    )
                                )
                            ],
                        )
                    )
                    repairing_report = True
                    continue
                break

            try:
                report = AuditReport.model_validate(raw_json)
            except ValidationError as exc:
                logger.warning(
                    "Model returned JSON that does not match the audit report schema "
                    f"(iteration {iteration}/{limit}): {exc}"
                )
                if iteration < limit:
                    if response.candidates and response.candidates[0].content:
                        contents.append(response.candidates[0].content)
                    contents.append(
                        types.Content(
                            role="user",
                            parts=[
                                types.Part.from_text(
                                    text=(
                                        "Do not call any tools. Correct the previous response so it matches "
                                        "the required audit report schema exactly: "
                                        '{"repository": "' + repo_url + '", "violations": [...]}. '
                                        f"Validation errors: {exc}. "
                                        "Keep the gathered findings, use an empty violations array only if "
                                        "there are genuinely no findings, and output ONLY valid JSON."
                                    )
                                )
                            ],
                        )
                    )
                    repairing_report = True
                    continue
                break

            logger.info("Audit report parsed and validated successfully")
            return report

    # If loop ended without parsed report, execute forced final synthesis
    logger.info("Loop ended without report — forcing final report extraction.")
    contents.append(
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(
                    text=(
                        f"Produce the final JSON audit report for {repo_url} now based on the findings above. "
                        'Schema: {"repository": "' + repo_url + '", "violations": [...]}. '
                        "Output ONLY the JSON object, enclosed in a ```json code fence."
                    )
                )
            ],
        )
    )
    final_resp = client.generate(
        contents=contents,
        tools=None,
        system_instruction=SYSTEM_PROMPT,
    )
    raw_json = client.parse_json_response(final_resp)
    if raw_json is not None:
        try:
            report = AuditReport.model_validate(raw_json)
        except ValidationError as exc:
            logger.error(f"Final model response did not match the audit report schema: {exc}")
            raise RuntimeError(
                "Gemini returned JSON that does not satisfy the required audit report schema."
            ) from exc
        logger.info("Final forced audit report parsed and validated successfully")
        return report

    raise RuntimeError(f"Audit loop exceeded maximum iterations ({limit}) without producing a report.")
