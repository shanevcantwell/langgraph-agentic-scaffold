@echo off
rem This script is for Windows users.

rem Activate the Python virtual environment for Windows
call .\.venv_agents_windows\Scripts\activate.bat

rem Run the main application module, passing along any command-line arguments
python -m app.src.main %*