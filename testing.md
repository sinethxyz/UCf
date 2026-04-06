# Testing Rules

## When Tests Are Required

Every PR must include tests for:
- New API endpoints: handler test + integration test
- New domain logic: unit tests covering happy path, error cases, edge cases
- Bug fixes: regression test that reproduces the bug before the fix
- Refactors: existing tests must pass unchanged (test behavior, not implementation)

Tests are NOT required for:
- Documentation-only changes
- Config changes (but these require manual verification notes in the PR)
- Generated code (test the generator, not the output)

## Test Conventions — Go (unicorn-app)

- Test files live next to the code: `handler.go` → `handler_test.go`
- Use `testing.T` and table-driven tests for unit tests.
- Use `testify/assert` for assertions.
- Integration tests use a real test database (see `scripts/test-db-setup.sh`).
- Test function naming: `TestFunctionName_Scenario_Expected`

```go
func TestGetCompany_ValidID_ReturnsCompany(t *testing.T) { ... }
func TestGetCompany_NotFound_Returns404(t *testing.T) { ... }
```

## Test Conventions — TypeScript (unicorn-app frontend)

- Test files: `Component.tsx` → `Component.test.tsx`
- Use Vitest + React Testing Library.
- Test user-visible behavior, not implementation details.
- Mock API calls at the fetch layer, not at the component level.

## Test Conventions — Python (unicorn-foundry)

- Test files mirror source: `foundry/orchestration/run_engine.py` → `tests/unit/orchestration/test_run_engine.py`
- Use pytest.
- Use fixtures for database sessions, mock providers, sample task requests.
- Integration tests that call Claude are in `tests/integration/` and are expensive — run them explicitly, not in CI by default.

## Verification Steps

After implementation, the verification runner executes in order:
1. `go build ./...` (for Go changes)
2. `go vet ./...` (for Go changes)
3. `go test ./...` (for Go changes)
4. `npx tsc --noEmit` (for TS changes)
5. `npx eslint .` (for TS changes)
6. JSON Schema validation (for schema changes)
7. OpenAPI spec validation (for API changes)

All steps must pass. A single failure blocks the PR.
