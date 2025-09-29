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
        echo "--- Running CLI verification test ---"
        # Read the prompt from a file and pipe it to the CLI. This is the most
        # robust way to handle complex prompts. The CLI defaults to the 'invoke'
        # command and reads from stdin if no prompt argument is given.
        JSON_RESPONSE=$(cat ./scripts/test_prompt.txt | ./scripts/cli.sh --json-only)

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
        # A successful workflow is defined by the presence of the 'final_user_response.md'
        # key within the 'artifacts' dictionary. This is the most reliable signal
        # that the entire termination sequence completed successfully.
        if echo "$JSON_RESPONSE" | jq -e '.artifacts."final_user_response.md"'; then
            echo "---"
            echo "✅ Verification test PASSED: Agent returned a meaningful response and routed successfully."
            exit 0
        else
            echo "---"
            echo "❌ Verification test FAILED: Agent response was not meaningful or routing failed."
            echo "JSON Response:"
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