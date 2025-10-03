#!/bin/bash
# /start.sh - Starts both the API and UI services for development.

# Exit immediately if a command exits.
set -e

# --- ADD THIS SECTION ---
# Explicitly export proxy variables to ensure they are inherited by all child processes,
# including those spawned by Uvicorn's reloader.
export HTTP_PROXY="http://proxy:3128"
export HTTPS_PROXY="http://proxy:3128"
export NO_PROXY="localhost,127.0.0.1"
export no_proxy="localhost,127.0.0.1"
# ------------------------

echo "--- Starting FastAPI server (with reload) ---"
uvicorn app.src.api:app --host 0.0.0.0 --port 8000 --reload --log-config log_config.yaml &

echo "--- Starting Gradio UI server ---"
python -m app.src.ui --port 5003 &

# Wait for any process to exit
wait -n

# Exit with status of process that exited first
exit $?