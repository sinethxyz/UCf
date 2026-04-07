"""Go verification: build, vet, test, and lint.

Runs the full Go verification suite in sequence against a worktree.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class StepResult:
    """Result of a single verification step within a check."""

    step_name: str
    passed: bool
    output: str
    duration_ms: int


@dataclass
class VerificationResult:
    """Result of a single verification check."""

    check_type: str
    passed: bool
    output: str
    duration_ms: int
    details: list[StepResult] = field(default_factory=list)


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
            VerificationResult with aggregated check outcome and per-step
            details in the ``details`` field.
        """
        pkg_target = packages or ["./..."]
        checks = [
            ("go_build", ["go", "build"] + pkg_target),
            ("go_vet", ["go", "vet"] + pkg_target),
            ("go_test", ["go", "test", "-count=1", "-timeout=120s"] + pkg_target),
        ]

        all_output: list[str] = []
        step_details: list[StepResult] = []
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

            step_passed = proc.returncode == 0
            step_details.append(StepResult(
                step_name=check_name,
                passed=step_passed,
                output=output,
                duration_ms=elapsed,
            ))

            all_output.append(f"=== {check_name} ({elapsed}ms) ===\n{output}")

            if not step_passed:
                logger.warning("%s failed (exit %d)", check_name, proc.returncode)
                total_ms = int((time.monotonic() - total_start) * 1000)
                return VerificationResult(
                    check_type="go",
                    passed=False,
                    output="\n\n".join(all_output),
                    duration_ms=total_ms,
                    details=step_details,
                )

            logger.info("%s passed (%dms)", check_name, elapsed)

        total_ms = int((time.monotonic() - total_start) * 1000)
        return VerificationResult(
            check_type="go",
            passed=True,
            output="\n\n".join(all_output),
            duration_ms=total_ms,
            details=step_details,
        )
