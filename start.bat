@echo off
REM ============================================================
REM Enterprise Data Agent - Windows Startup Script
REM Conda env: agent-env
REM ============================================================

set PROJ_DIR=%~dp0
set PYTHON=C:\miniconda3\envs\agent-env\python.exe

cd /d "%PROJ_DIR%"

echo [1/2] Starting FastAPI backend (port 8000)...
start "FastAPI-Backend" /min "%PYTHON%" fastapi_server.py

timeout /t 3 /nobreak >nul

echo [2/2] Starting Streamlit frontend (port 8501)...
start "Streamlit-Frontend" /min "%PYTHON%" -m streamlit run streamlit_web.py --server.port=8501 --server.address=0.0.0.0 --server.headless=true

echo.
echo ============================================================
echo  Services started:
echo    FastAPI backend:  http://127.0.0.1:8000
echo    Streamlit frontend: http://127.0.0.1:8501
echo ============================================================
echo  To stop: close the FastAPI-Backend and Streamlit-Frontend windows
echo  Or use Task Manager to end python.exe processes
echo ============================================================
pause