"""Evidence type and confidence accuracy scorer."""


class EvidenceScorer:
    """Evaluates evidence type and confidence accuracy."""

    def score(self, predicted: dict, expected: dict) -> dict:
        """Score predicted evidence against expected ground truth.

        Args:
            predicted: Evidence output from the model.
            expected: Ground truth evidence.

        Returns:
            Scoring metrics dict.
        """
        raise NotImplementedError("Phase 1")
