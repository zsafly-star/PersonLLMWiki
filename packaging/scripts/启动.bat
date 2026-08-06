@echo off
chcp 65001 >nul
title PersonLLMWiki
cd /d "%~dp0"

set PORT=5000
if defined PERSONLLMWIKI_PORT set PORT=%PERSONLLMWIKI_PORT%

REM ════════════════════════════════════════
REM 端口检测：已运行则直接打开浏览器
REM ════════════════════════════════════════
netstat -ano | findstr ":%PORT% " | findstr "LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo PersonLLMWiki 已在运行，正在打开浏览器...
    start http://127.0.0.1:%PORT%
    timeout /t 3 /nobreak >nul
    exit /b 0
)

echo ════════════════════════════════════════
echo   PersonLLMWiki 启动中...
echo ════════════════════════════════════════
echo.

REM ════════════════════════════════════════
REM 环境自检
REM ════════════════════════════════════════

REM [1/4] 检测 runtime
echo [1/4] 检查 Python 运行时...
if not exist "runtime\python.exe" (
    echo.
    echo [错误] 未找到 runtime\python.exe
    echo 请确保完整下载了安装包，或联系提供者。
    echo.
    pause
    exit /b 1
)
echo       OK

REM [2/4] 检测依赖完整性
echo [2/4] 检查依赖...
runtime\python.exe -c "import flask, openai, fitz, fastembed" 2>nul
if errorlevel 1 (
    echo       依赖缺失，正在安装...
    runtime\python.exe -m pip install -r app\requirements.txt --no-warn-script-location
    if errorlevel 1 (
        echo       [错误] 依赖安装失败，请检查网络连接。
        pause
        exit /b 1
    )
) else (
    echo       OK
)

REM [3/4] 创建 .env（如不存在）
echo [3/4] 检查配置文件...
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo       已从模板创建 .env
    ) else (
        echo RESOURCE_BASE_PATH=> .env
        echo       已创建默认 .env，请到设置页配置资源路径
    )
) else (
    echo       .env 已存在
)

REM [4/4] 创建桌面快捷方式（如不存在）
echo [4/4] 检查桌面快捷方式...
powershell -Command "$desktop = [Environment]::GetFolderPath('Desktop'); $lnk = \"$desktop\PersonLLMWiki.lnk\"; if (-not (Test-Path $lnk)) { $ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut($lnk); $s.TargetPath = '%CD%\启动.bat'; $s.WorkingDirectory = '%CD%'; $s.IconLocation = '%CD%\app\static\img\AIChat.png'; $s.Description = 'PersonLLMWiki 个人知识管理'; $s.Save(); Write-Host '      已创建桌面快捷方式' } else { Write-Host '      已存在' }"

echo.
echo ════════════════════════════════════════
echo   环境检查完成，启动服务...
echo   浏览器将自动打开 http://127.0.0.1:%PORT%
echo   首次使用请到「设置 → 路径设置」配置资源路径
echo   关闭此窗口即可停止服务
echo ════════════════════════════════════════
echo.

REM 设置环境变量
set PYTHONPATH=%CD%\app
set PORT=%PORT%

REM 延迟打开浏览器
start /b cmd /c "timeout /t 3 /nobreak >nul && start http://127.0.0.1:%PORT%"

REM 启动 Flask
cd /d "%~dp0\app"
"%~dp0\runtime\python.exe" app.py 2>&1
