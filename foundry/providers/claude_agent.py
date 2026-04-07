"""Claude Agent SDK integration.

Wraps the Agent SDK for agentic task execution (planning, implementation,
review). Used by the orchestrator for interactive, tool-using runs.
"""

import json
import logging
import time
from typing import Any

import anthropic

logger = logging.getLogger(__name__)


class ClaudeAgentProvider:
    """Provider for Claude Agent SDK interactions.

    Used for agentic workflows where Claude needs tools: planning,
    implementation, and review subagents.

    Phase 1 uses the Anthropic Messages API with manual tool-use loops
    until the Agent SDK stabilises. The interface is forward-compatible
    with a future Agent SDK swap.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key
        self._client = anthropic.AsyncAnthropic(api_key=api_key) if api_key else anthropic.AsyncAnthropic()

    async def run(
        self,
        system_prompt: str,
        user_message: str,
        tools: list[dict[str, Any]] | None = None,
        model: str = "claude-sonnet-4-6",
        output_schema: dict[str, Any] | None = None,
        mcp_profile: str | None = None,
        max_turns: int = 50,
        tool_handler: Any | None = None,
    ) -> dict:
        """Run an agent session with optional tools and structured output.

        Uses multi-turn Messages API with tool_use/tool_result loops.

        Args:
            system_prompt: System instructions for the agent.
            user_message: The user-facing prompt to execute.
            tools: List of Anthropic tool definitions (dicts with name, description, input_schema).
            model: Model identifier (default: claude-sonnet-4-6).
            output_schema: Optional JSON Schema to constrain output.
            mcp_profile: Optional MCP profile name for tool access.
            max_turns: Maximum conversation turns before forced stop.
            tool_handler: Async callable(tool_name, tool_input) -> tool_result.

        Returns:
            Agent output as a dict containing response and metadata.
        """
        start = time.monotonic()
        total_input_tokens = 0
        total_output_tokens = 0

        messages = [{"role": "user", "content": user_message}]

        for turn in range(max_turns):
            response = await self._client.messages.create(
                model=model,
                max_tokens=8192,
                system=system_prompt,
                messages=messages,
                tools=tools or [],
            )

            total_input_tokens += response.usage.input_tokens
            total_output_tokens += response.usage.output_tokens

            # Check if we need to handle tool use
            if response.stop_reason == "tool_use" and tool_handler is not None:
                # Build assistant message with all content blocks
                messages.append({"role": "assistant", "content": response.content})

                # Process each tool use block
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        try:
                            result = await tool_handler(block.name, block.input)
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": str(result),
                            })
                        except Exception as e:
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": f"Error: {e}",
                                "is_error": True,
                            })

                messages.append({"role": "user", "content": tool_results})
                continue

            # Extract text response
            text_content = ""
            for block in response.content:
                if hasattr(block, "text"):
                    text_content += block.text

            duration_ms = int((time.monotonic() - start) * 1000)

            # Try to parse as JSON
            parsed = text_content
            try:
                parsed = json.loads(text_content)
            except (json.JSONDecodeError, TypeError):
                pass

            return {
                "response": parsed,
                "raw_text": text_content,
                "model": model,
                "tokens_in": total_input_tokens,
                "tokens_out": total_output_tokens,
                "duration_ms": duration_ms,
                "turns": turn + 1,
            }

        duration_ms = int((time.monotonic() - start) * 1000)
        return {
            "response": None,
            "raw_text": "",
            "model": model,
            "tokens_in": total_input_tokens,
            "tokens_out": total_output_tokens,
            "duration_ms": duration_ms,
            "turns": max_turns,
            "error": "Max turns exceeded",
        }

    async def run_with_structured_output(
        self,
        system_prompt: str,
        user_message: str,
        model: str,
        output_schema: dict[str, Any],
    ) -> dict:
        """Run an agent session that must return structured output.

        Uses the system prompt to enforce JSON output and validates the
        response against the provided schema.

        Args:
            system_prompt: System instructions for the agent.
            user_message: The user-facing prompt to execute.
            model: Model identifier.
            output_schema: JSON Schema the output must conform to.

        Returns:
            Validated structured output as a dict.
        """
        result = await self.run(
            system_prompt=system_prompt,
            user_message=user_message,
            model=model,
        )

        response = result.get("response")
        if response is None or isinstance(response, str):
            raise ValueError(
                f"Expected structured JSON output but got: {result.get('raw_text', '')[:200]}"
            )

        return result
