#!/bin/bash
# /start.sh - Starts both the API and UI services for development.

# Exit immediately if a command exits.
set -e

# Trap SIGINT and SIGTERM to gracefully shut down background processes
trap 'kill $(jobs -p); exit' SIGINT SIGTERM

echo "--- Running Connectivity Verification ---"
python -m app.src.utils.verify_connectivity
if [ $? -ne 0 ]; then
    echo "❌ Connectivity check failed. Exiting."
    exit 1
fi

echo "--- Starting FastAPI server (with reload) ---"
# Use explicit reload directories to prevent the log file from triggering reloads.
# Watch the 'app' directory for changes, but exclude the 'logs' directory.
uvicorn app.src.api:app --host 0.0.0.0 --port 8000 --reload \
--reload-dir app \
--reload-exclude "logs/*" \
--reload-exclude "*.pyc" \
--reload-exclude "__pycache__/*" \
--log-config log_config.yaml &

echo "--- Starting Gradio UI server ---"
python -m app.src.ui --port 5003 &

# Wait for any process to exit
wait -n

# Exit with status of process that exited first
exit $?