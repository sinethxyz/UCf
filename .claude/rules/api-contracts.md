# API Contract Rules

## OpenAPI First
unicorn-app's API is defined by OpenAPI specs in `packages/contracts/`. Any endpoint change must update the OpenAPI spec first, then implement the handler to match.

When building or modifying endpoints:
1. Read the existing OpenAPI spec for the domain.
2. Add or modify the route, request body, response schema, and error responses in the spec.
3. Implement the Go handler to match the spec exactly.
4. Run schema verification to confirm the implementation matches the spec.

## JSON Schemas
All domain objects (events, evidence, company state, scorecards) have JSON Schemas in `canon/schemas/`. These schemas are the contract between Foundry and unicorn-app.

When producing structured output:
- Always validate against the relevant schema before storing.
- Invalid output is a run failure, not a warning.
- Never add fields not in the schema. If the schema needs extension, that is a separate `canon_update` task.

## Response Consistency
All API responses in unicorn-app follow this envelope:

```json
{
  "data": { ... },
  "meta": { "request_id": "...", "timestamp": "..." }
}
```

Error responses:

```json
{
  "error": { "code": "...", "message": "..." },
  "meta": { "request_id": "...", "timestamp": "..." }
}
```

Follow this pattern for every new endpoint. No exceptions.

## Versioning
All public endpoints are prefixed with `/v1/`. Breaking changes require a new version prefix. Additive changes (new optional fields, new endpoints) do not.

## Generated Clients
After any OpenAPI change, the TypeScript client in `packages/contracts/` must be regenerated. Include this in the PR.
