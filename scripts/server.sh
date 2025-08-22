#!/bin/bash
# This script is a simple wrapper around the Python-based server control script.

# Exit immediately if a command exits with a non-zero status.
set -e

# Get the directory of the script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
# Go to the parent directory (project root)
cd "$SCRIPT_DIR/.."

# Activate virtual environment if it exists
if [ -d ".venv_agents" ]; then
    source ./.venv_agents/bin/activate
fi

# Run the Python server control script, passing all arguments
python scripts/server.py "$@"
