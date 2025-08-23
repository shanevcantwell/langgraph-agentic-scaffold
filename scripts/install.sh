#!/bin/bash
# This script sets up the development environment for the langgraph-agentic-scaffold.

# Exit immediately if a command exits with a non-zero status.
set -e

# Get the directory of the script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
# Go to the parent directory (project root)
cd "$SCRIPT_DIR/.."

echo "--- Setting up Python virtual environment ---"
python3 -m venv .venv_agents
source ./.venv_agents/bin/activate

echo "--- Installing Python dependencies ---"
pip install -r requirements-dev.txt

echo "--- Checking for jq dependency ---"
if ! command -v jq &> /dev/null
then
    echo "Warning: jq is not installed. It is required for running verification scripts."
    echo "Please install jq using your system's package manager:"
    echo "  On Debian/Ubuntu: sudo apt-get install jq"
    echo "  On macOS (using Homebrew): brew install jq"
    echo "  For other systems, please refer to https://stedolan.github.io/jq/download/"
else
    echo "jq is installed."
fi

echo "--- Copying example configuration files ---"
cp .env.example .env
cp config.yaml.example config.yaml
cp user_settings.yaml.example user_settings.yaml

echo "---"
echo "✅ Development environment setup complete."
echo "To activate the virtual environment, run: source ./.venv_agents/bin/activate"
echo "Then, edit .env with your API keys and config.yaml to define your agent setup."
