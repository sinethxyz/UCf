"""Raw Claude Messages API integration.

Used for non-agentic, single-turn interactions: extraction, classification,
eval scoring. Supports structured output mode.
"""


class ClaudeMessagesProvider:
    """Provider for Claude Messages API."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key

    async def create_message(
        self,
        model: str,
        system: str,
        messages: list[dict],
        max_tokens: int = 4096,
    ) -> dict:
        """Send a message to the Claude API.

        Args:
            model: Model identifier.
            system: System prompt.
            messages: Message list.
            max_tokens: Maximum response tokens.

        Returns:
            API response as dict.
        """
        raise NotImplementedError
