"""Agent SDK wrapper for running subagents.

Wraps the Claude Agent SDK to execute planner, implementer, reviewer,
and extractor subagents with appropriate tool access and system prompts.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from foundry.contracts.review_models import ReviewVerdict
from foundry.contracts.task_types import PlanArtifact, TaskRequest

logger = logging.getLogger(__name__)


class AgentRunner:
    """Wraps the Anthropic Agent SDK to run subagents with specific roles.

    Each subagent gets its own context window, tool access list, and system
    prompt. The runner handles serialization of structured outputs and
    validation against expected schemas.
    """

    def __init__(self) -> None:
        pass

    async def run_agent(
        self,
        system_prompt: str,
        user_message: str,
        tools: list[str],
        model: str,
        output_schema: type | None = None,
    ) -> dict:
        """Execute a Claude subagent with the given configuration.

        Args:
            system_prompt: The system prompt defining the agent's role.
            user_message: The task-specific user message.
            tools: List of tool names the agent is allowed to use.
            model: Model identifier (e.g. "claude-opus-4-6").
            output_schema: Optional Pydantic model class for structured output
                validation. If provided, the agent's response is validated
                against this schema.

        Returns:
            Parsed structured output from the agent as a dict.
        """
        raise NotImplementedError("Agent execution not yet implemented")

    async def run_planner(
        self,
        task_request: TaskRequest,
        worktree_path: str,
    ) -> PlanArtifact:
        """Run the planner subagent to produce a structured implementation plan.

        The planner has read-only access to the worktree and produces a
        PlanArtifact with ordered steps, risks, and open questions.

        Args:
            task_request: The task to plan for.
            worktree_path: Path to the worktree for repo exploration.

        Returns:
            Validated PlanArtifact.
        """
        raise NotImplementedError("Planner agent not yet implemented")

    async def run_implementer(
        self,
        plan: PlanArtifact,
        task_request: TaskRequest,
        worktree_path: str,
        language: Literal["go", "typescript"],
    ) -> str:
        """Run the implementer subagent to execute a plan.

        Selects the backend (Go) or frontend (TypeScript) implementer based
        on the language parameter. The implementer has write access to the
        worktree and restricted Bash access.

        Args:
            plan: The validated implementation plan.
            task_request: Original task request for context.
            worktree_path: Path to the worktree where edits are made.
            language: Target language — determines which implementer to use.

        Returns:
            The git diff of all changes made by the implementer.
        """
        raise NotImplementedError("Implementer agent not yet implemented")

    async def run_reviewer(
        self,
        diff: str,
        pr_title: str,
        pr_description: str,
    ) -> ReviewVerdict:
        """Run the reviewer subagent to independently review a diff.

        The reviewer does NOT receive the plan — it judges the diff on its
        own merits to prevent confirmation bias.

        Args:
            diff: The git diff to review.
            pr_title: Title of the proposed PR.
            pr_description: Description of the proposed PR.

        Returns:
            ReviewVerdict with verdict, issues list, and summary.
        """
        raise NotImplementedError("Reviewer agent not yet implemented")

    async def run_migration_guard(
        self,
        diff: str,
    ) -> ReviewVerdict:
        """Run the migration guard subagent for high-scrutiny review.

        Automatically invoked when changes touch protected paths: migrations/,
        auth/, infra/, *.env*, docker-compose*, Dockerfile*.

        Args:
            diff: The git diff to review for migration safety.

        Returns:
            ReviewVerdict with migration-specific safety assessment.
        """
        raise NotImplementedError("Migration guard agent not yet implemented")

    async def run_repo_explorer(
        self,
        target_path: str,
        worktree_path: str,
    ) -> dict:
        """Run the repo explorer subagent for read-only reconnaissance.

        Discovers patterns, conventions, module structure, and test
        conventions in the target area of the repository.

        Args:
            target_path: Relative path within the repo to explore.
            worktree_path: Path to the worktree root.

        Returns:
            Structured JSON summary of discovered patterns.
        """
        raise NotImplementedError("Repo explorer agent not yet implemented")
