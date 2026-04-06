# SKILL.md — run-eval

## Description
Runs an evaluation dataset through a model and scores the results against expected outputs.

## When to Use
- An eval dataset and scorer are specified.
- Baseline accuracy needs to be established or tracked.
- Explicitly invoked via `/run-eval`.

## Workflow

1. **Load eval dataset.** Read the specified JSONL file from `evals/datasets/`.

2. **Configure the scorer.** Load the appropriate scorer from `evals/scorers/` based on the eval type (extraction_accuracy, evidence_strength, state_inference).

3. **Run inference.** For each item in the dataset:
   - Send the source text to the specified model with the appropriate extraction/scoring prompt.
   - Collect structured output.

4. **Score results.** For each output:
   - Compare against the expected output using the scorer.
   - Record per-item scores.

5. **Compute aggregate metrics.**
   - Precision, recall, F1 score.
   - Per-field accuracy.
   - Confidence calibration.

6. **Store results.** Write eval results as a structured artifact including:
   - Aggregate metrics.
   - Per-item scores.
   - Model used, dataset, timestamp.

## Output
Eval results JSON stored as an artifact and logged to `eval_runs` + `eval_results` tables.

## Failure Conditions
- Dataset file not found -> report error immediately.
- Scorer not found -> report error immediately.
- Model produces invalid output for >50% of items -> flag as potential prompt regression.
