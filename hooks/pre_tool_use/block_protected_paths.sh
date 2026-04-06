#!/bin/bash
# PreToolUse hook: block writes to protected paths unless task type authorizes them.
# Registered for: Edit, Write
# Reads RUN_TASK_TYPE from environment.

set -euo pipefail

INPUT=$(cat)
PATH_ARG=$(echo "$INPUT" | jq -r '.tool_input.path // .tool_input.file_path // empty')

if [ -z "$PATH_ARG" ]; then
    echo '{"decision": "allow"}'
    exit 0
fi

# Protected path patterns
IS_PROTECTED=false

case "$PATH_ARG" in
    *migrations/*)    IS_PROTECTED=true ;;
    *auth/*)          IS_PROTECTED=true ;;
    *infra/*)         IS_PROTECTED=true ;;
    *docker-compose*) IS_PROTECTED=true ;;
    *Dockerfile*)     IS_PROTECTED=true ;;
esac

if [ "$IS_PROTECTED" = true ]; then
    # Only migration_plan and canon_update tasks can write to protected paths
    TASK_TYPE="${RUN_TASK_TYPE:-unknown}"
    if [ "$TASK_TYPE" != "migration_plan" ] && [ "$TASK_TYPE" != "canon_update" ]; then
        echo "{\"decision\": \"deny\", \"reason\": \"Protected path requires migration_plan or canon_update task type. Current: $TASK_TYPE\"}"
        exit 0
    fi
fi

echo '{"decision": "allow"}'
