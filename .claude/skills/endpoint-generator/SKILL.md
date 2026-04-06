# SKILL.md — endpoint-generator

## Description
Generates a complete API endpoint in unicorn-app following existing patterns: handler, model, route registration, OpenAPI spec, and tests.

## When to Use
- Plan step targets `services/api/` with action `create` for a new endpoint.
- Task type is `endpoint_build`.
- Explicitly invoked via `/endpoint-generator`.

## Workflow

1. **Read existing patterns.** In the target domain directory:
   - Read one handler file for function signature and response patterns.
   - Read the routes file for registration pattern.
   - Read one model file for struct and JSON tag conventions.
   - Read one test file for test conventions.

2. **Read the OpenAPI spec.** Understand existing route structure, shared schemas, and response envelope format.

3. **Generate OpenAPI additions.** Add the new route with:
   - Path and method
   - Path parameters and query parameters
   - Request body schema (if applicable)
   - Response schema (200, 400, 404, 500)

4. **Generate the model.** Request and response structs with proper JSON tags and validation tags.

5. **Generate the handler.** Following the discovered pattern:
   - Parse and validate request
   - Call domain logic
   - Return response via envelope helper
   - Handle all error cases

6. **Register the route.** Add the route to the domain's routes file.

7. **Generate tests.** Table-driven tests covering:
   - Happy path
   - Invalid input (400)
   - Not found (404)
   - At least one edge case

8. **Verify.** Run `go build ./...` and `go test ./...` on the affected packages.

## Output
Modified/created files in the worktree. Verification results.

## Failure Conditions
- Cannot discover consistent handler pattern → stop and report.
- Build fails after generation → report the error, do not attempt multiple fix loops.
