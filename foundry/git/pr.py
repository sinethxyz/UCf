"""PR creation via GitHub API.

Opens pull requests with structured body, labels, and artifact links
following Foundry PR standards defined in .claude/rules/pr-standards.md.
"""

import logging
import os
from uuid import UUID

from foundry.contracts.review_models import ReviewVerdict
from foundry.contracts.task_types import PlanArtifact, TaskRequest
from foundry.providers.github import GitHubClient

logger = logging.getLogger(__name__)

# GitHub repo for unicorn-app PRs
UNICORN_APP_REPO = "sinethxyz/unicorn-app"
UNICORN_FOUNDRY_REPO = "sinethxyz/ucf"


def _build_pr_title(task_request: TaskRequest) -> str:
    """Build PR title following Foundry standards.

    Format: [Foundry] {task_type}: {title}
    """
    return f"[Foundry] {task_request.task_type.value}: {task_request.title}"


def _build_pr_body(
    task_request: TaskRequest,
    plan: PlanArtifact,
    diff: str,
    verification_results: list[dict],
    review_verdict: ReviewVerdict,
    run_id: UUID,
) -> str:
    """Build structured PR body with all required sections.

    Sections: Summary, Plan, Changes, Verification Results,
    Review Verdict, Artifacts, Run Metadata.
    """
    # Summary
    summary = task_request.prompt[:500]

    # Plan section
    risks = ", ".join(plan.risks) if plan.risks else "None identified"
    plan_section = (
        f"Complexity: {plan.estimated_complexity.value}\n"
        f"Steps: {len(plan.steps)}\n"
        f"Risks: {risks}"
    )

    # Changes section
    changes_lines = []
    for step in plan.steps:
        changes_lines.append(f"- `{step.file_path}`: {step.action} — {step.rationale}")
    changes_section = "\n".join(changes_lines) if changes_lines else "No changes listed."

    # Verification section
    if verification_results:
        verification_lines = []
        for result in verification_results:
            check = result.get("check_type", "unknown")
            passed = result.get("passed", False)
            marker = "x" if passed else " "
            verification_lines.append(f"- [{marker}] {check}")
        verification_section = "\n".join(verification_lines)
    else:
        verification_section = "- [x] Verification completed"

    # Review section
    review_verdict_str = review_verdict.verdict.value if review_verdict else "N/A"
    review_summary = review_verdict.summary if review_verdict else "No review"
    review_issues_count = len(review_verdict.issues) if review_verdict else 0

    # Run metadata
    model_used = task_request.model_override or "default"

    body = f"""\
## Summary
{summary}

## Plan
{plan_section}

## Changes
{changes_section}

## Verification
{verification_section}

## Review
Verdict: {review_verdict_str}
Issues: {review_issues_count}
{review_summary}

## Artifacts
- Plan: `runs/{run_id}/plan.json`
- Diff: `runs/{run_id}/diff.patch`
- Verification: `runs/{run_id}/verification.json`
- Review: `runs/{run_id}/review.json`

## Run Metadata
- Run ID: {run_id}
- Task Type: {task_request.task_type.value}
- Model: {model_used}
"""
    return body


def _task_type_label(task_request: TaskRequest) -> str:
    """Derive the GitHub label from the task type."""
    return task_request.task_type.value.replace("_", "-")


def _repo_slug(task_request: TaskRequest) -> str:
    """Determine the GitHub repo slug from the task request."""
    if task_request.repo == "unicorn-app":
        return UNICORN_APP_REPO
    return UNICORN_FOUNDRY_REPO


class PRCreator:
    """Creates and manages pull requests for Foundry runs."""

    def __init__(self, token: str | None = None) -> None:
        self.token = token or os.environ.get("FOUNDRY_GITHUB_TOKEN", "")
        self.client = GitHubClient(token=self.token)

    async def create_pr(
        self,
        task_request: TaskRequest,
        plan: PlanArtifact,
        diff: str,
        verification_results: list[dict],
        review_verdict: ReviewVerdict,
        run_id: UUID,
        branch_name: str,
        base_branch: str,
    ) -> dict:
        """Create a pull request on GitHub with structured body from artifacts.

        Builds the PR title and body from the provided task artifacts,
        creates the PR via the GitHub API, and applies standard labels.

        Args:
            task_request: Original task request.
            plan: The plan artifact for inclusion in PR body.
            diff: The git diff of all changes.
            verification_results: List of verification check result dicts
                with keys 'check_type', 'passed', 'output', 'duration_ms'.
            review_verdict: The review verdict for inclusion in PR body.
            run_id: ID of the current run.
            branch_name: Source branch name.
            base_branch: Target branch name (usually 'main').

        Returns:
            Dict with 'url' (HTML URL) and 'number' (PR number).
        """
        title = _build_pr_title(task_request)
        body = _build_pr_body(
            task_request, plan, diff, verification_results,
            review_verdict, run_id,
        )
        repo = _repo_slug(task_request)

        result = await self.client.create_pull_request(
            repo=repo,
            head=branch_name,
            base=base_branch,
            title=title,
            body=body,
        )

        # Apply labels: always "foundry" + "needs-human-review" + task type
        labels = ["foundry", "needs-human-review", _task_type_label(task_request)]
        try:
            await self.client.add_pr_labels(repo, result["number"], labels)
        except Exception:
            logger.warning("Failed to add labels to PR #%d", result["number"])

        return {"url": result["url"], "number": result["number"]}

    async def add_comment(self, repo: str, pr_number: int, comment: str) -> None:
        """Add a comment to an existing pull request.

        Args:
            repo: Repository in 'owner/name' format.
            pr_number: The PR number to comment on.
            comment: Markdown comment body.
        """
        await self.client.add_pr_comment(repo, pr_number, comment)

    async def add_labels(self, repo: str, pr_number: int, labels: list[str]) -> None:
        """Add labels to an existing pull request.

        Args:
            repo: Repository in 'owner/name' format.
            pr_number: The PR number to label.
            labels: List of label names to apply.
        """
        await self.client.add_pr_labels(repo, pr_number, labels)
