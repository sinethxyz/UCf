"""Go verification: build, vet, test, and lint.

Runs the full Go verification suite in sequence against a worktree.
"""

from dataclasses import dataclass


@dataclass
class VerificationResult:
    """Result of a single verification check."""

    check_type: str
    passed: bool
    output: str
    duration_ms: int


class GoVerifier:
    """Runs Go verification checks: build, vet, test, golangci-lint."""

    async def verify(
        self,
        worktree_path: str,
        packages: list[str] | None = None,
    ) -> VerificationResult:
        """Run the full Go verification suite on a worktree.

        Executes in order: go build, go vet, go test, golangci-lint.
        Stops on first failure.

        Args:
            worktree_path: Absolute path to the worktree to verify.
            packages: Optional list of Go packages to check. Defaults
                to './...' (all packages).

        Returns:
            VerificationResult with aggregated check outcome.
        """
        raise NotImplementedError("Phase 1")
