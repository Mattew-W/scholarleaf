@echo off
chcp 936 >nul 2>&1
setlocal EnableDelayedExpansion

:: ============================================================
::  反检测浏览器 v2 · 一键启动（依赖自检版）
::  功能：启动前自动检测并修复 Python 依赖
::  用法：双击运行，或拖拽网址到本文件
:: ============================================================

:: 项目根目录
set "ROOT=%~dp0"
set "PIP_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple"
cd /d "%ROOT%"

title 反检测浏览器 v2 - 依赖自检启动

cls
echo.
echo  +==============================================================+
echo  ^|        反检测浏览器 v2 - 依赖自检启动器                      ^|
echo  +==============================================================+
echo.

:: ------------------------------------------------------------
:: 步骤 1/4：定位 Python 解释器
:: ------------------------------------------------------------
echo  [1/4] 定位 Python 解释器...

set "PYTHON=%ROOT%.venv\Scripts\python.exe"
if exist "%PYTHON%" (
    for /f "tokens=*" %%v in ('"%PYTHON%" --version 2^>^&1') do set "PY_VER=%%v"
    echo        [OK] 使用虚拟环境 Python
    echo             %PY_VER%
    goto :python_done
)

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo        [FAIL] 未找到 Python 解释器
    echo.
    echo  [错误] 请先安装 Python 3.8 或更高版本，并添加到系统环境变量。
    echo        下载地址: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

set "PYTHON=python"
for /f "tokens=*" %%v in ('"%PYTHON%" --version 2^>^&1') do set "PY_VER=%%v"
echo        [OK] 使用系统 Python
echo             %PY_VER%

:python_done
echo.

:: ------------------------------------------------------------
:: 步骤 2/4：扫描项目依赖
:: ------------------------------------------------------------
echo  [2/4] 扫描项目依赖 (requirements.txt)...

set "CHECKER=%ROOT%check_deps.py"
if not exist "%CHECKER%" (
    echo        [FAIL] 未找到依赖检测脚本: check_deps.py
    pause
    exit /b 1
)

set "DEPS_LOG=%TEMP%\zb_deps_check_%RANDOM%.log"
"%PYTHON%" "%CHECKER%" > "%DEPS_LOG%" 2>&1
set "CHECK_RESULT=%errorlevel%"

for /f "usebackq tokens=*" %%a in ("%DEPS_LOG%") do (
    echo      %%a
)
del /f /q "%DEPS_LOG%" >nul 2>&1

if %CHECK_RESULT% equ 0 (
    echo.
    echo  [2/4] 依赖检查通过，无需安装
    goto :deps_ready
)

:: ------------------------------------------------------------
:: 步骤 3/4：自动安装缺失依赖
:: ------------------------------------------------------------
echo.
echo  [3/4] 检测到依赖缺失或版本不符，正在自动安装...
echo        命令: %PYTHON% -m pip install -r "%ROOT%requirements.txt" --upgrade -i "%PIP_INDEX%"
echo        提示: 安装进度如下，请耐心等待...
echo.

"%PYTHON%" -m pip install -r "%ROOT%requirements.txt" --upgrade --progress-bar on -i "%PIP_INDEX%"
set "INSTALL_RESULT=%errorlevel%"

if %INSTALL_RESULT% neq 0 (
    echo.
    echo  [3/4] 依赖安装失败
    echo        可能原因：网络连接异常、pip 版本过旧、或依赖源不可用。
    echo        请尝试手动执行以下命令排查：
    echo.
    echo        %PYTHON% -m pip install -r "%ROOT%requirements.txt" -i "%PIP_INDEX%"
    echo.
    pause
    exit /b 1
)

echo.
echo  [3/4] 依赖安装完成

:: ------------------------------------------------------------
:: 步骤 4/4：安装后复检
:: ------------------------------------------------------------
echo.
echo  [4/4] 安装后复检...

set "DEPS_LOG2=%TEMP%\zb_deps_check2_%RANDOM%.log"
"%PYTHON%" "%CHECKER%" > "%DEPS_LOG2%" 2>&1
set "CHECK2_RESULT=%errorlevel%"

for /f "usebackq tokens=*" %%a in ("%DEPS_LOG2%") do (
    echo      %%a
)
del /f /q "%DEPS_LOG2%" >nul 2>&1

if %CHECK2_RESULT% neq 0 (
    echo.
    echo  [4/4] 复检未通过
    echo        依赖仍存在问题，请检查 requirements.txt 或手动安装。
    pause
    exit /b 1
)

echo.
echo  [4/4] 复检通过

:: ------------------------------------------------------------
:: 环境就绪，启动主程序
:: ------------------------------------------------------------
:deps_ready
echo.
echo  ================================================================
echo   环境准备就绪，正在启动主程序...
echo  ================================================================
echo.

if not "%~1"=="" (
    set "TARGET_URL=%~1"
    goto :launch
)

cls
echo.
echo  +==============================================================+
echo  ^|                 反检测浏览器 v2 - 纯净模式                 ^|
echo  +==============================================================+
echo.
echo  请输入目标网址，直接回车打开 about:blank
echo  例: https://edqab.com/tealeaman/studentpage.jsp
echo.
set /p TARGET_URL="网址: "

if "%TARGET_URL%"=="" set "TARGET_URL=about:blank"

:launch
echo.
echo  [启动中] 反检测浏览器正在启动，关闭浏览器窗口即退出...
echo.

"%PYTHON%" cli.py launch "%TARGET_URL%"

echo.
echo  [已退出] 主程序运行结束
pause
