#!/bin/bash
# This script performs a basic smoke test of the Gradio UI.
# It verifies that:
# 1. The API server can start
# 2. The Gradio UI can launch
# 3. The UI is accessible via HTTP
#
# This is a MANUAL verification script - it launches the UI and provides
# instructions for the user to test it interactively.

set -e

# Get the directory of the script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
# Go to the parent directory (project root)
cd "$SCRIPT_DIR/.."

API_PORT=8000
UI_PORT=7860
API_HEALTH_URL="http://127.0.0.1:${API_PORT}/"
UI_HEALTH_URL="http://127.0.0.1:${UI_PORT}/"

echo "--- Gradio UI Verification Script ---"
echo ""
echo "This script will:"
echo "  1. Start the API server (if not already running)"
echo "  2. Launch the Gradio UI"
echo "  3. Wait for you to test the UI manually"
echo "  4. Clean up when you're done"
echo ""
echo "Press Ctrl+C to stop the UI when finished testing."
echo ""

# --- Cleanup function ---
cleanup() {
    echo ""
    echo "---"
    echo "Cleaning up: stopping servers..."
    ./scripts/server.sh stop > /dev/null 2>&1 || true
    echo "Cleanup complete."
}

# Trap EXIT and INT signals
trap cleanup EXIT INT

# --- Start API server if not running ---
echo "--- Checking API server status ---"
if curl -s --fail "$API_HEALTH_URL" > /dev/null 2>&1; then
    echo "✅ API server is already running at $API_HEALTH_URL"
else
    echo "Starting API server..."
    ./scripts/server.sh start

    echo "Waiting for API server to become healthy (max 30 seconds)..."
    for i in {1..30}; do
        if curl -s --fail "$API_HEALTH_URL" > /dev/null 2>&1; then
            echo "✅ API server is healthy"
            break
        fi
        echo -n "."
        sleep 1
    done

    if ! curl -s --fail "$API_HEALTH_URL" > /dev/null 2>&1; then
        echo ""
        echo "❌ API server failed to start within 30 seconds"
        echo "Check logs: ./logs/agentic_server.log"
        exit 1
    fi
fi

echo ""
echo "--- Launching Gradio UI ---"
echo "The UI will be available at: http://127.0.0.1:${UI_PORT}"
echo ""
echo "📋 Manual Test Checklist:"
echo "  1. UI loads without errors"
echo "  2. Can enter a prompt (try: 'Hello, this is a test')"
echo "  3. Submit button responds"
echo "  4. Status updates appear"
echo "  5. Log output shows agent activity"
echo "  6. Final state appears in JSON tab"
echo "  7. Archive report appears in Archive tab (for complex queries)"
echo ""
echo "Press Ctrl+C when you're done testing to stop the UI and cleanup."
echo "---"
echo ""

# Launch the UI (this will block until Ctrl+C)
python app/src/ui/gradio_app.py --port ${UI_PORT}
