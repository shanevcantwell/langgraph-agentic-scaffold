#!/bin/bash
# This script activates the virtual environment, installs dependencies,
# and manages the FastAPI application server for Linux/macOS users.

# Ensure the script is run from the project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR/.."

# Activate the virtual environment
source ./.venv_agents/bin/activate

# Load environment variables from .env file if it exists.
# This allows for configuration of LOG_LEVEL, etc.
if [ -f .env ]; then
  set -a # automatically export all variables
  source .env
  set +a
fi

RUN_DIR="$(pwd)/.run"
LOGS_DIR="$(pwd)/logs"
SERVER_PID_FILE="$RUN_DIR/agentic_server.pid"
SERVER_LOG_FILE="$LOGS_DIR/agentic_server.log"
PORT=8000
LOG_LEVEL_UVICORN=${LOG_LEVEL:-info} # Default to info if not set

start_server() {
    if [ -f "$SERVER_PID_FILE" ]; then
        PID=$(cat "$SERVER_PID_FILE")
        if ps -p $PID > /dev/null; then
            echo "Server is already running with PID $PID."
            return 0
        else
            echo "Stale PID file found. Removing..."
            rm "$SERVER_PID_FILE"
        fi
    fi

    mkdir -p "$RUN_DIR"
    mkdir -p "$LOGS_DIR"
    echo "Starting Agentic API server with Uvicorn..."
    echo "Access the API at http://127.0.0.1:${PORT}"
    echo "Log level set to: ${LOG_LEVEL_UVICORN}"
    echo "View the interactive documentation at http://127.0.0.1:${PORT}/docs"
    echo "Server logs are at: $SERVER_LOG_FILE"

    # Run the FastAPI server using uvicorn. The application's logging configuration
    # handles writing to the log file. We redirect the script's console output
    # to /dev/null to prevent it from cluttering the console when run in the background.
    PYTHONUNBUFFERED=1 uvicorn app.src.api:app --host 0.0.0.0 --port ${PORT} --log-level "${LOG_LEVEL_UVICORN,,}" > /dev/null 2>&1 &
    echo $! > "$SERVER_PID_FILE"
    echo "Server started with PID $(cat "$SERVER_PID_FILE")."
}

stop_server() {
    local PID
    if [ -f "$SERVER_PID_FILE" ]; then
        PID=$(cat "$SERVER_PID_FILE")
    else
        echo "Server PID file not found. Checking for process on port ${PORT}..."
        PID=$(lsof -ti :${PORT} 2>/dev/null)
        if [ -z "$PID" ]; then
            echo "Server is not running (no PID file and nothing on port ${PORT})."
            return 1 # Indicate failure (not running)
        else
            echo "Found server on port ${PORT} with PID $PID."
        fi
    fi

    if ps -p $PID > /dev/null; then
        echo "Stopping server with PID $PID..."
        kill $PID
        # Wait for the process to terminate
        for i in {1..10}; do
            if ! ps -p $PID > /dev/null; then
                echo "Server stopped."
                [ -f "$SERVER_PID_FILE" ] && rm "$SERVER_PID_FILE"
                return 0 # Indicate success
            fi
            sleep 1
        done
        echo "Server did not stop gracefully. Attempting to force kill..."
        kill -9 $PID
        [ -f "$SERVER_PID_FILE" ] && rm "$SERVER_PID_FILE"
        echo "Server force killed."
        return 0 # Indicate success
    else
        echo "Server not running or PID $PID is stale. Removing PID file if it exists."
        [ -f "$SERVER_PID_FILE" ] && rm "$SERVER_PID_FILE"
        return 1 # Indicate failure (not running)
    fi
}

status_server() {
    if [ -f "$SERVER_PID_FILE" ]; then
        PID=$(cat "$SERVER_PID_FILE")
        if ps -p $PID > /dev/null; then
            echo "Server is running with PID $PID."
            return 0
        else
            echo "Server PID file found, but process $PID is not running. PID file is stale."
            return 1
        fi
    else
        # Fallback: Check if anything is listening on port 8000
        PORT_PID=$(lsof -ti :${PORT} 2>/dev/null)
        if [ -n "$PORT_PID" ]; then
            echo "Server is running on port ${PORT} with PID $PORT_PID (PID file not found)."
            return 0
        else
            echo "Server is not running."
            return 1
        fi
    fi
}

case "$1" in
    start)
        start_server
        ;;
    stop)
        stop_server
        ;;
    restart)
        stop_server
        start_server
        ;;
    status)
        status_server
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        exit 1
        ;;esac