"""GitHub REST API client for PR creation and repo operations."""

import logging

import httpx

logger = logging.getLogger(__name__)


class GitHubClient:
    """Client for GitHub API interactions.

    Handles pull request creation, commenting, labeling, and
    file listing for Foundry's PR workflow.
    """

    BASE_URL = "https://api.github.com"

    def __init__(self, token: str | None = None) -> None:
        self.token = token
        self._headers = {
            "Accept": "application/vnd.github.v3+json",
        }
        if token:
            self._headers["Authorization"] = f"token {token}"

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
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.BASE_URL}/repos/{repo}/pulls",
                headers=self._headers,
                json={
                    "title": title,
                    "body": body,
                    "head": head,
                    "base": base,
                },
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()

        logger.info("Created PR #%d on %s: %s", data["number"], repo, data["html_url"])
        return {
            "url": data["html_url"],
            "number": data["number"],
            "html_url": data["html_url"],
        }

    async def add_pr_comment(self, repo: str, pr_number: int, body: str) -> None:
        """Add a comment to a pull request.

        Args:
            repo: Repository in 'owner/name' format.
            pr_number: PR number.
            body: Comment body markdown.
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.BASE_URL}/repos/{repo}/issues/{pr_number}/comments",
                headers=self._headers,
                json={"body": body},
                timeout=30.0,
            )
            response.raise_for_status()

    async def add_pr_labels(self, repo: str, pr_number: int, labels: list[str]) -> None:
        """Add labels to a pull request.

        Args:
            repo: Repository in 'owner/name' format.
            pr_number: PR number.
            labels: List of label names to apply.
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.BASE_URL}/repos/{repo}/issues/{pr_number}/labels",
                headers=self._headers,
                json={"labels": labels},
                timeout=30.0,
            )
            # Labels may not exist yet — ignore 422 errors
            if response.status_code not in (200, 422):
                response.raise_for_status()

    async def get_pr(self, repo: str, pr_number: int) -> dict:
        """Get pull request details.

        Args:
            repo: Repository in 'owner/name' format.
            pr_number: PR number.

        Returns:
            PR metadata dict.
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/repos/{repo}/pulls/{pr_number}",
                headers=self._headers,
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()

    async def list_pr_files(self, repo: str, pr_number: int) -> list[dict]:
        """List files changed in a pull request.

        Args:
            repo: Repository in 'owner/name' format.
            pr_number: PR number.

        Returns:
            List of dicts with filename, status, additions, deletions.
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/repos/{repo}/pulls/{pr_number}/files",
                headers=self._headers,
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()
