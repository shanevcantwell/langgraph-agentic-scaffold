#!/bin/bash
# This script compiles pyproject.toml into requirements files using pip-tools.
# This ensures that we have pinned, reproducible dependencies.

echo "Compiling base requirements..."
pip-compile --resolver=backtracking -o requirements.txt pyproject.toml

echo "Compiling development requirements..."
pip-compile --resolver=backtracking --extra dev -o requirements-dev.txt pyproject.toml

echo "Done. Please commit the updated requirements.txt and requirements-dev.txt files."