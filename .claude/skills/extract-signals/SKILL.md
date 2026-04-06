# SKILL.md — extract-signals

## Description
Transforms raw startup signal sources into structured event and evidence JSON per the canon schemas.

## When to Use
- Raw source material needs normalization into structured events.
- A batch extraction run is submitted.
- Explicitly invoked via `/extract-signals`.

## Workflow

1. **Receive raw source.** Accept raw source text plus source metadata (URL, source type, retrieval date).

2. **Classify source type.** Determine the source category: funding announcement, product launch, hiring page, changelog, press release, etc.

3. **Extract structured events.** Per `canon/schemas/event.schema.json`:
   - Identify every discrete event in the source.
   - Assign event type from the taxonomy in `canon/docs/event_taxonomy.md`.
   - Extract date, company, summary, and structured data fields.

4. **Attach evidence objects.** Per `canon/schemas/evidence.schema.json`:
   - For each event, create evidence objects with type, quote, confidence, and source location.
   - Assign evidence strength level: direct, strong_inference, weak_inference, contextual.

5. **Assign confidence scores.**
   - 0.9-1.0: Direct quote or official announcement.
   - 0.7-0.89: Strong inference from reliable source.
   - 0.5-0.69: Reasonable inference with ambiguity.
   - Below 0.5: Omit unless contextually important.

6. **Validate output.** Validate the complete extraction result against the canon JSON Schemas. Invalid output is a failure.

7. **Return validated JSON array.** One extraction result per source document.

## Model Selection
- **Sonnet 4.6** for complex or ambiguous sources.
- **Haiku 4.5** for clear-cut, well-structured sources (e.g., structured funding announcements).

## Output
Validated JSON matching `canon/schemas/extraction_result.schema.json`.

## Failure Conditions
- Source is too noisy to extract reliably -> return empty events array with explanation.
- Output fails schema validation -> report as extraction failure.
- Confidence below threshold for all signals -> return empty events array.
