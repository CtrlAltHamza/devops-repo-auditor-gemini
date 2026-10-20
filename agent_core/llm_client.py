import os
from typing import Optional, List, Dict, Any
from google import genai
from google.genai import types
from agent_core.logger import get_logger

logger = get_logger("llm_client")


def get_gemini_client(api_key: Optional[str] = None) -> genai.Client:
    """
    Initializes and returns the official Google Gemini SDK client.
    """
    key = api_key or os.getenv("GEMINI_API_KEY")
    if not key:
        raise ValueError(
            "GEMINI_API_KEY is not set. Please provide it in the environment "
            "or in a .env file."
        )
    return genai.Client(api_key=key)


def get_inspection_tools_declaration() -> types.Tool:
    """
    Constructs the tool declarations for the DevOps Auditing Agent.
    Strictly follows Python agent/tool loop requirements without external frameworks.
    """
    declarations = [
        types.FunctionDeclaration(
            name="list_files",
            description="Discover repository files and directory structure.",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "sub_dir": types.Schema(
                        type="STRING",
                        description="Optional sub-directory to inspect relative to repository root."
                    ),
                    "max_depth": types.Schema(
                        type="INTEGER",
                        description="Maximum depth of recursion (default 4)."
                    )
                }
            )
        ),
        types.FunctionDeclaration(
            name="read_file",
            description="Inspect relevant source code or configuration file with line numbers.",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "file_path": types.Schema(
                        type="STRING",
                        description="Relative path of the file to inspect."
                    ),
                    "start_line": types.Schema(
                        type="INTEGER",
                        description="1-indexed starting line number (default: 1)."
                    ),
                    "end_line": types.Schema(
                        type="INTEGER",
                        description="1-indexed ending line number (default: 150)."
                    )
                },
                required=["file_path"]
            )
        ),
        types.FunctionDeclaration(
            name="search_code",
            description="Search repository files for suspicious patterns, hardcoded secrets, or config directives.",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "pattern": types.Schema(
                        type="STRING",
                        description="Regex or substring to search for."
                    ),
                    "file_pattern": types.Schema(
                        type="STRING",
                        description="Optional file name filter (e.g. '*.py', '*.yml', 'Dockerfile')."
                    )
                },
                required=["pattern"]
            )
        ),
        types.FunctionDeclaration(
            name="git_log",
            description="Inspect commit history for commit hygiene or accidental credential commits.",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "max_commits": types.Schema(
                        type="INTEGER",
                        description="Number of recent commits to inspect (default: 15)."
                    )
                }
            )
        ),
        types.FunctionDeclaration(
            name="git_status",
            description="Inspect git status to check for untracked or committed temporary/build artifacts.",
            parameters=types.Schema(
                type="OBJECT",
                properties={}
            )
        )
    ]
    return types.Tool(function_declarations=declarations)
