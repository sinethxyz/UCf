"""Agent SDK wrapper for running subagents.

Wraps the Claude Agent SDK to execute planner, implementer, reviewer,
and extractor subagents with appropriate tool access and system prompts.
"""


class AgentRunner:
    """Runs a Claude subagent with configured tools and prompts."""

    def __init__(self, agent_type: str, model: str, tools: list[str] | None = None) -> None:
        self.agent_type = agent_type
        self.model = model
        self.tools = tools or []

    async def run(self, prompt: str, system_prompt: str | None = None) -> dict:
        """Execute the subagent and return its output.

        Args:
            prompt: The task prompt for the agent.
            system_prompt: Optional system prompt override.

        Returns:
            Structured output from the agent.
        """
        raise NotImplementedError("Agent runner not yet implemented")
