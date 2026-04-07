# SKILL.md — extract-signals

## Description
Transforms raw startup signal sources into structured event and evidence JSON at scale, using the Message Batches API for cost-efficient bulk processing.

## Trigger
- Raw source material needs normalization into structured events/evidence.
- Task type is `extraction_batch`.
- Explicitly invoked via `/extract-signals`.

## Workflow

1. **Validate inputs.** Confirm all source documents have required metadata (URL, source type, retrieval date). Reject malformed inputs immediately — do not attempt partial extraction.

2. **Load canon context.** Read the relevant canon documents before building prompts:
   - `canon/docs/event_taxonomy.md` — event types and required fields.
   - `canon/docs/evidence_taxonomy.md` — evidence types, strength levels, attachment rules.
   - `canon/schemas/event.schema.json` — event output schema.
   - `canon/schemas/evidence.schema.json` — evidence output schema.
   - `canon/schemas/extraction_result.schema.json` — full extraction result schema.

3. **Pre-classify sources with Haiku.** Send each source to Haiku 4.5 for a lightweight classification pass:
   - Source category: funding announcement, product launch, hiring page, changelog, press release, regulatory filing, partnership, acquisition, etc.
   - Complexity estimate: simple (single clear event) vs. complex (multiple events, ambiguity, conflicting signals).
   - This classification determines model routing in step 4.

4. **Build batch request with prompt caching.** Construct a Message Batches API request:
   - Use **Haiku 4.5** for sources classified as simple (clear structure, single event, high-confidence signals).
   - Use **Sonnet 4.6** for sources classified as complex (multiple events, ambiguity, requires inference).
   - Enable prompt caching for the system prompt (which includes canon context and schemas) to reduce cost across the batch.
   - Each request includes: system prompt with canon context, source text, source metadata, and output schema instructions.

5. **Submit batch and poll.** Submit the batch request via the Message Batches API (`foundry/providers/claude_batch.py`). Poll for completion with exponential backoff (initial 30s, max 5m). Log batch ID and status transitions.

6. **Validate results against JSON Schema.** For each completed result:
   - Parse the structured output.
   - Validate against `canon/schemas/extraction_result.schema.json`.
   - Valid items proceed to step 7.
   - Invalid items are logged as extraction failures with the validation errors.

7. **Push valid items to unicorn-app.** Send validated extraction results to unicorn-app's internal ingestion endpoint:
   - `POST /internal/ingest/source` with the validated event and evidence payloads.
   - Retry transient failures (5xx, timeout) up to 3 times with exponential backoff.
   - Log all push results (success, failure, retry count).

8. **Store artifacts.** Store the full extraction run as an artifact:
   - Input sources and metadata.
   - Per-source results (events, evidence, validation status).
   - Aggregate stats (total sources, successful extractions, failures, events extracted, evidence objects created).
   - Batch API metadata (batch ID, cost, tokens used).

## Model Selection
- **Haiku 4.5** — simple, well-structured sources (structured funding announcements, clear press releases, standard changelog entries). Also used for the pre-classification pass.
- **Sonnet 4.6** — complex or ambiguous sources (multi-event documents, sources requiring inference, conflicting or noisy signals).
- Pre-classification by Haiku determines routing. Override via `model_override` in the task request if needed.

## Confidence Scoring
- 0.9–1.0: Direct quote or official announcement.
- 0.7–0.89: Strong inference from reliable source.
- 0.5–0.69: Reasonable inference with ambiguity.
- Below 0.5: Omit unless contextually important (flag for human review if included).

## Output
Validated JSON matching `canon/schemas/extraction_result.schema.json`, one result per source document.

## Failure Conditions
- Source is too noisy to extract reliably — return empty events array with explanation.
- Output fails schema validation — report as extraction failure, do not push to unicorn-app.
- Confidence below threshold for all signals — return empty events array.
- Batch API failure — retry the full batch up to 2 times, then fail the run.
- Ingestion endpoint returns 4xx — log the rejected item and continue (do not retry client errors).

## Cost Optimization
- **Prompt caching** is mandatory for batch runs. The system prompt (canon context + schemas) is identical across all items in a batch and should be cached.
- **Haiku pre-classification** prevents routing simple sources to Sonnet, saving ~5x per simple item.
- **Batching** via the Message Batches API provides 50% cost reduction over individual requests.
- Monitor cost per extraction and flag runs that exceed 2x the historical average cost per source.
