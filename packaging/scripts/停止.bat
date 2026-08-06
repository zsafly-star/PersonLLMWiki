@echo off
chcp 65001 >nul
title 停止 PersonLLMWiki
cd /d "%~dp0"

set PORT=5000
if defined PERSONLLMWIKI_PORT set PORT=%PERSONLLMWIKI_PORT%

echo 正在停止 PersonLLMWiki (端口 %PORT%)...
set FOUND=0
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do (
    echo 停止进程 PID: %%a
    taskkill /PID %%a /F >nul 2>&1
    set FOUND=1
)
if "%FOUND%"=="0" (
    echo 未发现正在运行的 PersonLLMWiki。
) else (
    echo PersonLLMWiki 已停止。
)
timeout /t 2 /nobreak >nul
