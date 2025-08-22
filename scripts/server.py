import typer
import psutil
import subprocess
import os
import sys
import time
import logging
from dotenv import load_dotenv
from typing_extensions import Annotated

# --- Configuration ---
# This script should be run from the project root.
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RUN_DIR = os.path.join(PROJECT_ROOT, ".run")
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")

# --- Environment Loading ---
# Load environment variables from .env file in the project root.
# This ensures the server process inherits the necessary secrets.
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

SERVER_PID_FILE = os.path.join(RUN_DIR, "server.pid")
SERVER_LOG_FILE = os.path.join(LOGS_DIR, "agentic_server.log")
LOG_CONFIG_FILE = os.path.join(PROJECT_ROOT, "log_config.yaml")
PORT = 8000

# --- Setup Logging ---
# This script has its own simple logger for control-related messages.
def setup_logging():
    """Sets up logging for this control script."""
    os.makedirs(LOGS_DIR, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - [SERVER_CONTROL] - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )

app = typer.Typer(
    help="A Python-based server control script for the agentic application."
)

def _is_server_running() -> psutil.Process | None:
    """Checks if the server process is running based on the PID file."""
    if not os.path.exists(SERVER_PID_FILE):
        return None
    try:
        with open(SERVER_PID_FILE, "r") as f:
            pid = int(f.read().strip())
        proc = psutil.Process(pid)
        # Check if the process name contains 'python' or 'uvicorn' for extra safety
        if 'python' in proc.name().lower() or 'uvicorn' in proc.name().lower():
            return proc
    except (psutil.NoSuchProcess, FileNotFoundError, ValueError):
        if os.path.exists(SERVER_PID_FILE):
            logging.warning(f"Removing stale PID file: {SERVER_PID_FILE}")
            os.remove(SERVER_PID_FILE)
        return None
    return None

@app.command()
def start(
    foreground: Annotated[bool, typer.Option(
        "--foreground",
        "-f",
        help="Run the server in the foreground, streaming logs to the console."
    )] = False
):
    """Starts the Uvicorn server. By default, it runs as a detached background process."""
    if proc := _is_server_running():
        logging.info(f"Server is already running with PID {proc.pid}.")
        return

    command = [
        sys.executable,  # Use the same python interpreter that's running this script
        "-m", "uvicorn", "app.src.api:app",
        "--host", "0.0.0.0", "--port", str(PORT),
        "--log-config", LOG_CONFIG_FILE
    ]

    if foreground:
        logging.info("Starting Agentic API server in the foreground...")
        logging.info("Press Ctrl+C to stop the server.")
        try:
            # When running in the foreground, we execute directly and block.
            # The Uvicorn process will inherit the standard streams.
            subprocess.run(command, cwd=PROJECT_ROOT, check=True)
        except KeyboardInterrupt:
            logging.info("\nServer stopped by user.")
        except subprocess.CalledProcessError as e:
            logging.error(f"Server process failed with exit code {e.returncode}.")
        return

    # --- Background process logic ---
    os.makedirs(RUN_DIR, exist_ok=True)
    logging.info("Starting Agentic API server...")
    logging.info(f"Server logs are configured to be written to: {SERVER_LOG_FILE}")

    # Start the process with stdout and stderr piped so we can check for startup errors.
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,  # Redirect stderr to stdout
        text=True,  # Decode streams as text
        cwd=PROJECT_ROOT,
        # On Unix, start_new_session=True detaches the process from the controlling terminal
        # On Windows, DETACHED_PROCESS flag is used for the same purpose.
        creationflags=subprocess.DETACHED_PROCESS if sys.platform == "win32" else 0,
        start_new_session=(sys.platform != "win32")
    )

    # --- Health Check ---
    logging.info("Performing server health check...")
    time.sleep(3)  # Give it a few seconds to start up or fail.

    if process.poll() is not None:
        logging.error("="*80)
        logging.error("SERVER FAILED TO START. See error output below.")
        logging.error("="*80)
        startup_output, _ = process.communicate()
        logging.error(startup_output)
        with open(SERVER_LOG_FILE, "a") as f:
            f.write("\n" + "="*80 + "\n")
            f.write("SERVER FAILED TO START\n")
            f.write(startup_output)
            f.write("="*80 + "\n")
        return

    with open(SERVER_PID_FILE, "w") as f:
        f.write(str(process.pid))

    logging.info(f"Server started successfully with PID {process.pid}.")
    logging.info(f"Access the API at http://127.0.0.1:{PORT}")
    if process.stdout:
        process.stdout.close()

@app.command()
def stop():
    """Stops the running Uvicorn server."""
    proc = _is_server_running()
    if not proc:
        logging.info("Server is not running.")
        # If the process isn't running but the PID file exists, clean it up.
        if os.path.exists(SERVER_PID_FILE):
            logging.warning(f"Removing stale PID file: {SERVER_PID_FILE}")
            os.remove(SERVER_PID_FILE)
        return

    logging.info(f"Stopping server with PID {proc.pid}...")
    try:
        # Graceful shutdown
        proc.terminate()
        # Wait for the process to terminate
        proc.wait(timeout=5)
        logging.info("Server stopped gracefully.")
    except psutil.TimeoutExpired:
        logging.warning("Server did not stop gracefully after 5 seconds. Forcing termination...")
        proc.kill()
        proc.wait() # Wait for the killed process to be reaped
        logging.info("Server terminated.")
    except psutil.NoSuchProcess:
        # This can happen if the process terminates between the _is_server_running() check and proc.terminate()
        logging.info("Process already stopped.")
    finally:
        # Ensure the PID file is always removed after a stop attempt
        if os.path.exists(SERVER_PID_FILE):
            os.remove(SERVER_PID_FILE)

@app.command()
def restart():
    """Restarts the server."""
    logging.info("Restarting server...")
    stop()
    time.sleep(1)
    start()

@app.command()
def status():
    """Checks the status of the server."""
    if proc := _is_server_running():
        logging.info(f"Server is RUNNING with PID {proc.pid}.")
        logging.info(f"  - CPU: {proc.cpu_percent(interval=0.1)}%")
        logging.info(f"  - Memory: {proc.memory_info().rss / 1024 / 1024:.2f} MB")
    else:
        logging.info("Server is STOPPED.")

if __name__ == "__main__":
    setup_logging()
    app()