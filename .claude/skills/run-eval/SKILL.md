# SKILL.md — run-eval

## Description
Runs evaluation datasets through production prompts, scores results against expected outputs, and flags regressions to protect extraction and inference quality.

## Trigger
- After changing extraction prompts or canon schemas.
- On a scheduled cadence (weekly or per-release).
- When establishing a new baseline for a dataset.
- Explicitly invoked via `/run-eval`.

## Workflow

1. **Load JSONL dataset.** Read the specified dataset file from `evals/datasets/`. Each line contains a source input and expected structured output. Validate the file exists and is well-formed before proceeding.

2. **Run inference with production prompts.** For each item in the dataset:
   - Use the exact same prompts and model configuration as production extraction/inference.
   - Never modify prompts to improve eval scores — the eval must reflect real performance.
   - Collect structured output for each item.

3. **Score with specified scorer.** Load the appropriate scorer from `evals/scorers/` and score each output:
   - Compare predicted output against expected output.
   - Record per-item scores with field-level detail.
   - Log any items where the model produced invalid output.

4. **Aggregate metrics.** Compute the following aggregate metrics:
   - **Precision** — fraction of predicted items that are correct.
   - **Recall** — fraction of expected items that were predicted.
   - **F1 score** — harmonic mean of precision and recall.
   - **Accuracy** — overall exact-match rate.
   - **Calibration** — correlation between model confidence scores and actual correctness.
   - Per-field breakdowns for all metrics where applicable.

5. **Store results.** Write eval results as a structured artifact and persist to the database:
   - Artifact: full eval results JSON with aggregate metrics, per-item scores, model info, dataset name, and timestamp.
   - Database: insert into `eval_runs` (run-level metadata) and `eval_results` (per-item scores) tables.

6. **Compare to baseline and flag regressions.** Load the most recent baseline for this dataset and scorer combination:
   - If any aggregate metric has regressed by more than **2%**, flag the run as a regression.
   - Regression flag blocks the associated PR if one exists.
   - Report which metrics regressed, by how much, and which items contributed most to the regression.
   - If no baseline exists, this run becomes the baseline.

## Available Datasets
- `extraction_accuracy` — tests end-to-end extraction from raw sources to structured events/evidence.
- `evidence_strength` — tests correct assignment of evidence strength levels (direct, strong_inference, weak_inference, contextual).
- `state_inference` — tests company state computation from events and evidence.

Datasets live in `evals/datasets/` as JSONL files.

## Available Scorers
- `extraction_scorer` — scores event and evidence extraction against expected outputs. Evaluates event type, date, company, structured data fields, and evidence attachments.
- `evidence_scorer` — scores evidence strength assignment and confidence calibration.
- `state_scorer` — scores inferred company state against expected state snapshots.

Scorers live in `evals/scorers/`.

## Constraints
- **Use production prompts.** The eval must use the exact same prompts as production extraction. Never modify a prompt to pass an eval — if the eval fails, fix the prompt in production.
- **Never modify a scorer to pass an eval.** If a scorer is producing incorrect results, that is a separate bug to fix, not an eval workaround.
- **Regression threshold is 2%.** Any aggregate metric drop greater than 2% from baseline is a blocking regression. This threshold is not configurable per-run.
- **Invalid output rate.** If the model produces invalid (non-schema-conforming) output for more than 50% of items, flag as a potential prompt regression and fail the run.

## Output
Eval results JSON stored as an artifact and logged to `eval_runs` + `eval_results` tables. Includes aggregate metrics, per-item scores, baseline comparison, and regression flags.
