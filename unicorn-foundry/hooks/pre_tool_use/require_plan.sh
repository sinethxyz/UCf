#!/bin/bash
# PreToolUse hook: block implementation edits if no plan artifact exists.
# Registered for: Edit, Write
# Only enforced during the "implementing" run state.
# Reads RUN_STATE and ARTIFACT_DIR from environment.

set -euo pipefail

RUN_STATE="${RUN_STATE:-unknown}"
ARTIFACT_DIR="${ARTIFACT_DIR:-/tmp/foundry-artifacts}"

# Only enforce during implementation phase
if [ "$RUN_STATE" != "implementing" ]; then
    echo '{"decision": "allow"}'
    exit 0
fi

# Check for plan artifact
if [ ! -f "$ARTIFACT_DIR/plan.json" ]; then
    echo '{"decision": "deny", "reason": "No plan artifact found at '"$ARTIFACT_DIR"'/plan.json. Planning phase must complete before implementation."}'
    exit 0
fi

# Validate plan is not empty
PLAN_SIZE=$(stat -c%s "$ARTIFACT_DIR/plan.json" 2>/dev/null || echo "0")
if [ "$PLAN_SIZE" -lt 10 ]; then
    echo '{"decision": "deny", "reason": "Plan artifact exists but appears empty or invalid."}'
    exit 0
fi

echo '{"decision": "allow"}'
