@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title 单机武侠 ZMUD - 本地检查

set "PYTHON_CMD=python"
where py >nul 2>nul
if not errorlevel 1 (
    py -3.13 --version >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_CMD=py -3.13"
    )
)

 echo.
echo ========================================
echo   单机武侠 ZMUD - 本地检查
echo ========================================
echo 使用解释器：%PYTHON_CMD%
echo.

 echo [1/3] 自动化测试...
%PYTHON_CMD% -m pytest -q
if errorlevel 1 goto :failed

echo.
echo [2/3] Python 编译检查...
%PYTHON_CMD% -m compileall -q .
if errorlevel 1 goto :failed

echo.
echo [3/3] 游戏数据校验...
%PYTHON_CMD% data_validator.py
if errorlevel 1 goto :failed

echo.
echo ========================================
echo 全部检查通过。完整实玩仍建议验证一次。
echo ========================================
pause
exit /b 0

:failed
echo.
echo 检查失败。请保留上方错误信息并发回开发对话。
pause
exit /b 1
