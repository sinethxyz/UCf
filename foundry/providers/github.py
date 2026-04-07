"""GitHub REST API client for PR creation and repo operations."""


class GitHubClient:
    """Client for GitHub API interactions.

    Handles pull request creation, commenting, labeling, and
    file listing for Foundry's PR workflow.
    """

    def __init__(self, token: str | None = None) -> None:
        self.token = token

    async def create_pull_request(
        self,
        repo: str,
        head: str,
        base: str,
        title: str,
        body: str,
    ) -> dict:
        """Create a pull request.

        Args:
            repo: Repository in 'owner/name' format.
            head: Source branch.
            base: Target branch.
            title: PR title.
            body: PR body markdown.

        Returns:
            Dict with 'url', 'number', and 'html_url'.
        """
        raise NotImplementedError("Phase 1")

    async def add_pr_comment(self, repo: str, pr_number: int, body: str) -> None:
        """Add a comment to a pull request.

        Args:
            repo: Repository in 'owner/name' format.
            pr_number: PR number.
            body: Comment body markdown.
        """
        raise NotImplementedError("Phase 1")

    async def add_pr_labels(self, repo: str, pr_number: int, labels: list[str]) -> None:
        """Add labels to a pull request.

        Args:
            repo: Repository in 'owner/name' format.
            pr_number: PR number.
            labels: List of label names to apply.
        """
        raise NotImplementedError("Phase 1")

    async def get_pr(self, repo: str, pr_number: int) -> dict:
        """Get pull request details.

        Args:
            repo: Repository in 'owner/name' format.
            pr_number: PR number.

        Returns:
            PR metadata dict.
        """
        raise NotImplementedError("Phase 1")

    async def list_pr_files(self, repo: str, pr_number: int) -> list[dict]:
        """List files changed in a pull request.

        Args:
            repo: Repository in 'owner/name' format.
            pr_number: PR number.

        Returns:
            List of dicts with filename, status, additions, deletions.
        """
        raise NotImplementedError("Phase 1")
