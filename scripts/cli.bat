@echo off
rem This script provides a convenient way to run the CLI for Windows.
rem It ensures the command is run from the project root and passes all arguments to the CLI script.

rem Go to the parent directory of this script (the project root).
pushd "%~dp0.."

rem Activate virtual environment if it exists
if exist .\.venv_agents_windows\Scripts\activate.bat (
    call .\.venv_agents_windows\Scripts\activate.bat
)

rem Smart default command logic:
rem If first arg is not a known command (invoke, stream, distill) and not a flag (starts with -),
rem prepend "invoke" to make bare prompts work
set first_arg=%~1
if "%first_arg%"=="" (
    rem No arguments - just pass through
    python -m app.src.cli %*
) else if "%first_arg%"=="invoke" (
    python -m app.src.cli %*
) else if "%first_arg%"=="stream" (
    python -m app.src.cli %*
) else if "%first_arg%"=="distill" (
    python -m app.src.cli %*
) else if "%first_arg:~0,1%"=="-" (
    rem First arg is a flag - pass through
    python -m app.src.cli %*
) else (
    rem First arg is not a command or flag - default to invoke
    python -m app.src.cli invoke %*
)

popd