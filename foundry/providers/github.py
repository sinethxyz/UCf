"""GitHub REST/GraphQL client for PR creation and repo operations."""


class GitHubProvider:
    """Provider for GitHub API interactions."""

    def __init__(self, token: str | None = None) -> None:
        self.token = token

    async def create_pull_request(
        self,
        repo: str,
        head: str,
        base: str,
        title: str,
        body: str,
        labels: list[str] | None = None,
    ) -> dict:
        """Create a pull request.

        Args:
            repo: Repository in 'owner/name' format.
            head: Source branch.
            base: Target branch.
            title: PR title.
            body: PR body markdown.
            labels: Labels to apply.

        Returns:
            PR metadata with url, number, html_url.
        """
        raise NotImplementedError

    async def add_comment(self, repo: str, issue_number: int, body: str) -> dict:
        """Add a comment to an issue or PR.

        Args:
            repo: Repository in 'owner/name' format.
            issue_number: Issue or PR number.
            body: Comment body markdown.

        Returns:
            Comment metadata.
        """
        raise NotImplementedError
