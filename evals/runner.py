"""Eval runner: loads datasets, runs inference, scores results."""


async def run_eval(dataset_path: str, scorer_name: str, model: str) -> dict:
    """Execute an evaluation run.

    Args:
        dataset_path: Path to JSONL dataset file.
        scorer_name: Name of the scorer to use.
        model: Model identifier for inference.

    Returns:
        Aggregate eval results dict.
    """
    raise NotImplementedError
