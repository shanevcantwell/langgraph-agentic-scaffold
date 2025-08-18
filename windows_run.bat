@echo off
rem This script activates the virtual environment, installs dependencies,
rem and runs the FastAPI application server for Windows users.

rem Activate the virtual environment
call .\.venv_agents_windows\Scripts\activate.bat

echo "Installing/updating dependencies from requirements.txt..."
pip install -r requirements.txt

echo "Starting SpecialistHub API server with Uvicorn..."
echo "Access the API at http://127.0.0.1:8000"
echo "View the interactive documentation at http://127.0.0.1:8000/docs"

rem Run the FastAPI server using uvicorn
rem --reload will automatically restart the server when code changes are detected
uvicorn app.src.api:app --host 0.0.0.0 --port 8000 --reload