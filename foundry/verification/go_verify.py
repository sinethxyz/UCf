"""Go verification: build, vet, test, and lint.

Runs the full Go verification suite in sequence against a worktree.
"""

import asyncio
import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class VerificationResult:
    """Result of a single verification check."""

    check_type: str
    passed: bool
    output: str
    duration_ms: int


class GoVerifier:
    """Runs Go verification checks: build, vet, test."""

    async def verify(
        self,
        worktree_path: str,
        packages: list[str] | None = None,
    ) -> VerificationResult:
        """Run the full Go verification suite on a worktree.

        Executes in order: go build, go vet, go test.
        Stops on first failure.

        Args:
            worktree_path: Absolute path to the worktree to verify.
            packages: Optional list of Go packages to check. Defaults
                to './...' (all packages).

        Returns:
            VerificationResult with aggregated check outcome.
        """
        pkg_target = packages or ["./..."]
        checks = [
            ("go_build", ["go", "build"] + pkg_target),
            ("go_vet", ["go", "vet"] + pkg_target),
            ("go_test", ["go", "test", "-count=1", "-timeout=120s"] + pkg_target),
        ]

        all_output = []
        total_start = time.monotonic()

        for check_name, cmd in checks:
            logger.info("Running %s in %s", check_name, worktree_path)
            start = time.monotonic()

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=worktree_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            elapsed = int((time.monotonic() - start) * 1000)

            output = stdout.decode(errors="replace")
            if stderr:
                output += "\n" + stderr.decode(errors="replace")

            all_output.append(f"=== {check_name} ({elapsed}ms) ===\n{output}")

            if proc.returncode != 0:
                logger.warning("%s failed (exit %d)", check_name, proc.returncode)
                total_ms = int((time.monotonic() - total_start) * 1000)
                return VerificationResult(
                    check_type="go",
                    passed=False,
                    output="\n\n".join(all_output),
                    duration_ms=total_ms,
                )

            logger.info("%s passed (%dms)", check_name, elapsed)

        total_ms = int((time.monotonic() - total_start) * 1000)
        return VerificationResult(
            check_type="go",
            passed=True,
            output="\n\n".join(all_output),
            duration_ms=total_ms,
        )
