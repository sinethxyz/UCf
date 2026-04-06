"""Claude Agent SDK integration.

Wraps the Agent SDK for agentic task execution (planning, implementation,
review). Used by the orchestrator for interactive, tool-using runs.
"""


class ClaudeAgentProvider:
    """Provider for Claude Agent SDK interactions."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key

    async def create_agent(
        self,
        model: str,
        system_prompt: str,
        tools: list[str] | None = None,
    ) -> dict:
        """Create and run an agent session.

        Args:
            model: Model identifier.
            system_prompt: System instructions for the agent.
            tools: List of tool names the agent can use.

        Returns:
            Agent output as structured dict.
        """
        raise NotImplementedError
