"""Task implementation: review_diff.

Independent code review of a diff without access to the plan.
Produces a ReviewVerdict artifact. This IS the review — it does not
itself get reviewed.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING
from uuid import UUID

from foundry.contracts.review_models import ReviewVerdict
from foundry.contracts.shared import MCPProfile, TaskType
from foundry.contracts.task_types import TaskRequest
from foundry.orchestration.agent_runner import AgentRunner
from foundry.storage.artifact_store import ArtifactStore, ArtifactType
from foundry.tasks import TaskExecutor, register_task

if TYPE_CHECKING:
    from foundry.orchestration.run_engine import RunEngine

logger = logging.getLogger(__name__)


async def execute_standalone_review(
    diff: str,
    title: str,
    description: str,
    run_id: UUID | None = None,
    artifact_store: ArtifactStore | None = None,
) -> ReviewVerdict:
    """Execute a standalone blind diff review outside the run lifecycle.

    This function can be called directly from the /reviews debug endpoint
    or from any context that needs an independent code review without
    spinning up a full run.

    The reviewer sees ONLY the diff, title, and description. It never
    receives a PlanArtifact — this prevents confirmation bias.

    Args:
        diff: The git diff to review.
        title: PR or change title for context.
        description: PR or change description for context.
        run_id: Optional run ID for artifact storage.
        artifact_store: Optional artifact store for persisting the review.

    Returns:
        ReviewVerdict with verdict, issues, summary, and confidence.
    """
    # Extract changed files from the diff for additional context
    changed_files: list[str] = []
    for line in diff.split("\n"):
        if line.startswith("diff --git"):
            parts = line.split(" b/", 1)
            if len(parts) == 2:
                changed_files.append(parts[1])

    runner = AgentRunner()
    verdict = await runner.run_reviewer(
        diff=diff,
        pr_title=title,
        pr_description=description,
        changed_files=changed_files,
    )

    # Persist review artifact if run_id and store are provided
    if run_id is not None and artifact_store is not None:
        review_json = verdict.model_dump_json(indent=2)
        await artifact_store.store(
            run_id, ArtifactType.REVIEW, review_json,
        )

    return verdict


@register_task(TaskType.REVIEW_DIFF)
class ReviewDiffTask(TaskExecutor):
    """Performs standalone independent code review of a diff.

    Uses Opus for high-quality review reasoning. The reviewer does NOT
    have access to the original plan — it judges the diff purely on its
    own merits to prevent confirmation bias.

    Workflow:
    1. Load: Read the diff from task_request metadata or worktree.
    2. Analyze: Review the diff for correctness, safety, performance,
       test coverage, API contract compliance, and style.
    3. Verdict: Produce a ReviewVerdict (approve / request_changes / reject)
       with categorized issues (critical, major, minor, nit).
    4. Store: Persist the ReviewVerdict as an artifact.
    """

    default_model = "claude-opus-4-6"
    mcp_profile = MCPProfile.GITHUB_ONLY
    requires_verification = False
    requires_review = False

    async def execute(
        self,
        run_engine: RunEngine,
        run_id: UUID,
        task_request: TaskRequest,
        worktree_path: str,
    ) -> dict:
        """Execute a diff review task.

        Loads the diff from task_request.metadata["diff"] or from the
        worktree's uncommitted changes. Runs the blind reviewer and
        stores the ReviewVerdict as an artifact.

        Args:
            run_engine: The RunEngine instance for artifact storage.
            run_id: Unique identifier for this run.
            task_request: Task request with diff in metadata or prompt.
            worktree_path: Path to the worktree for fallback diff extraction.

        Returns:
            Dict with verdict data and metadata.
        """
        # 1. Load diff: prefer metadata, fall back to worktree git diff
        diff = task_request.metadata.get("diff", "")
        if not diff:
            proc = await asyncio.create_subprocess_exec(
                "git", "diff", "HEAD",
                cwd=worktree_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            diff = stdout.decode(errors="replace")

        if not diff.strip():
            raise ValueError("No diff provided and no changes found in worktree")

        # 2. Build PR title/description from task request
        pr_title = f"[Foundry] review diff: {task_request.title}"
        pr_description = task_request.prompt[:500]

        # 3. Run blind review with artifact storage
        verdict = await execute_standalone_review(
            diff=diff,
            title=pr_title,
            description=pr_description,
            run_id=run_id,
            artifact_store=run_engine.artifact_store,
        )

        return {
            "verdict": verdict.verdict.value,
            "issues_count": len(verdict.issues),
            "critical_count": sum(
                1 for i in verdict.issues if i.severity.value == "critical"
            ),
            "major_count": sum(
                1 for i in verdict.issues if i.severity.value == "major"
            ),
            "summary": verdict.summary,
            "confidence": verdict.confidence,
        }

    async def get_plan_prompt(self, task_request: TaskRequest) -> str:
        """Generate planning prompt for review diff.

        Review tasks don't use a traditional planning phase — the review
        itself is the entire task. Returns a prompt describing the review
        criteria and output format.

        Args:
            task_request: The task request to build a plan prompt for.

        Returns:
            Prompt string describing the review task.
        """
        return (
            f"Review the diff for: {task_request.title}\n\n"
            f"Description: {task_request.prompt}\n\n"
            "This is a review-only task. No planning is needed. "
            "The reviewer will independently assess the diff for "
            "correctness, safety, contract compliance, test coverage, "
            "and adherence to conventions."
        )
