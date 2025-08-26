@echo off
REM This script sets up the development environment for the langgraph-agentic-scaffold.

REM Get the directory of the script
set "SCRIPT_DIR=%~dp0"
REM Go to the parent directory (project root)
pushd "%SCRIPT_DIR%.."

echo --- Setting up Python virtual environment ---
python -m venv .venv_agents_windows
call .venv_agents_windows\Scripts\activate.bat

echo --- Installing Python dependencies ---
pip install -r requirements-dev.txt

echo --- Checking for jq dependency ---
where jq >nul 2>nul
if %errorlevel% neq 0 (
    echo Warning: jq is not installed. It is required for running verification scripts.
    echo Please install jq using your system's package manager or download from:
    echo   https://stedolan.github.io/jq/download/
) else (
    echo jq is installed.
)

echo --- Copying example configuration files ---
copy .env.example .env >nul
copy config.yaml.example config.yaml >nul
copy user_settings.yaml.example user_settings.yaml >nul

echo ---
echo ✅ Development environment setup complete.
echo To activate the virtual environment, run: .venv_agents_windows\Scripts\activate.bat
echo Then, edit .env with your API keys and config.yaml to define your agent setup.
echo.
echo Note for Windows Users: If you encounter an UnauthorizedAccess error when running PowerShell scripts (e.g., verify.ps1),
echo you may need to adjust your PowerShell execution policy. Open PowerShell with Administrator privileges and run:
echo   Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned

popd
