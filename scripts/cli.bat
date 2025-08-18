@echo off
rem This script provides a convenient way to run the CLI for Windows.
rem It ensures the command is run from the project root and passes all arguments to the CLI script.

rem Go to the parent directory of this script (the project root)
cd /d "%~dp0.."

rem Activate virtual environment if it exists
if exist .\.venv_agents_windows\Scripts\activate.bat (
    call .\.venv_agents_windows\Scripts\activate.bat
)

rem Run the CLI module, passing all script arguments
python -m app.src.cli %*