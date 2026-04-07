"""PR creation via GitHub API.

Opens pull requests with structured body, labels, and artifact links
following Foundry PR standards defined in .claude/rules/pr-standards.md.
"""

import logging
import os

from foundry.providers.github import GitHubClient

logger = logging.getLogger(__name__)

# GitHub repo for unicorn-app PRs
UNICORN_APP_REPO = "sinethxyz/unicorn-app"


class PRCreator:
    """Creates and manages pull requests for Foundry runs."""

    def __init__(self, token: str | None = None) -> None:
        self.token = token or os.environ.get("FOUNDRY_GITHUB_TOKEN", "")
        self.client = GitHubClient(token=self.token)

    async def create_pr(
        self,
        repo: str,
        branch: str,
        base_branch: str,
        title: str,
        body: str,
        labels: list[str] | None = None,
    ) -> dict:
        """Create a pull request on GitHub.

        Args:
            repo: Repository in 'owner/name' format.
            branch: Source branch name.
            base_branch: Target branch name (usually 'main').
            title: PR title following '[Foundry] task_type: description' format.
            body: PR body with summary, plan, changes, verification, review, artifacts.
            labels: GitHub labels to apply (always includes 'foundry').

        Returns:
            Dict with 'url' (HTML URL) and 'number' (PR number).
        """
        result = await self.client.create_pull_request(
            repo=repo,
            head=branch,
            base=base_branch,
            title=title,
            body=body,
        )

        # Apply labels
        all_labels = ["foundry", "needs-human-review"]
        if labels:
            all_labels.extend(labels)

        try:
            await self.client.add_pr_labels(repo, result["number"], all_labels)
        except Exception:
            logger.warning("Failed to add labels to PR #%d", result["number"])

        return result

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
