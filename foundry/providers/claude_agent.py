"""Claude Agent SDK integration.

Wraps the Agent SDK for agentic task execution (planning, implementation,
review). Used by the orchestrator for interactive, tool-using runs.
"""

from typing import Any


class ClaudeAgentProvider:
    """Provider for Claude Agent SDK interactions.

    Used for agentic workflows where Claude needs tools: planning,
    implementation, and review subagents.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key

    async def run(
        self,
        system_prompt: str,
        user_message: str,
        tools: list[str] | None = None,
        model: str = "claude-sonnet-4-6",
        output_schema: dict[str, Any] | None = None,
        mcp_profile: str | None = None,
    ) -> dict:
        """Run an agent session with optional tools and structured output.

        Args:
            system_prompt: System instructions for the agent.
            user_message: The user-facing prompt to execute.
            tools: List of tool names the agent can use.
            model: Model identifier (default: claude-sonnet-4-6).
            output_schema: Optional JSON Schema to constrain output.
            mcp_profile: Optional MCP profile name for tool access.

        Returns:
            Agent output as a dict containing response and metadata.
        """
        raise NotImplementedError("Phase 1")

    async def run_with_structured_output(
        self,
        system_prompt: str,
        user_message: str,
        model: str,
        output_schema: dict[str, Any],
    ) -> dict:
        """Run an agent session that must return structured output.

        Args:
            system_prompt: System instructions for the agent.
            user_message: The user-facing prompt to execute.
            model: Model identifier.
            output_schema: JSON Schema the output must conform to.

        Returns:
            Validated structured output as a dict.
        """
        raise NotImplementedError("Phase 1")
