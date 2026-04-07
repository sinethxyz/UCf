"""Eval runner: loads datasets, runs inference, scores results, aggregates metrics."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from foundry.contracts.eval_models import EvalDefinition, EvalResult


class EvalRunner:
    """Loads dataset, runs inference, scores, aggregates metrics."""

    async def run(self, definition: EvalDefinition) -> EvalResult:
        """Execute an evaluation run.

        Args:
            definition: Eval definition specifying dataset, scorer, and model.

        Returns:
            Aggregated eval results.
        """
        raise NotImplementedError("Phase 1")
