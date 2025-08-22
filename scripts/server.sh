#!/bin/bash

# Get the directory where the script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR/.."
RUN_DIR="$PROJECT_ROOT/run"
LOGS_DIR="$PROJECT_ROOT/logs"
SERVER_PID_FILE="$RUN_DIR/server.pid"
PORT=${PORT:-8000}

# Function to start the server
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

    # Activate virtual environment
    if [ -d "$PROJECT_ROOT/venv" ]; then
        echo "Activating Python virtual environment..."
        source "$PROJECT_ROOT/venv/bin/activate"
    else
        echo "WARNING: Virtual environment not found at '$PROJECT_ROOT/venv'."
    fi

    export PYTHONPATH="$PROJECT_ROOT"

    echo "Access the API at http://127.0.0.1:${PORT}"
    echo "Log level is now controlled by 'log_config.yaml'."

    # The --log-config flag is the single source of truth for logging.
    # The --log-level flag has been removed to prevent conflicts.
    PYTHONUNBUFFERED=1 uvicorn app.src.api:app --host 0.0.0.0 --port ${PORT} \
        --log-config "$PROJECT_ROOT/log_config.yaml" &
    
    echo $! > "$SERVER_PID_FILE"
    echo "Server started with PID $(cat "$SERVER_PID_FILE")."
}

# Function to stop the server
stop_server() {
    local PID
    if [ -f "$SERVER_PID_FILE" ]; then
        PID=$(cat "$SERVER_PID_FILE")
    else
        echo "Server PID file not found. Checking for process on port ${PORT}..."
        PID=$(lsof -ti :${PORT} 2>/dev/null)
        if [ -z "$PID" ]; then
            echo "Server is not running (no PID file and nothing on port ${PORT})."
            return 1
        fi
    fi

    if [ -n "$PID" ] && ps -p "$PID" > /dev/null; then
        echo "Stopping server with PID $PID..."
        kill "$PID"
        for i in {1..10}; do
            if ! ps -p "$PID" > /dev/null; then
                echo "Server stopped."
                rm -f "$SERVER_PID_FILE"
                return 0
            fi
            sleep 0.5
        done
        echo "Server did not stop gracefully. It may need to be killed manually."
        return 1
    else
        echo "Server is not running."
        rm -f "$SERVER_PID_FILE"
        return 1
    fi
}

# Main logic
case "$1" in
    start)
        start_server
        ;;
    stop)
        stop_server
        ;;
    restart)
        echo "Restarting server..."
        stop_server
        sleep 1
        start_server
        ;;
    status)
        if [ -f "$SERVER_PID_FILE" ]; then
            PID=$(cat "$SERVER_PID_FILE")
            if ps -p $PID > /dev/null; then
                echo "Server is running with PID $PID."
            else
                echo "Server is not running, but a stale PID file exists."
            fi
        else
            echo "Server is not running."
        fi
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac
