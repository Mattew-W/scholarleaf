@echo off
chcp 65001 >nul 2>&1
set "ROOT=%~dp0.."
set "PYTHON=%ROOT%\.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
cd /d "%ROOT%"

title ScholarLeaf - Verify Mode

if "%~1"=="" (
    set "TARGET_URL=https://edqab.com"
) else (
    set "TARGET_URL=%~1"
)

echo [Verify] Target: %TARGET_URL%
"%PYTHON%" cli.py verify "%TARGET_URL%"
pause
