@echo off
rem This script activates the virtual environment, installs dependencies,
rem and runs the FastAPI application server for Windows users.

rem Activate the virtual environment
call .\.venv_agents_windows\Scripts\activate.bat

rem Load LOG_LEVEL from .env file if it exists
if exist .env (
    for /f "tokens=1,* delims==" %%a in ('findstr /R /C:"^LOG_LEVEL=" .env') do (
        set "LOG_LEVEL=%%b"
    )
)

rem Set default log level if not found in .env or file
if not defined LOG_LEVEL set "LOG_LEVEL=info"

echo "Starting Agentic API server with Uvicorn..."
echo "Log level set to: %LOG_LEVEL%"
echo "Access the API at http://127.0.0.1:8000"
echo "View the interactive documentation at http://127.0.0.1:8000/docs"

rem Run the FastAPI server using uvicorn
rem --reload will automatically restart the server when code changes are detected
uvicorn app.src.api:app --host 0.0.0.0 --port 8000 --reload --log-level %LOG_LEVEL%