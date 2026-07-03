@echo off
chcp 65001 >nul 2>&1
title 反检测浏览器 v2 - 验证模式

:: ══════════════════════════════════════════════════════
::   反检测浏览器 v2 · 验证模式
::   启动后自动输出指纹检测报告，用于调试反检测效果
::   普通使用请用 一键启动.bat
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

:: ── 命令行参数模式 ────────────────────────────────────
if not "%~1"=="" (
    set "TARGET_URL=%~1"
    goto :launch
)

:: ── 交互式输入 ────────────────────────────────────────
cls
echo.
echo  ╔══════════════════════════════════════════════════╗
echo  ║       反检测浏览器 v2 · 验证模式                 ║
echo  ╚══════════════════════════════════════════════════╝
echo.
echo  请输入要检测的网址：
echo.
set /p TARGET_URL="网址: "

if "%TARGET_URL%"=="" set "TARGET_URL=about:blank"

:launch
echo.
echo  [启动中] 指纹检测报告将自动输出...
echo.

"%PYTHON%" cli.py verify "%TARGET_URL%"

pause
