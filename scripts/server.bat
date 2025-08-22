@echo off
setlocal

rem This script is a simple wrapper around the Python-based server control script.

rem Activate the virtual environment
rem Go to the parent directory of this script (the project root)
pushd "%~dp0.."

rem Activate the virtual environment if it exists
if exist .\.venv_agents_windows\Scripts\activate.bat (
    call .\.venv_agents_windows\Scripts\activate.bat
)

rem Run the Python server control script, passing all arguments
python scripts/server.py %*