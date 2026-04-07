"""Verification dispatch: routes verification to the correct runner based on file types."""

import logging

from foundry.verification.go_verify import GoVerifier, VerificationResult
from foundry.verification.schema_verify import SchemaVerifier
from foundry.verification.ts_verify import TypeScriptVerifier

logger = logging.getLogger(__name__)


class VerificationRunner:
    """Dispatches verification based on changed file types.

    Detects .go files -> GoVerifier, .ts/.tsx files -> TypeScriptVerifier,
    .schema.json files -> SchemaVerifier. Runs all applicable verifiers.
    """

    def __init__(self) -> None:
        self.go_verifier = GoVerifier()
        self.ts_verifier = TypeScriptVerifier()
        self.schema_verifier = SchemaVerifier()

    async def run_all(
        self,
        worktree_path: str,
        changed_files: list[str],
    ) -> list[VerificationResult]:
        """Run all applicable verification checks based on changed file types.

        Inspects file extensions to determine which verifiers to run:
        - .go -> GoVerifier
        - .ts, .tsx -> TypeScriptVerifier (Phase 1: deferred)
        - .schema.json -> SchemaVerifier (Phase 1: deferred)

        Args:
            worktree_path: Absolute path to the worktree.
            changed_files: List of changed file paths (relative to worktree).

        Returns:
            List of VerificationResult objects, one per verifier run.
        """
        results: list[VerificationResult] = []

        has_go = any(f.endswith(".go") for f in changed_files)

        if has_go:
            logger.info("Go files detected — running Go verification")
            result = await self.go_verifier.verify(worktree_path)
            results.append(result)

        if not results:
            logger.warning("No applicable verifiers for changed files: %s", changed_files)
            results.append(VerificationResult(
                check_type="none",
                passed=True,
                output="No applicable verification checks for the changed files.",
                duration_ms=0,
            ))

        return results
