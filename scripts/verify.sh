#!/bin/bash
# This script runs a basic end-to-end sanity check of the agentic system.
# It starts the server, sends a test prompt, and then stops the server.

# Exit immediately if a command exits with a non-zero status.
set -e

# Get the directory of the script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
# Go to the parent directory (project root)
cd "$SCRIPT_DIR/.."

PORT=8000
HEALTH_CHECK_URL="http://127.0.0.1:${PORT}/"
TEST_PROMPT="Hello, world! Please respond with a simple confirmation."

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
    if curl -s --fail "$HEALTH_CHECK_URL" > /dev/null; then
        echo "Server is up and running."
        # Run the CLI script and check its exit code
        echo "--- Running CLI verification test ---"
        if ./scripts/cli.sh "$TEST_PROMPT"; then
            echo "---"
            echo "✅ Verification test PASSED."
            exit 0
        else
            echo "---"
            echo "❌ Verification test FAILED: CLI command failed."
            exit 1
        fi
    fi
    echo -n "."
    sleep 1
done

echo -e "\n\n❌ Verification test FAILED: Server did not become healthy within 30 seconds."
echo "Check server logs for errors: ./logs/agentic_server.log"
exit 1