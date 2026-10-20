"""
Gemini LLM Client — wraps google‑genai for the audit agent.
Supports:
  - Function / tool calling (native JSON schema format)
  - Structured JSON output with retry on parse failure
  - Configurable model, temperature, and max tokens
"""

import json
import os
from typing import Any

from google import genai
from google.genai import types

from agent_core.logger import get_logger

logger = get_logger("llm_client")


class GeminiClient:
    """Thin wrapper around the google‑genai SDK for use in the agentic loop."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        temperature: float = 0.2,
        max_output_tokens: int = 8192,
    ) -> None:
        self._api_key = api_key or os.environ["GEMINI_API_KEY"]
        self._model   = model or os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
        self._temperature        = temperature
        self._max_output_tokens  = max_output_tokens
        self._client             = genai.Client(api_key=self._api_key)
        logger.info(f"GeminiClient initialized with model={self._model}")

    # ─────────────────────────────────────────────────────────
    # Core call
    # ─────────────────────────────────────────────────────────
    def generate(
        self,
        contents: list[types.ContentUnionDict],
        tools: list[types.Tool] | None = None,
        system_instruction: str | None = None,
    ) -> types.GenerateContentResponse:
        """Send *contents* to the Gemini model and return the raw response."""
        config_kwargs: dict[str, Any] = {
            "temperature":       self._temperature,
            "max_output_tokens": self._max_output_tokens,
        }
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction
        if tools:
            config_kwargs["tools"] = tools

        config = types.GenerateContentConfig(**config_kwargs)

        logger.debug(f"Sending request to {self._model} with {len(contents)} content parts")
        response = self._client.models.generate_content(
            model    = self._model,
            contents = contents,
            config   = config,
        )
        logger.debug("Response received from Gemini API")
        return response

    # ─────────────────────────────────────────────────────────
    # Convenience: extract text
    # ─────────────────────────────────────────────────────────
    @staticmethod
    def extract_text(response: types.GenerateContentResponse) -> str | None:
        """Return the first text part of the response, or None."""
        try:
            return response.text
        except Exception:
            return None

    # ─────────────────────────────────────────────────────────
    # Convenience: extract tool calls
    # ─────────────────────────────────────────────────────────
    @staticmethod
    def extract_tool_calls(
        response: types.GenerateContentResponse,
    ) -> list[types.FunctionCall]:
        """Return a list of FunctionCall objects from the response (may be empty)."""
        calls = []
        try:
            for part in response.candidates[0].content.parts:
                if part.function_call:
                    calls.append(part.function_call)
        except Exception:
            pass
        return calls

    # ─────────────────────────────────────────────────────────
    # Convenience: parse structured JSON from text response
    # ─────────────────────────────────────────────────────────
    @staticmethod
    def parse_json_response(response: types.GenerateContentResponse) -> dict[str, Any] | None:
        """Attempt to parse JSON from the model text response.
        Strips markdown fences if present.
        """
        text = GeminiClient.extract_text(response)
        if not text:
            return None
        # Strip markdown code fences
        stripped = text.strip()
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            stripped = "\n".join(lines[1:-1]) if len(lines) > 2 else stripped
        try:
            return json.loads(stripped)
        except json.JSONDecodeError as exc:
            logger.warning(f"JSON parse failure: {exc} | raw={text[:200]!r}")
            return None
