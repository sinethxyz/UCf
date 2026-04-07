"""Agent SDK wrapper for running subagents.

Wraps the Claude Agent SDK to execute planner, implementer, reviewer,
and extractor subagents with appropriate tool access and system prompts.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from foundry.contracts.review_models import ReviewVerdict
from foundry.contracts.task_types import PlanArtifact, TaskRequest
from foundry.orchestration import prompt_templates
from foundry.orchestration.model_router import resolve_model
from foundry.providers.claude_agent import ClaudeAgentProvider

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool definitions for Anthropic tool_use
# ---------------------------------------------------------------------------

READ_TOOL = {
    "name": "read_file",
    "description": "Read the contents of a file at the given path.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Absolute path to the file to read."},
        },
        "required": ["path"],
    },
}

WRITE_TOOL = {
    "name": "write_file",
    "description": "Write content to a file, creating it if it doesn't exist.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Absolute path to the file."},
            "content": {"type": "string", "description": "Full file content to write."},
        },
        "required": ["path", "content"],
    },
}

BASH_TOOL = {
    "name": "bash",
    "description": "Execute a bash command and return stdout/stderr.",
    "input_schema": {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The bash command to execute."},
        },
        "required": ["command"],
    },
}

LIST_DIR_TOOL = {
    "name": "list_directory",
    "description": "List files in a directory.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Absolute path to the directory."},
        },
        "required": ["path"],
    },
}

SEARCH_TOOL = {
    "name": "search_files",
    "description": "Search for a pattern in files using grep-like search.",
    "input_schema": {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Regex pattern to search for."},
            "path": {"type": "string", "description": "Directory to search in."},
            "glob": {"type": "string", "description": "File glob pattern (e.g. '*.go')."},
        },
        "required": ["pattern", "path"],
    },
}

PLANNER_TOOLS = [READ_TOOL, LIST_DIR_TOOL, SEARCH_TOOL]
IMPLEMENTER_TOOLS = [READ_TOOL, WRITE_TOOL, BASH_TOOL, LIST_DIR_TOOL, SEARCH_TOOL]
REVIEWER_TOOLS: list[dict] = []  # Reviewer has no tools — judges diff only


async def _handle_tool(
    tool_name: str,
    tool_input: dict[str, Any],
    worktree_path: str | None = None,
) -> str:
    """Execute a tool call from the agent, scoped to the worktree."""

    if tool_name == "read_file":
        path = tool_input["path"]
        try:
            return Path(path).read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            return f"Error: File not found: {path}"
        except Exception as e:
            return f"Error reading file: {e}"

    elif tool_name == "write_file":
        path = Path(tool_input["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(tool_input["content"], encoding="utf-8")
        return f"Written {len(tool_input['content'])} bytes to {path}"

    elif tool_name == "bash":
        command = tool_input["command"]
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=worktree_path,
        )
        stdout, stderr = await proc.communicate()
        output = stdout.decode(errors="replace")
        if stderr:
            output += "\nSTDERR:\n" + stderr.decode(errors="replace")
        if proc.returncode != 0:
            output = f"Exit code: {proc.returncode}\n{output}"
        return output[:50000]  # Cap output size

    elif tool_name == "list_directory":
        path = Path(tool_input["path"])
        if not path.is_dir():
            return f"Error: Not a directory: {path}"
        entries = sorted(path.iterdir())
        return "\n".join(
            f"{'d' if e.is_dir() else 'f'} {e.name}" for e in entries[:500]
        )

    elif tool_name == "search_files":
        pattern = tool_input["pattern"]
        search_path = tool_input["path"]
        glob_pattern = tool_input.get("glob", "*")
        proc = await asyncio.create_subprocess_exec(
            "grep", "-rn", "--include", glob_pattern, pattern, search_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return stdout.decode(errors="replace")[:50000]

    return f"Unknown tool: {tool_name}"


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
        tools: list[dict],
        model: str,
        output_schema: type | None = None,
        worktree_path: str | None = None,
    ) -> dict:
        """Execute a Claude subagent with the given configuration.

        Args:
            system_prompt: The system prompt defining the agent's role.
            user_message: The task-specific user message.
            tools: List of Anthropic tool definitions.
            model: Model identifier (e.g. "claude-opus-4-6").
            output_schema: Optional Pydantic model class for structured output
                validation. If provided, the agent's response is validated
                against this schema.
            worktree_path: Optional worktree path for tool execution scoping.

        Returns:
            Parsed structured output from the agent as a dict.
        """
        async def handler(name: str, inp: dict) -> str:
            return await _handle_tool(name, inp, worktree_path)

        result = await self.provider.run(
            system_prompt=system_prompt,
            user_message=user_message,
            tools=tools if tools else None,
            model=model,
            tool_handler=handler if tools else None,
        )

        if output_schema is not None and isinstance(result.get("response"), dict):
            # Validate against Pydantic model
            output_schema.model_validate(result["response"])

        return result

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

        return PlanArtifact.model_validate(result["response"])

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

        # Also include untracked files
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
        user_msg = prompt_templates.build_reviewer_user_message(
            pr_title=pr_title,
            pr_description=pr_description,
            diff=diff,
        )

        result = await self.run_agent(
            system_prompt=prompt_templates.REVIEWER_SYSTEM,
            user_message=user_msg,
            tools=REVIEWER_TOOLS,
            model="claude-opus-4-6",
        )

        return ReviewVerdict.model_validate(result["response"])

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
