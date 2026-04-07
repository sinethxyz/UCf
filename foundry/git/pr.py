"""PR creation via GitHub API.

Opens pull requests with structured body, labels, and artifact links
following Foundry PR standards defined in .claude/rules/pr-standards.md.
"""


class PRCreator:
    """Creates and manages pull requests for Foundry runs."""

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
        raise NotImplementedError("Phase 1")

    async def add_comment(self, repo: str, pr_number: int, comment: str) -> None:
        """Add a comment to an existing pull request.

        Args:
            repo: Repository in 'owner/name' format.
            pr_number: The PR number to comment on.
            comment: Markdown comment body.
        """
        raise NotImplementedError("Phase 1")

    async def add_labels(self, repo: str, pr_number: int, labels: list[str]) -> None:
        """Add labels to an existing pull request.

        Args:
            repo: Repository in 'owner/name' format.
            pr_number: The PR number to label.
            labels: List of label names to apply.
        """
        raise NotImplementedError("Phase 1")
