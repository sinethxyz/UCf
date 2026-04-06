#!/bin/bash
# PostToolUse hook: log every tool call to the run's event log.
# Registered for: * (all tools)
# Reads RUN_ID and ARTIFACT_DIR from environment.

set -euo pipefail

INPUT=$(cat)
TOOL=$(echo "$INPUT" | jq -r '.tool_name // "unknown"')
PATH_ARG=$(echo "$INPUT" | jq -r '.tool_input.path // .tool_input.file_path // .tool_input.command // "n/a"')
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

RUN_ID="${RUN_ID:-unknown}"
ARTIFACT_DIR="${ARTIFACT_DIR:-/tmp/foundry-artifacts}"
LOG_FILE="$ARTIFACT_DIR/tool_log.jsonl"

# Ensure artifact directory exists
mkdir -p "$ARTIFACT_DIR"

# Truncate path arg if too long (e.g., large bash commands)
if [ ${#PATH_ARG} -gt 500 ]; then
    PATH_ARG="${PATH_ARG:0:497}..."
fi

# Append log entry
echo "{\"ts\":\"$TIMESTAMP\",\"run_id\":\"$RUN_ID\",\"tool\":\"$TOOL\",\"target\":\"$PATH_ARG\"}" >> "$LOG_FILE"
