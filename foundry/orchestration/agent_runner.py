"""Agent SDK wrapper for running subagents.

Wraps the Claude Agent SDK to execute planner, implementer, reviewer,
and extractor subagents with appropriate tool access and system prompts.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Literal

from foundry.contracts.review_models import ReviewVerdict
from foundry.contracts.shared import TaskType
from foundry.contracts.task_types import PlanArtifact, TaskRequest
from foundry.orchestration import prompt_templates
from foundry.orchestration.model_router import resolve_model
from foundry.providers.claude_agent import ClaudeAgentProvider

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool configurations for each subagent role.
# Tools are specified as string names matching the Agent SDK's built-in tools.
# The working_directory parameter scopes file operations at runtime.
# ---------------------------------------------------------------------------

PLANNER_TOOLS: list[str] = ["Read", "Grep", "Glob"]
IMPLEMENTER_TOOLS: list[str] = ["Read", "Write", "Edit", "Bash", "Grep", "Glob"]
REVIEWER_TOOLS: list[str] = []  # Reviewer has no tools — judges diff only


class AgentRunner:
    """Wraps the Anthropic Agent SDK to run subagents with specific roles.

    Each subagent gets its own context window, tool access list, and system
    prompt. The runner handles serialization of structured outputs and
    validation against expected schemas.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self.provider = ClaudeAgentProvider(api_key=api_key)

    async def run_agent(
        self,
        system_prompt: str,
        user_message: str,
        tools: list[str],
        model: str,
        output_schema: type | None = None,
        worktree_path: str | None = None,
    ) -> dict:
        """Execute a Claude subagent with the given configuration.

        Delegates to the ClaudeAgentProvider. When output_schema is provided,
        uses run_with_structured_output for validated JSON responses.
        Otherwise uses run for free-form text/JSON responses.

        Args:
            system_prompt: The system prompt defining the agent's role.
            user_message: The task-specific user message.
            tools: List of tool name strings (e.g. ["Read", "Grep", "Glob"]).
            model: Model identifier (e.g. "claude-opus-4-6").
            output_schema: Optional Pydantic model class for structured output
                validation. If provided, the agent's response is validated
                against this schema.
            worktree_path: Optional worktree path for tool execution scoping.

        Returns:
            Agent result dict with response and metadata.
        """
        if output_schema is not None:
            return await self.provider.run_with_structured_output(
                system_prompt=system_prompt,
                user_message=user_message,
                model=model,
                output_schema=output_schema,
                tools=tools if tools else None,
                working_directory=worktree_path,
            )

        return await self.provider.run(
            system_prompt=system_prompt,
            user_message=user_message,
            model=model,
            tools=tools if tools else None,
            working_directory=worktree_path,
        )

    async def run_planner(
        self,
        task_request: TaskRequest,
        worktree_path: str,
    ) -> PlanArtifact:
        """Run the planner subagent to produce a structured implementation plan.

        The planner has read-only access (Read, Grep, Glob) scoped to the
        worktree and produces a PlanArtifact with ordered steps, risks, and
        open questions.

        Args:
            task_request: The task to plan for.
            worktree_path: Path to the worktree for repo exploration.

        Returns:
            Validated PlanArtifact.
        """
        model = resolve_model(task_request.task_type, "planner")
        user_msg = prompt_templates.build_planner_user_message(
            task_id=str(task_request.metadata.get("run_id", "unknown")),
            task_type=task_request.task_type.value,
            title=task_request.title,
            prompt=task_request.prompt,
            target_paths=task_request.target_paths,
        )

        result = await self.run_agent(
            system_prompt=prompt_templates.PLANNER_SYSTEM,
            user_message=user_msg,
            tools=PLANNER_TOOLS,
            model=model,
            output_schema=PlanArtifact,
            worktree_path=worktree_path,
        )

        response = result["response"]
        if isinstance(response, PlanArtifact):
            return response
        return PlanArtifact.model_validate(response)

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
        if language == "go":
            system_prompt = prompt_templates.BACKEND_IMPLEMENTER_SYSTEM
        else:
            system_prompt = prompt_templates.FRONTEND_IMPLEMENTER_SYSTEM

        model = resolve_model(task_request.task_type, "implementer")
        plan_json = plan.model_dump_json(indent=2)
        user_msg = prompt_templates.build_implementer_user_message(
            plan_json=plan_json,
            task_title=task_request.title,
        )

        await self.run_agent(
            system_prompt=system_prompt,
            user_message=user_msg,
            tools=IMPLEMENTER_TOOLS,
            model=model,
            worktree_path=worktree_path,
        )

        # Capture the diff from the worktree
        proc = await asyncio.create_subprocess_exec(
            "git", "diff", "HEAD",
            cwd=worktree_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        diff = stdout.decode(errors="replace")

        # Also include staged changes
        proc2 = await asyncio.create_subprocess_exec(
            "git", "diff", "--cached",
            cwd=worktree_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout2, _ = await proc2.communicate()
        cached_diff = stdout2.decode(errors="replace")

        full_diff = diff + cached_diff
        if not full_diff.strip():
            # Try git status to see what happened
            proc3 = await asyncio.create_subprocess_exec(
                "git", "status", "--porcelain",
                cwd=worktree_path,
                stdout=asyncio.subprocess.PIPE,
            )
            stdout3, _ = await proc3.communicate()
            logger.warning("No diff found. Git status: %s", stdout3.decode())

        return full_diff

    async def run_reviewer(
        self,
        diff: str,
        pr_title: str,
        pr_description: str,
        changed_files: list[str] | None = None,
    ) -> ReviewVerdict:
        """Run the reviewer subagent to independently review a diff.

        CRITICAL: The reviewer does NOT receive the PlanArtifact. It judges
        the diff on its own merits to prevent confirmation bias. It sees
        ONLY: the diff, the PR title, the PR description, and optionally
        the list of changed files.

        Args:
            diff: The git diff to review.
            pr_title: Title of the proposed PR.
            pr_description: Description of the proposed PR.
            changed_files: Optional list of changed file paths for context.

        Returns:
            ReviewVerdict with verdict, issues list, summary, and confidence.
        """
        model = resolve_model(TaskType.REVIEW_DIFF, "reviewer")

        user_msg = prompt_templates.build_reviewer_user_message(
            pr_title=pr_title,
            pr_description=pr_description,
            diff=diff,
        )

        # Append changed file list for additional context (never the plan)
        if changed_files:
            files_str = "\n".join(f"- {f}" for f in changed_files)
            user_msg += f"\n\nChanged files:\n{files_str}"

        result = await self.run_agent(
            system_prompt=prompt_templates.REVIEWER_SYSTEM,
            user_message=user_msg,
            tools=REVIEWER_TOOLS,
            model=model,
            output_schema=ReviewVerdict,
        )

        response = result["response"]
        if isinstance(response, ReviewVerdict):
            return response
        return ReviewVerdict.model_validate(response)

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
        user_msg = f"Review this diff for migration safety:\n\n```\n{diff}\n```"

        result = await self.run_agent(
            system_prompt=prompt_templates.MIGRATION_GUARD_SYSTEM,
            user_message=user_msg,
            tools=REVIEWER_TOOLS,
            model="claude-opus-4-6",
        )

        return ReviewVerdict.model_validate(result["response"])

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
        user_msg = f"Explore the repository at: {target_path}\nWorktree root: {worktree_path}"

        result = await self.run_agent(
            system_prompt=prompt_templates.REPO_EXPLORER_SYSTEM,
            user_message=user_msg,
            tools=PLANNER_TOOLS,
            model="claude-haiku-4-5-20251001",
            worktree_path=worktree_path,
        )

        return result.get("response", {})
