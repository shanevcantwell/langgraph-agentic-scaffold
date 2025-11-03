#!/bin/bash
# This script runs a basic end-to-end sanity check of the agentic system.
# It starts the server, sends a test prompt, and then stops the server.

# Exit immediately if a command exits with a non-zero status.
set -e

# Get the directory of the script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
# Go to the parent directory (project root)
cd "$SCRIPT_DIR/.."

# --- Check for jq dependency ---
if ! command -v jq &> /dev/null
then
    echo "Error: jq is not installed. Please install jq to run this verification script."
    echo "On Debian/Ubuntu: sudo apt-get install jq"
    echo "On macOS (using Homebrew): brew install jq"
    echo "For other systems, please refer to https://stedolan.github.io/jq/download/"
    exit 1
fi

PORT=8000
HEALTH_CHECK_URL="http://127.0.0.1:${PORT}/"

# --- Test Configuration ---
# Default to 'ping' for a quick test. Pass 'complex' as an argument to use the complex prompt.
TEST_TYPE=${1:-ping}
if [ "$TEST_TYPE" == "ping" ]; then
    PROMPT_FILE="./scripts/ping_prompt.txt"
elif [ "$TEST_TYPE" == "complex" ]; then
    PROMPT_FILE="./scripts/complex_prompt.txt"
else
    echo "Error: Invalid test type '$TEST_TYPE'. Use 'ping' or 'complex'." >&2; exit 1
fi

# --- Cleanup function ---
# This function will be called on script exit to ensure the server is stopped.
cleanup() {
    echo "---"
    echo "Running cleanup: stopping server..."
    # Use the server script to stop. Redirect output to hide it unless there's an error.
    ./scripts/server.sh stop > /dev/null 2>&1 || true # Ignore errors if already stopped
    echo "Cleanup complete."
}

# Trap the EXIT signal to run the cleanup function, ensuring the server is always stopped.
trap cleanup EXIT

# --- Main script ---
echo "--- Starting server for verification test ---"
./scripts/server.sh start

echo "--- Waiting for server to become healthy (max 30 seconds) ---"
for i in {1..30}; do
    # Use curl to check the health endpoint.
    if curl -s --fail "$HEALTH_CHECK_URL" > /dev/null;
    then
        echo "Server is up and running."
        echo "--- Running CLI verification test (type: $TEST_TYPE) ---"
        # Read the prompt from a file and pipe it to the CLI. The CLI now correctly
        # handles top-level options and defaults to the 'invoke' command.
        JSON_RESPONSE=$(cat "$PROMPT_FILE" | ./scripts/cli.sh --json-only)

        # Check if JSON_RESPONSE is empty or not valid JSON
        if [ -z "$JSON_RESPONSE" ]; then
            echo "---"
            echo "❌ Verification test FAILED: No JSON response received from CLI."
            echo "Full CLI Output:"
            echo "---"
            echo "---"
            exit 1
        fi

        # Validate the JSON response using jq
        # A successful workflow is defined by the presence of the 'archive_report.md'
        # key within the 'artifacts' dictionary. This is the most reliable signal
        # that the Coordinated Completion Sequence completed successfully.
        # (Signal → EndSpecialist [synthesis + archive] → Confirm)

        # Extract key diagnostic information
        ROUTING_HISTORY=$(echo "$JSON_RESPONSE" | jq -r '.routing_history | join(" → ")' 2>/dev/null || echo "N/A")
        TURN_COUNT=$(echo "$JSON_RESPONSE" | jq -r '.turn_count // "N/A"' 2>/dev/null)
        HAS_ARCHIVE=$(echo "$JSON_RESPONSE" | jq -e '.artifacts."archive_report.md"' > /dev/null 2>&1 && echo "YES" || echo "NO")
        HAS_FINAL_RESPONSE=$(echo "$JSON_RESPONSE" | jq -e '.artifacts."final_user_response.md"' > /dev/null 2>&1 && echo "YES" || echo "NO")
        ERROR_REPORT=$(echo "$JSON_RESPONSE" | jq -r '.error_report // "None"' 2>/dev/null)

        # Find most recent archive file
        LATEST_ARCHIVE=$(ls -t ./logs/archive/*.md 2>/dev/null | head -1 || echo "None found")

        echo "---"
        echo "📊 Diagnostic Information:"
        echo "  🔄 Routing History: $ROUTING_HISTORY"
        echo "  🔢 Turn Count: $TURN_COUNT"
        echo "  📦 Archive Report: $HAS_ARCHIVE"
        echo "  📝 Final Response: $HAS_FINAL_RESPONSE"
        echo "  📄 Latest Archive File: $LATEST_ARCHIVE"
        echo "  📋 Server Log: ./logs/agentic_server.log"

        if [ "$ERROR_REPORT" != "None" ]; then
            echo "  ❌ Error Report Present: YES"
        fi

        echo ""

        if [ "$HAS_ARCHIVE" == "YES" ]; then
            echo "✅ Verification test PASSED: Coordinated Completion Sequence completed successfully."
            echo ""
            echo "🔍 To view detailed LangSmith trace:"
            echo "  1. Open https://smith.langchain.com"
            echo "  2. Navigate to project: $(grep LANGSMITH_PROJECT .env 2>/dev/null | cut -d= -f2 || echo 'pr-whispered-stencil-31')"
            echo "  3. Find the most recent run matching the routing history above"
            exit 0
        else
            echo "❌ Verification test FAILED: Archive report not generated (completion sequence incomplete)."
            echo ""
            if [ "$HAS_FINAL_RESPONSE" == "YES" ]; then
                echo "⚠️  Note: Final response was generated but archiver did not run."
                echo "   This suggests EndSpecialist or Archiver may have issues."
            fi
            echo ""
            echo "🔍 Debug Information:"
            echo "  - Check routing history above to see where execution stopped"
            echo "  - Review server logs: tail -50 ./logs/agentic_server.log"
            if [ "$LATEST_ARCHIVE" != "None found" ]; then
                echo "  - Compare with last successful archive: $LATEST_ARCHIVE"
            fi
            echo ""
            echo "Full JSON Response:"
            echo "$JSON_RESPONSE" | jq .
            exit 1
        fi
    fi
    echo -n "."
    sleep 1
done

echo -e "\n\n❌ Verification test FAILED: Server did not become healthy within 30 seconds."
echo "Check server logs for errors: ./logs/agentic_server.log"
exit 1