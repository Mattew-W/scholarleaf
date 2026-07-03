@echo off
chcp 65001 >nul 2>&1
title 反检测浏览器 v2 - 全功能启动器

:: ════════════════════════════════════════════════════════
::   反检测浏览器 v2 · 全功能启动器
::   支持: 纯净 / 监控 / 验证 / 诊断 / 查看日志
:: ════════════════════════════════════════════════════════

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

:: ── 直接参数模式 ──────────────────────────────────────
::   支持: 一键启动(全能版).bat launch <URL>
::         一键启动(全能版).bat monitor <URL>
::         一键启动(全能版).bat verify <URL>
::         一键启动(全能版).bat diagnose [URL]
if not "%~1"=="" (
    "%PYTHON%" cli.py %*
    pause
    exit /b 0
)

:: ── 交互式菜单 ────────────────────────────────────────
:menu
cls
echo.
echo  ╔══════════════════════════════════════════════════╗
echo  ║       反检测浏览器 v2 · 全功能启动器             ║
echo  ╚══════════════════════════════════════════════════╝
echo.
echo  [1] 纯净模式   - 只启动反检测浏览器
echo  [2] 监控模式   - 反检测 + 自动答题监控
echo  [3] 验证模式   - 输出指纹检测报告
echo  [4] 诊断模式   - 检查页面按钮/frameset 状态
echo  [5] 查看日志   - 查看最近监控日志
echo  [0] 退出
echo.
set /p CHOICE="选择模式: "

if "%CHOICE%"=="1" goto :clean
if "%CHOICE%"=="2" goto :monitor
if "%CHOICE%"=="3" goto :verify
if "%CHOICE%"=="4" goto :diagnose
if "%CHOICE%"=="5" goto :viewlog
if "%CHOICE%"=="0" exit /b 0

echo [错误] 无效选择，请重新输入
pause
goto :menu

:clean
call :input_url
set "MODE=launch"
goto :run

:monitor
call :input_url
set "MODE=monitor"
goto :run

:verify
call :input_url
set "MODE=verify"
goto :run

:diagnose
call :input_url
set "MODE=diagnose"
goto :run

:viewlog
set "MODE=view-log"
set "TARGET_URL="
goto :run

:input_url
echo.
set /p TARGET_URL="请输入网址 (默认 about:blank): "
if "%TARGET_URL%"=="" set "TARGET_URL=about:blank"
goto :eof

:run
echo.
echo  [启动中] 模式: %MODE%  网址: %TARGET_URL%
echo.
if "%TARGET_URL%"=="" (
    "%PYTHON%" cli.py %MODE%
) else (
    "%PYTHON%" cli.py %MODE% "%TARGET_URL%"
)
pause
goto :menu
