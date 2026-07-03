@echo off
chcp 65001 >nul 2>&1
set "ROOT=%~dp0.."
set "PYTHON=%ROOT%\.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
cd /d "%ROOT%"

title ScholarLeaf - Diagnose Mode

if "%~1"=="" (
    set "TARGET_URL=https://edqab.com/tealeaman/studentassign.jsp"
) else (
    set "TARGET_URL=%~1"
)

echo [Diagnose] Target: %TARGET_URL%
"%PYTHON%" cli.py diagnose "%TARGET_URL%"
pause
