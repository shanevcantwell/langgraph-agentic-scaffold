#!/bin/bash
# This script activates the virtual environment, installs dependencies,
# and manages the FastAPI application server for Linux/macOS users.

# Activate the virtual environment
source ./.venv_agents/bin/activate

SERVER_PID_FILE="/tmp/specialisthub_server.pid"

start_server() {
    if [ -f "$SERVER_PID_FILE" ]; then
        PID=$(cat "$SERVER_PID_FILE")
        if ps -p $PID > /dev/null; then
            echo "Server is already running with PID $PID."
            exit 0
        else
            echo "Stale PID file found. Removing..."
            rm "$SERVER_PID_FILE"
        fi
    fi

    echo "Starting SpecialistHub API server with Uvicorn..."
    echo "Access the API at http://127.0.0.1:8000"
    echo "View the interactive documentation at http://127.0.0.1:8000/docs"

    # Run the FastAPI server using uvicorn in the background and capture its PID
    PYTHONUNBUFFERED=1 uvicorn app.src.api:app --host 0.0.0.0 --port 8000 2>&1 &
    echo $! > "$SERVER_PID_FILE"
    echo "Server started with PID $(cat "$SERVER_PID_FILE")."
}

stop_server() {
    if [ -f "$SERVER_PID_FILE" ]; then
        PID=$(cat "$SERVER_PID_FILE")
        if ps -p $PID > /dev/null; then
            echo "Stopping server with PID $PID..."
            kill $PID
            # Wait for the process to terminate
            for i in {1..10}; do
                if ! ps -p $PID > /dev/null; then
                    echo "Server stopped."
                    rm "$SERVER_PID_FILE"
                    return 0 # Indicate success
                fi
                sleep 1
            done
            echo "Server did not stop gracefully. Attempting to force kill..."
            kill -9 $PID
            rm "$SERVER_PID_FILE"
            echo "Server force killed."
            return 0 # Indicate success
        else
            echo "Server not running or PID file is stale. Removing PID file."
            rm "$SERVER_PID_FILE"
            return 1 # Indicate failure (not running)
        fi
    else
        echo "Server PID file not found. Server may not be running."
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
        PORT_PID=$(lsof -ti :8000 2>/dev/null)
        if [ -n "$PORT_PID" ]; then
            echo "Server is running on port 8000 with PID $PORT_PID (PID file not found)."
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