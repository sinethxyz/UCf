# Repo Safety Rules

## Secret Files
Never read, write, edit, log, or reference any file matching:
- `*.env`, `*.env.*`, `*.env.local`, `*.env.production`
- `*secrets*`, `*credentials*`, `*service-account*`
- `*.pem`, `*.key`, `*.p12`, `*.pfx`

If a task requires environment variables, reference them by name only (e.g., `os.environ["DATABASE_URL"]`). Never log their values.

## Protected Paths
The following paths require explicit task authorization (`migration_plan` or `canon_update` task type):
- `migrations/` — database migrations
- `auth/` — authentication and authorization logic
- `infra/` — infrastructure configuration
- `Dockerfile*`, `docker-compose*` — container definitions

If your task type does not authorize these paths and you believe changes are needed, stop and report this as a plan issue. Do not attempt to bypass.

## Branch Safety
- Never force push.
- Never commit to `main` directly.
- Never rebase a shared branch.
- All work happens in worktree branches named `foundry/{task-type}-{short-description}`.

## Destructive Operations
- Never run `rm -rf` on anything outside the current worktree.
- Never drop database tables outside of a migration.
- Never delete git branches that are not owned by the current run.

## Error Handling
If you encounter an unexpected error:
1. Log the error to the run event stream.
2. Store any partial artifacts.
3. Transition the run to `errored` state.
4. Do not attempt to recover silently.
