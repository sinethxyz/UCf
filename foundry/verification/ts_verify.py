"""TypeScript verification: tsc, eslint, next build.

Runs the full TypeScript/Next.js verification suite against a worktree.
"""

from foundry.verification.go_verify import VerificationResult


class TypeScriptVerifier:
    """Runs TypeScript verification checks: tsc, eslint, next build."""

    async def verify(self, worktree_path: str) -> VerificationResult:
        """Run the full TypeScript verification suite on a worktree.

        Executes in order: tsc --noEmit, eslint, next build.
        Stops on first failure.

        Args:
            worktree_path: Absolute path to the worktree to verify.

        Returns:
            VerificationResult with aggregated check outcome.
        """
        raise NotImplementedError("Phase 1")
