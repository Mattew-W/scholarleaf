@echo off
chcp 65001 >nul 2>&1
set "ROOT=%~dp0.."
set "PYTHON=%ROOT%\.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
cd /d "%ROOT%"

title ScholarLeaf - Monitor Mode

if "%~1"=="" (
    set "TARGET_URL=https://edqab.com/tealeaman/studentpage.jsp?orgnum=0"
) else (
    set "TARGET_URL=%~1"
)

echo [Monitor] Target: %TARGET_URL%
"%PYTHON%" cli.py monitor "%TARGET_URL%"
pause
