#!/usr/bin/env bash
# .claude/hooks/post-commit-smoke.sh — Runs Tier 1 smoke tests after git commits (#269)
#
# Claude Code PostToolUse hook. Receives JSON on stdin with tool_input.command.
# Only fires on "git commit" commands. Gracefully skips if container is down.
#
# Exit codes:
#   0 — pass (or not a commit, or container down)
#   2 — smoke tests failed; stderr fed back to Claude

set -uo pipefail

INPUT=$(cat)

# Extract the bash command that was executed
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)

# Only trigger on git commit commands
if ! echo "$COMMAND" | grep -q 'git commit'; then
    exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
SMOKE_SCRIPT="$SCRIPT_DIR/scripts/smoke_test.sh"

if [ ! -x "$SMOKE_SCRIPT" ]; then
    echo "Smoke test script not found at $SMOKE_SCRIPT" >&2
    exit 0  # Don't block — script might have been removed
fi

# Check if container is up before running (don't block commits when container is down)
if ! curl -s --max-time 3 http://localhost:8000/ >/dev/null 2>&1; then
    exit 0  # Container down — silently skip
fi

echo "Running Tier 1 smoke tests after commit..." >&2

# Run Tier 1 only (no --full), capture output
OUTPUT=$("$SMOKE_SCRIPT" 2>&1)
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo "$OUTPUT" >&2
    echo "" >&2
    echo "Smoke tests FAILED after commit. Review failures above." >&2
    exit 2
fi

# Tests passed — brief confirmation to stderr (visible in verbose mode)
echo "Smoke tests passed." >&2
exit 0
