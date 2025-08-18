#!/bin/bash
# This script provides a convenient way to run the CLI for Linux/macOS.
# It ensures the command is run from the project root and passes all arguments to the CLI script.

# Get the directory of the script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
# Go to the parent directory (project root)
cd "$SCRIPT_DIR/.."

# Activate virtual environment if it exists
if [ -d ".venv_agents" ]; then
    source ./.venv_agents/bin/activate
fi

# Run the CLI module, passing all script arguments
python -m app.src.cli "$@"