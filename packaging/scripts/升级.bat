@echo off
chcp 65001 >nul
title PersonLLMWiki 升级
cd /d "%~dp0"

set VERSIONS_URL=https://raw.githubusercontent.com/your-org/PersonLLMWiki/main/versions.json

echo ════════════════════════════════════════
echo   PersonLLMWiki 在线升级
echo ════════════════════════════════════════
echo.

REM Step 1: 停止服务
echo [1/4] 停止服务...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5000 " ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)
timeout /t 2 /nobreak >nul

REM Step 2: 检查并执行升级
echo [2/4] 检查并下载更新...
runtime\python.exe "%~dp0\app\common\upgrade_check.py" --versions-url "%VERSIONS_URL%" --app-dir "%~dp0\app" --version-file "%~dp0\VERSION"
if errorlevel 2 (
    echo.
    echo 已是最新版本，无需升级。
    pause
    exit /b 0
)
if errorlevel 1 (
    echo.
    echo 升级失败，请检查网络连接或稍后重试。
    pause
    exit /b 1
)

REM Step 3: 依赖更新（如有变化）
echo [3/4] 检查依赖...
runtime\python.exe -m pip install -r app\requirements.txt --quiet --no-warn-script-location 2>nul
echo       依赖检查完成

REM Step 4: 完成
echo [4/4] 完成！
echo.
echo ════════════════════════════════════════
echo   升级完成！双击"启动.bat"开始使用
echo ════════════════════════════════════════
pause
