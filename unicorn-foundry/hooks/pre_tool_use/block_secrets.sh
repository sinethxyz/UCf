#!/bin/bash
# PreToolUse hook: block access to secret and credential files.
# Registered for: Read, Edit, Write
# Returns JSON with decision: allow or deny.

set -euo pipefail

INPUT=$(cat)
PATH_ARG=$(echo "$INPUT" | jq -r '.tool_input.path // .tool_input.file_path // empty')

if [ -z "$PATH_ARG" ]; then
    echo '{"decision": "allow"}'
    exit 0
fi

# Normalize to basename for pattern matching
BASENAME=$(basename "$PATH_ARG")
FULL_PATH="$PATH_ARG"

# Block patterns
BLOCKED=false

# Exact extensions
case "$BASENAME" in
    *.env|*.env.*|*.pem|*.key|*.p12|*.pfx)
        BLOCKED=true
        ;;
esac

# Substring patterns
case "$FULL_PATH" in
    *secrets*|*credentials*|*service-account*|*private_key*|*secret_key*)
        BLOCKED=true
        ;;
esac

# Specific filenames
case "$BASENAME" in
    .env|.env.local|.env.production|.env.staging|.env.development)
        BLOCKED=true
        ;;
esac

if [ "$BLOCKED" = true ]; then
    echo "{\"decision\": \"deny\", \"reason\": \"Access to secret/credential file blocked: $BASENAME\"}"
else
    echo '{"decision": "allow"}'
fi
