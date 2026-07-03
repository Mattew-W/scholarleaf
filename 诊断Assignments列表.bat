@echo off
chcp 65001 >nul 2>&1
title TeaLeaMan - 诊断 Assignments 列表

:: ══════════════════════════════════════════════════════
::   诊断 TeaLeaMan 作业列表页面，检查按钮显示状态
:: ══════════════════════════════════════════════════════

:: ── 选择 Python 解释器（优先 .venv，否则系统 Python）──
set "ROOT=%~dp0"
set "PYTHON=%ROOT%.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    where python >nul 2>&1
    if %errorlevel% neq 0 (
        echo [错误] 未找到 Python，请先安装 Python 3.8+
        pause
        exit /b 1
    )
    set "PYTHON=python"
)

:: ── 检查依赖 ──────────────────────────────────────────
"%PYTHON%" -c "import patchright" >nul 2>&1
if %errorlevel% neq 0 (
    echo [提示] 首次运行，正在安装依赖...
    "%PYTHON%" -m pip install -r requirements.txt
)

"%PYTHON%" cli.py diagnose https://edqab.com/tealeaman/studentassign.jsp

pause
