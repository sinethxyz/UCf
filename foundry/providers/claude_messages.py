"""Raw Claude Messages API integration.

Used for non-agentic, single-turn interactions: extraction, classification,
eval scoring. Supports structured output mode.
"""

from typing import Any


class ClaudeMessagesProvider:
    """Provider for Claude Messages API.

    Used for single-turn completions where tool use is not needed.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key

    async def send(
        self,
        system_prompt: str,
        user_message: str,
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 4096,
    ) -> dict:
        """Send a single-turn message to the Claude API.

        Args:
            system_prompt: System prompt.
            user_message: User message content.
            model: Model identifier (default: claude-sonnet-4-6).
            max_tokens: Maximum response tokens.

        Returns:
            API response as dict with content and usage metadata.
        """
        raise NotImplementedError("Phase 1")

    async def send_structured(
        self,
        system_prompt: str,
        user_message: str,
        model: str,
        output_schema: dict[str, Any],
    ) -> dict:
        """Send a message expecting structured JSON output.

        Args:
            system_prompt: System prompt.
            user_message: User message content.
            model: Model identifier.
            output_schema: JSON Schema the output must conform to.

        Returns:
            Validated structured output as a dict.
        """
        raise NotImplementedError("Phase 1")
