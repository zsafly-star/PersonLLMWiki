param(
    [string]$Action = "start"
)

$ErrorActionPreference = "Stop"

$CondaPython = "$env:USERPROFILE\miniconda3\envs\flask\python.exe"
$Port = 5000
$SrcDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "[ZSSNote] Using conda flask env: $CondaPython" -ForegroundColor Cyan

if (-not (Test-Path $CondaPython)) {
    Write-Host "[ERROR] conda flask env not found at $CondaPython" -ForegroundColor Red
    exit 1
}

function Stop-Server {
    $connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    if ($connections) {
        $procIds = $connections | ForEach-Object { $_.OwningProcess } | Sort-Object -Unique
        foreach ($procId in $procIds) {
            if ($procId -eq 0) {
                Write-Host "[ZSSNote] Skipping system process (PID 0)" -ForegroundColor DarkGray
                continue
            }
            $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
            if ($proc) {
                Write-Host "[ZSSNote] Stopping PID $procId ($($proc.ProcessName))..." -ForegroundColor Yellow
                # Also kill parent process (the terminal window)
                $parentId = (Get-CimInstance Win32_Process -Filter "ProcessId=$procId").ParentProcessId
                Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
                if ($parentId -and $parentId -ne 0) {
                    $parentProc = Get-Process -Id $parentId -ErrorAction SilentlyContinue
                    if ($parentProc -and $parentProc.ProcessName -match 'powershell|pwsh|cmd') {
                        Write-Host "[ZSSNote] Closing parent terminal PID $parentId ($($parentProc.ProcessName))..." -ForegroundColor DarkGray
                        Stop-Process -Id $parentId -Force -ErrorAction SilentlyContinue
                    }
                }
            }
        }
        Start-Sleep -Milliseconds 500
        $check = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
        if ($check) {
            Write-Host "[ZSSNote] Port $Port still in use, force killing..." -ForegroundColor Red
            $check | ForEach-Object { 
                if ($_.OwningProcess -ne 0) {
                    Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue 
                }
            }
            Start-Sleep -Milliseconds 500
        }
        Write-Host "[ZSSNote] Server stopped." -ForegroundColor Green
    } else {
        Write-Host "[ZSSNote] No process on port $Port." -ForegroundColor DarkGray
    }
}

function Start-Server {
    Set-Location $SrcDir
    Write-Host "[ZSSNote] Starting Flask dev server on port $Port..." -ForegroundColor Green
    Write-Host "[ZSSNote] http://127.0.0.1:$Port" -ForegroundColor Green
    Write-Host "[ZSSNote] Press Ctrl+C to stop" -ForegroundColor DarkGray
    Write-Host ""
    & $CondaPython app.py
}

switch ($Action.ToLower()) {
    "restart" {
        Write-Host "[ZSSNote] Restarting..." -ForegroundColor Cyan
        Stop-Server
        Start-Server
    }
    "stop" {
        Stop-Server
    }
    "status" {
        $connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
        if ($connections) {
            $procIds = $connections | ForEach-Object { $_.OwningProcess } | Sort-Object -Unique
            foreach ($procId in $procIds) {
                $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
                Write-Host "[ZSSNote] Port $Port in use by PID $procId ($($proc.ProcessName))" -ForegroundColor Green
            }
        } else {
            Write-Host "[ZSSNote] Port $Port is free." -ForegroundColor DarkGray
        }
    }
    default {
        $connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
        if ($connections) {
            $existingId = $connections[0].OwningProcess
            $proc = Get-Process -Id $existingId -ErrorAction SilentlyContinue
            Write-Host "[ZSSNote] Port $Port already in use by PID $existingId ($($proc.ProcessName))" -ForegroundColor Yellow
            Write-Host "[ZSSNote] Opening browser..." -ForegroundColor Cyan
            Start-Process "http://127.0.0.1:$Port"
            exit 0
        }
        Start-Server
    }
}
