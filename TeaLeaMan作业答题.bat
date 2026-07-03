@echo off
chcp 65001 >nul 2>&1
title TeaLeaMan v2 - 作业答题模式

:: ══════════════════════════════════════════════════════
::   TeaLeaMan 在线作业 · 快捷入口
::   启动监控模式，自动答题（需先登录）
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

:: ── 登录信息（交互式输入）──────────────────────────────
set "TEALEAMAN_URL=https://edqab.com/tealeaman/studentpage.jsp?orgnum=0"

echo.
echo  [提示] 默认打开 TeaLeaMan 登录页
echo  关闭浏览器窗口退出
echo.

"%PYTHON%" cli.py monitor "%TEALEAMAN_URL%"
