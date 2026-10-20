"""
Gemini LLM Client — wraps google‑genai for the audit agent.
Supports:
  - Function / tool calling (native JSON schema format)
  - Structured JSON output with retry on parse failure
  - Configurable model, temperature, and max tokens
"""

import json
import os
import re
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
        self._model   = model or os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
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
        max_retries: int = 5,
    ) -> types.GenerateContentResponse:
        """Send *contents* to the Gemini model and return the raw response with automatic 429 retry."""
        import time

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
        for attempt in range(max_retries):
            try:
                response = self._client.models.generate_content(
                    model    = self._model,
                    contents = contents,
                    config   = config,
                )
                logger.debug("Response received from Gemini API")
                return response
            except Exception as exc:
                err_str = str(exc)
                # If a specific model hit its daily project quota, switch to an alternative flash model
                if "PerDay" in err_str or "GenerateRequestsPerDay" in err_str:
                    fallbacks = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.7-flash", "gemini-3.5-flash"]
                    next_models = [m for m in fallbacks if m != self._model]
                    if next_models:
                        new_model = next_models[0]
                        logger.warning(
                            f"Daily quota reached on {self._model}. Seamlessly failing over to {new_model}..."
                        )
                        self._model = new_model
                        time.sleep(2)
                        continue

                if ("429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "503" in err_str) and attempt < max_retries - 1:
                    wait_time = 5 * (attempt + 1)
                    logger.warning(
                        f"API rate limit or temporary server error encountered. Waiting {wait_time}s before retry (attempt {attempt + 1}/{max_retries})..."
                    )
                    time.sleep(wait_time)
                else:
                    raise



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
        except (AttributeError, IndexError, TypeError):
            # Response had no candidates/parts (e.g. blocked or empty) — treat as no tool calls
            return []
        return calls

    # ─────────────────────────────────────────────────────────
    # Convenience: parse structured JSON from text response
    # ─────────────────────────────────────────────────────────
    @staticmethod
    def parse_json_response(response: types.GenerateContentResponse) -> dict[str, Any] | None:
        """Attempt to parse JSON from the model text response.
        Uses direct parsing, code fence extraction, and outermost JSON object regex matching.
        """
        text = GeminiClient.extract_text(response)
        if not text:
            return None
        stripped = text.strip()

        # 1. Direct JSON parse
        try:
            res = json.loads(stripped)
            if isinstance(res, dict):
                return res
        except json.JSONDecodeError:
            pass

        # 2. Markdown code fence extraction: ```(?:json)? ... ```
        fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", stripped)
        if fence_match:
            try:
                res = json.loads(fence_match.group(1).strip())
                if isinstance(res, dict):
                    return res
            except json.JSONDecodeError:
                pass

        # 3. Match outermost JSON object {...}
        obj_match = re.search(r"(\{[\s\S]*\})", stripped)
        if obj_match:
            try:
                res = json.loads(obj_match.group(1).strip())
                if isinstance(res, dict):
                    return res
            except json.JSONDecodeError:
                pass

        logger.warning(f"JSON parse failure | raw={text[:200]!r}")
        return None
