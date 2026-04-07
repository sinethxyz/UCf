"""Claude Agent SDK integration.

Wraps the Agent SDK for agentic task execution (planning, implementation,
review). Used by the orchestrator for interactive, tool-using runs.
"""

import json
import logging
import time
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

logger = logging.getLogger(__name__)


class ClaudeAgentProvider:
    """Provider for Claude Agent SDK interactions.

    Used for agentic workflows where Claude needs tools: planning,
    implementation, and review subagents.

    Creates agent sessions via the Claude Agent SDK's ``query()`` function.
    Each run gets a fresh session with the specified system prompt, model,
    tools, and optional structured output schema.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key

    async def _collect_result(
        self, prompt: str, options: ClaudeAgentOptions
    ) -> ResultMessage:
        """Run a query and collect the final ResultMessage from the stream."""
        result_msg: ResultMessage | None = None
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, ResultMessage):
                result_msg = message

        if result_msg is None:
            raise RuntimeError("Agent session ended without a ResultMessage")
        if result_msg.is_error:
            errors = ", ".join(result_msg.errors or ["Unknown error"])
            raise RuntimeError(f"Agent session failed: {errors}")

        return result_msg

    async def run(
        self,
        system_prompt: str,
        user_message: str,
        model: str = "claude-sonnet-4-6",
        tools: list[str] | None = None,
        working_directory: str | None = None,
    ) -> dict:
        """Run an agent session with optional tools.

        Creates an agent via the Claude Agent SDK with the given system
        prompt, model, and tools. Runs the agent with the user message.

        Args:
            system_prompt: System instructions for the agent.
            user_message: The user-facing prompt to execute.
            model: Model identifier (default: claude-sonnet-4-6).
            tools: List of tool names (e.g. ["Read", "Grep", "Glob"]).
            working_directory: Working directory for tool execution scoping.

        Returns:
            Dict with keys: response, raw_text, model, tokens_in,
            tokens_out, duration_ms.
        """
        start = time.monotonic()

        options = ClaudeAgentOptions(
            system_prompt=system_prompt,
            model=model,
            tools=tools or [],
            cwd=working_directory,
            permission_mode="bypassPermissions",
            max_turns=50,
        )

        result_msg = await self._collect_result(user_message, options)
        duration_ms = int((time.monotonic() - start) * 1000)

        # Extract text output and attempt JSON parse
        text = result_msg.result or ""
        parsed: Any = text
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            pass

        # Extract token counts from usage dict
        usage = result_msg.usage or {}
        tokens_in = usage.get("input_tokens", 0)
        tokens_out = usage.get("output_tokens", 0)

        return {
            "response": parsed,
            "raw_text": text,
            "model": model,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "duration_ms": duration_ms,
        }

    async def run_with_structured_output(
        self,
        system_prompt: str,
        user_message: str,
        model: str,
        output_schema: type,
        tools: list[str] | None = None,
        working_directory: str | None = None,
    ) -> dict:
        """Run an agent session that must return structured output.

        Uses the Agent SDK's output_format parameter with a JSON schema
        derived from the provided Pydantic model. Validates the response
        against the schema after parsing.

        Args:
            system_prompt: System instructions for the agent.
            user_message: The user-facing prompt to execute.
            model: Model identifier.
            output_schema: Pydantic model class for output validation.
            tools: List of tool names (e.g. ["Read", "Grep", "Glob"]).
            working_directory: Working directory for tool execution scoping.

        Returns:
            Dict with keys: response (validated Pydantic instance), model,
            tokens_in, tokens_out, duration_ms.
        """
        start = time.monotonic()

        # Derive JSON schema from Pydantic model for the SDK
        json_schema = output_schema.model_json_schema()

        options = ClaudeAgentOptions(
            system_prompt=system_prompt,
            model=model,
            tools=tools or [],
            output_format=json_schema,
            cwd=working_directory,
            permission_mode="bypassPermissions",
            max_turns=50,
        )

        result_msg = await self._collect_result(user_message, options)
        duration_ms = int((time.monotonic() - start) * 1000)

        # Parse structured output — prefer structured_output if the SDK
        # populated it, otherwise fall back to parsing result text.
        output = result_msg.structured_output
        if output is None:
            raw = result_msg.result or ""
            try:
                output = json.loads(raw)
            except (json.JSONDecodeError, TypeError) as exc:
                raise ValueError(
                    f"Expected structured JSON output but got: {raw[:200]}"
                ) from exc

        # Validate response against the Pydantic model.
        # Use model_validate_json for dict→JSON round-trip to handle
        # strict-mode coercion (e.g. UUID strings).
        if isinstance(output, output_schema):
            validated = output
        elif isinstance(output, dict):
            validated = output_schema.model_validate_json(json.dumps(output))
        else:
            validated = output_schema.model_validate_json(
                output if isinstance(output, str) else json.dumps(output)
            )

        # Extract token counts from usage dict
        usage = result_msg.usage or {}
        tokens_in = usage.get("input_tokens", 0)
        tokens_out = usage.get("output_tokens", 0)

        return {
            "response": validated,
            "model": model,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "duration_ms": duration_ms,
        }
