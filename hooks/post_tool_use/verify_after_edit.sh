#!/bin/bash
# PostToolUse hook: run targeted verification after file edits.
# Registered for: Edit, Write
# Reads WORKTREE_PATH from environment.

set -euo pipefail

INPUT=$(cat)
PATH_ARG=$(echo "$INPUT" | jq -r '.tool_input.path // .tool_input.file_path // empty')

if [ -z "$PATH_ARG" ]; then
    exit 0
fi

WORKTREE="${WORKTREE_PATH:-.}"

# Go files: run go vet on the package
if [[ "$PATH_ARG" == *.go ]]; then
    PKG_DIR=$(dirname "$PATH_ARG")
    cd "$WORKTREE" 2>/dev/null || exit 0
    # Run go vet, capture output but don't fail the hook
    OUTPUT=$(go vet "./$PKG_DIR/..." 2>&1) || true
    if [ -n "$OUTPUT" ]; then
        echo "go vet warnings for $PKG_DIR:"
        echo "$OUTPUT"
    fi
fi

# TypeScript files: run tsc --noEmit
if [[ "$PATH_ARG" == *.ts || "$PATH_ARG" == *.tsx ]]; then
    cd "$WORKTREE" 2>/dev/null || exit 0
    if [ -f "tsconfig.json" ]; then
        OUTPUT=$(npx tsc --noEmit 2>&1) || true
        if [ -n "$OUTPUT" ]; then
            echo "tsc errors:"
            echo "$OUTPUT"
        fi
    fi
fi

# Python files: run basic syntax check
if [[ "$PATH_ARG" == *.py ]]; then
    python3 -c "import py_compile; py_compile.compile('$PATH_ARG', doraise=True)" 2>&1 || true
fi

# JSON Schema files: validate JSON syntax
if [[ "$PATH_ARG" == *.schema.json || "$PATH_ARG" == *.json ]]; then
    python3 -c "import json; json.load(open('$PATH_ARG'))" 2>&1 || true
fi
