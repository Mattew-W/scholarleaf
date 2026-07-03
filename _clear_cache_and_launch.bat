@echo off
chcp 65001 >nul 2>&1
title 反检测浏览器 v2 - 清理缓存并启动

:: ══════════════════════════════════════════════════════
::   清理 Python 缓存与残留 Chromium 进程，然后启动
:: ══════════════════════════════════════════════════════

set "ROOT_DIR=%~dp0"
set "ROOT_DIR=%ROOT_DIR:~0,-1%"

:: ── 清理 Python 缓存 ──────────────────────────────────
echo [清理] 删除 Python 缓存文件...
rd /s /q "%ROOT_DIR%\__pycache__" 2>nul
rd /s /q "%ROOT_DIR%\core\__pycache__" 2>nul
rd /s /q "%ROOT_DIR%\launch\__pycache__" 2>nul
rd /s /q "%ROOT_DIR%\auto\__pycache__" 2>nul
del /q "%ROOT_DIR%\*.pyc" 2>nul
echo [清理] 完成

:: ── 关闭残留 Chromium 进程 ────────────────────────────
echo [清理] 关闭残留 Chromium 进程...
taskkill /f /im chromium.exe 2>nul
taskkill /f /im chrome.exe 2>nul
echo [清理] 完成

:: ── 选择 Python 解释器（优先 .venv，否则系统 Python）──
set "PYTHON=%ROOT_DIR%\.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    where python >nul 2>&1
    if %errorlevel% neq 0 (
        echo [错误] 未找到 Python，请先安装 Python 3.8+
        pause
        exit /b 1
    )
    set "PYTHON=python"
)

:: ── 启动浏览器 ────────────────────────────────────────
"%PYTHON%" cli.py launch %*

pause
