#!/bin/bash
# This script is for Linux/macOS users.

# Activate the Python virtual environment
source ./.venv_agents/bin/activate

# Run the main application module, passing along any command-line arguments
python -m app.src.main "$@"