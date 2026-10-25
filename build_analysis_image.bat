@echo off
setlocal
cd /d "%~dp0"
docker build -f docker\Dockerfile.analysis -t enterprise-data-analyst-python:latest .
if errorlevel 1 exit /b %errorlevel%
echo Analysis image built: enterprise-data-analyst-python:latest
