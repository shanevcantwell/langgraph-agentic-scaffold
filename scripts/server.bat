@echo off
setlocal

rem This script activates the virtual environment and manages the FastAPI application server for Windows users. It supports start, stop, status, and restart commands.

rem Activate the virtual environment
rem Go to the parent directory of this script (the project root)
cd /d "%~dp0.."
if exist .\.venv_agents_windows\Scripts\activate.bat (
    call .\.venv_agents_windows\Scripts\activate.bat
)

rem --- Configuration ---
set "RUN_DIR=%cd%\.run"
set "LOGS_DIR=%cd%\logs"
set "SERVER_PID_FILE=%RUN_DIR%\agentic_server.pid"
set "SERVER_LOG_FILE=%LOGS_DIR%\agentic_server.log"
set "PORT=8000"

rem Load LOG_LEVEL from .env file, default to "info"
set "LOG_LEVEL_UVICORN=info"
if exist .env (
    for /f "tokens=1,* delims==" %%a in ('findstr /R /C:"^LOG_LEVEL=" .env') do (
        set "LOG_LEVEL_UVICORN=%%b"
    )
)

rem --- Functions ---
goto :main

:start_server
    if exist "%SERVER_PID_FILE%" (
        set /p PID=<"%SERVER_PID_FILE%"
        tasklist /FI "PID eq %PID%" 2>NUL | find /I "%PID%" >NUL
        if "%ERRORLEVEL%"=="0" (
            echo Server is already running with PID %PID%.
            exit /b 0
        ) else (
            echo Stale PID file found. Removing...
            del "%SERVER_PID_FILE%"
        )
    )
    mkdir "%RUN_DIR%" 2>nul
    mkdir "%LOGS_DIR%" 2>nul
    echo Starting Agentic API server with Uvicorn...
    echo Access the API at http://127.0.0.1:%PORT%
    echo Log level set to: %LOG_LEVEL_UVICORN%
    echo View the interactive documentation at http://127.0.0.1:%PORT%/docs
    echo Server logs are at: %SERVER_LOG_FILE%
    
    rem Use PowerShell to start uvicorn in a new process and get its PID.
    rem The application's own logging configuration handles writing to the log file.
    rem We do not redirect stdout/stderr here to avoid duplicating log entries.
    powershell -Command "Start-Process python -ArgumentList '-m uvicorn app.src.api:app --host 0.0.0.0 --port %PORT% --log-level %LOG_LEVEL_UVICORN%' -PassThru | Select-Object -ExpandProperty Id | Out-File -FilePath '%SERVER_PID_FILE%' -Encoding ascii"
    
    rem Brief pause to allow PID file to be written
    timeout /t 1 /nobreak >nul
    if exist "%SERVER_PID_FILE%" (
        set /p PID=<"%SERVER_PID_FILE%"
        echo Server started with PID %PID%.
    ) else (
        echo Failed to start server or get PID.
    )
    exit /b 0

:stop_server
    if not exist "%SERVER_PID_FILE%" (
        echo Server PID file not found. Server may not be running.
        exit /b 1
    )
    set /p PID=<"%SERVER_PID_FILE%"
    tasklist /FI "PID eq %PID%" 2>NUL | find /I "%PID%" >NUL
    if "%ERRORLEVEL%"=="0" (
        echo Stopping server with PID %PID%...
        taskkill /F /PID %PID% >nul
        echo Server stopped.
    ) else (
        echo Server not running or PID %PID% is stale.
    )
    del "%SERVER_PID_FILE%"
    exit /b 0

:status_server
    if exist "%SERVER_PID_FILE%" (
        set /p PID=<"%SERVER_PID_FILE%"
        tasklist /FI "PID eq %PID%" 2>NUL | find /I "%PID%" >NUL
        if "%ERRORLEVEL%"=="0" (
            echo Server is running with PID %PID%.
            exit /b 0
        ) else (
            echo Server PID file found, but process %PID% is not running. PID file is stale.
            exit /b 1
        )
    ) else (
        rem Fallback: Check if anything is listening on the port
        netstat -ano | findstr /R /C:"TCP.*:%PORT%.*LISTENING" >NUL
        if "%ERRORLEVEL%"=="0" (
            echo Server is running on port %PORT% ^(PID file not found^).
            exit /b 0
        ) else (
            echo Server is not running.
            exit /b 1
        )
    )

:restart_server
    echo Restarting server...
    call :stop_server
    call :start_server
    exit /b 0

:main
    if /I "%1"=="start" (
        goto :start_server
    )
    if /I "%1"=="stop" (
        goto :stop_server
    )
    if /I "%1"=="status" (
        goto :status_server
    )
    if /I "%1"=="restart" (
        goto :restart_server
    )

    echo Usage: %~n0 {start^|stop^|restart^|status}
    exit /b 1