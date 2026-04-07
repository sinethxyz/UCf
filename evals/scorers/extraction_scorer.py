"""Extraction accuracy scorer."""


class ExtractionScorer:
    """Compares extraction results against ground truth."""

    def score(self, predicted: dict, expected: dict) -> dict:
        """Score predicted extraction against expected ground truth.

        Args:
            predicted: Extraction output from the model.
            expected: Ground truth extraction.

        Returns:
            Scoring metrics dict.
        """
        raise NotImplementedError("Phase 1")
