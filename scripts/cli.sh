#!/bin/bash
# This script provides a convenient way to run the CLI for Linux/macOS.
# It ensures the command is run from the project root and passes all arguments to the CLI script.

# Exit immediately if a command exits with a non-zero status.
set -e

# Get the directory of the script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
# Go to the parent directory (project root)
cd "$SCRIPT_DIR/.."

# Activate virtual environment if it exists
if [ -d ".venv_agents" ]; then
    . ./.venv_agents/bin/activate
fi

# Create an array to hold the arguments for the python script
args=()

# Smart default command logic:
# If first arg is not a known command (invoke, stream, distill) and not a flag (starts with -),
# prepend "invoke" to make bare prompts work
if [ $# -gt 0 ]; then
    first_arg="$1"
    if [[ "$first_arg" != "invoke" && "$first_arg" != "stream" && "$first_arg" != "distill" && "$first_arg" != -* ]]; then
        # First argument is not a command or flag, so default to invoke
        args+=("invoke")
    fi
fi

# Add all original arguments
for arg in "$@"; do
    args+=("$arg")
done

# Execute the python script, passing the arguments correctly
python -m app.src.cli "${args[@]}"