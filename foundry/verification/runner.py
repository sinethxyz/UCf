"""Verification dispatch: routes verification to the correct runner based on file types."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

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
        *,
        run_id: UUID | None = None,
        session: AsyncSession | None = None,
    ) -> tuple[list[VerificationResult], bool]:
        """Run all applicable verification checks based on changed file types.

        Inspects file extensions to determine which verifiers to run:
        - .go -> GoVerifier
        - .ts, .tsx -> TypeScriptVerifier (deferred — not yet implemented)
        - .schema.json -> SchemaVerifier (deferred — not yet implemented)

        When *run_id* and *session* are provided, each result is persisted to
        the ``verification_results`` table via the ORM model.

        Args:
            worktree_path: Absolute path to the worktree.
            changed_files: List of changed file paths (relative to worktree).
            run_id: Optional run ID for DB persistence.
            session: Optional async DB session for persistence.

        Returns:
            A tuple of (results, overall_passed) where *results* is a list of
            :class:`VerificationResult` objects and *overall_passed* is ``True``
            only when every result passed.
        """
        results: list[VerificationResult] = []

        has_go = any(f.endswith(".go") for f in changed_files)
        has_ts = any(
            f.endswith(".ts") or f.endswith(".tsx") for f in changed_files
        )
        has_schema = any(f.endswith(".schema.json") for f in changed_files)

        # --- Go ---------------------------------------------------------
        if has_go:
            logger.info("Go files detected — running Go verification")
            result = await self.go_verifier.verify(worktree_path)
            results.append(result)

        # --- TypeScript (dispatch hook — not yet implemented) -----------
        if has_ts:
            logger.info(
                "TypeScript files detected — ts_verify not yet implemented, skipping"
            )

        # --- JSON Schema (dispatch hook — not yet implemented) ----------
        if has_schema:
            logger.info(
                "Schema files detected — schema_verify not yet implemented, skipping"
            )

        # --- Fallback when nothing ran ----------------------------------
        if not results:
            logger.warning(
                "No applicable verifiers for changed files: %s", changed_files
            )
            results.append(
                VerificationResult(
                    check_type="none",
                    passed=True,
                    output="No applicable verification checks for the changed files.",
                    duration_ms=0,
                )
            )

        overall_passed = all(r.passed for r in results)

        # --- Persist to DB when session is available --------------------
        if session is not None and run_id is not None:
            from foundry.db.models import VerificationResult as VRModel

            for r in results:
                vr = VRModel(
                    run_id=run_id,
                    check_type=r.check_type,
                    passed=r.passed,
                    output=r.output[:10_000],
                    duration_ms=r.duration_ms,
                )
                session.add(vr)
            await session.flush()

        return results, overall_passed
