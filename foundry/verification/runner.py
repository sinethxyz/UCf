"""Verification dispatch: routes verification to the correct runner based on file types."""

from foundry.verification.go_verify import GoVerifier, VerificationResult
from foundry.verification.schema_verify import SchemaVerifier
from foundry.verification.ts_verify import TypeScriptVerifier


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
        - .ts, .tsx -> TypeScriptVerifier
        - .schema.json -> SchemaVerifier

        Args:
            worktree_path: Absolute path to the worktree.
            changed_files: List of changed file paths (relative to worktree).

        Returns:
            List of VerificationResult objects, one per verifier run.
        """
        raise NotImplementedError("Phase 1")
