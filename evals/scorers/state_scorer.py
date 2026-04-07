"""State inference accuracy scorer."""


class StateScorer:
    """Evaluates state inference accuracy."""

    def score(self, predicted: dict, expected: dict) -> dict:
        """Score predicted state against expected ground truth.

        Args:
            predicted: State inference output from the model.
            expected: Ground truth state.

        Returns:
            Scoring metrics dict.
        """
        raise NotImplementedError("Phase 1")
