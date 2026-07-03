@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

:: ScholarLeaf - One-Click Launcher (Auto-dependency check)
set "ROOT=%~dp0.."
set "PIP_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple"
cd /d "%ROOT%"

title ScholarLeaf - Auto Dependency Check

cls
echo.
echo  +============================================================+
echo  ^|          ScholarLeaf - Auto Dependency Launcher           ^|
echo  +============================================================+
echo.

:: [1/4] Locate Python
echo  [1/4] Locating Python interpreter...
set "PYTHON=%ROOT%\.venv\Scripts\python.exe"
if exist "%PYTHON%" (
    for /f "tokens=*" %%v in ('"%PYTHON%" --version 2^>^&1') do set "PY_VER=%%v"
    echo         [OK] Using virtual environment Python
    echo              %PY_VER%
    goto :python_done
)
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo         [FAIL] Python not found
    echo.
    echo  [Error] Please install Python 3.8+ and add it to PATH.
    pause
    exit /b 1
)
set "PYTHON=python"
:python_done

:: [2/4] Scan dependencies
echo.
echo  [2/4] Scanning dependencies...
set "DEPS_LOG=%TEMP%\sl_deps_%RANDOM%.log"
"%PYTHON%" "%ROOT%\check_deps.py" > "%DEPS_LOG%" 2>&1
type "%DEPS_LOG%"
del /f /q "%DEPS_LOG%" >nul 2>&1
if %errorlevel% equ 0 goto :deps_ready

:: [3/4] Auto-install
echo.
echo  [3/4] Installing missing dependencies...
"%PYTHON%" -m pip install -r "%ROOT%\requirements.txt" --upgrade --progress-bar on -i "%PIP_INDEX%"

:: [4/4] Recheck
echo.
echo  [4/4] Rechecking...
set "DEPS_LOG2=%TEMP%\sl_deps2_%RANDOM%.log"
"%PYTHON%" "%ROOT%\check_deps.py" > "%DEPS_LOG2%" 2>&1
type "%DEPS_LOG2%"
del /f /q "%DEPS_LOG2%" >nul 2>&1
if %errorlevel% neq 0 (
    echo [4/4] Recheck failed. Please fix dependencies manually.
    pause
    exit /b 1
)
echo [4/4] All dependencies OK
goto :launch

:deps_ready
echo [2/4] Dependencies satisfied

:launch
echo.
echo  ================================================================
echo   Environment ready. Launching...
echo  ================================================================
echo.

if not "%~1"=="" (
    set "TARGET_URL=%~1"
) else (
    set "TARGET_URL=about:blank"
)

"%PYTHON%" "%ROOT%\cli.py" launch "%TARGET_URL%"

echo.
echo  [Exited]
pause
