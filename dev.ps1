# dev.ps1 — PersonLLMWiki 开发/测试环境工具
#
# 用法:
#   .\dev.ps1                 # 启动开发实例（5000 已被占用时只打开浏览器）
#   .\dev.ps1 start           # 同默认
#   .\dev.ps1 restart         # 停掉整套进程树后重启开发实例
#   .\dev.ps1 stop            # 清理整套进程树: 开发实例/桌面EXE + MCP launcher + DSH
#   .\dev.ps1 stop -KeepDsh   # 保留 DSH（3080 页面不关闭）
#   .\dev.ps1 status          # 查看端口与相关进程
#
# 为什么 stop 要按命令行杀整套树，而不是 Ctrl+C 或按端口杀:
#   - 开发实例拉起的 MCP launcher、DSH web 都是独立进程/新会话，
#     终端 Ctrl+C 只作用于前台进程组，杀不到它们，导致 5000/3080 残留；
#   - 桌面 EXE 可能顺延占用 5001+（find_free_port），按端口 5000 杀会漏。
#
# 注意: stop 默认会杀掉 DSH web（监听 3080，即 DSH Web GUI 页面），
#       需要保留时请加 -KeepDsh。

param(
    [string]$Action = "start",
    [switch]$KeepDsh
)

$ErrorActionPreference = "Stop"

$CondaPython = "$env:USERPROFILE\miniconda3\envs\flask\python.exe"
$Port = 5000
$SrcDir = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not (Test-Path $CondaPython)) {
    Write-Host "[ERROR] conda flask env not found at $CondaPython" -ForegroundColor Red
    exit 1
}

# ─── 进程树清理 ──────────────────────────────────────────────

function Get-TargetProcesses {
    # 按命令行特征收集需要清理的进程（不依赖固定 PID / 端口）
    $all = Get-CimInstance Win32_Process
    $targets = @()
    foreach ($p in $all) {
        $cl = $p.CommandLine
        if (-not $cl) { continue }
        if ($p.Name -eq 'msedgewebview2.exe') { continue }  # WebView2 子进程随主 EXE 退出，无需单独清理
        if ($cl -match 'src/app\.py') {
            # 开发实例本体
            $targets += [pscustomobject]@{ Id = $p.ProcessId; Name = $p.Name; Kind = 'dev-app'; CommandLine = $cl }
        } elseif ($cl -match '\.personllmwiki\\mcp\\.*launcher\.py') {
            # MCP launcher 子进程
            $targets += [pscustomobject]@{ Id = $p.ProcessId; Name = $p.Name; Kind = 'mcp-launcher'; CommandLine = $cl }
        } elseif ($cl -match 'PersonLLMWiki\.exe') {
            # 桌面 EXE（含其 --mcp-launcher 子进程）
            $targets += [pscustomobject]@{ Id = $p.ProcessId; Name = $p.Name; Kind = 'desktop-exe'; CommandLine = $cl }
        } elseif ($cl -match 'dsh\.cmd" web|dsh\\lib\\bin\.js" web') {
            # DSH web：cmd.exe 包装 + node 本体
            $targets += [pscustomobject]@{ Id = $p.ProcessId; Name = $p.Name; Kind = 'dsh-web'; CommandLine = $cl }
        }
    }
    return $targets
}

function Stop-Tree {
    $targets = Get-TargetProcesses
    if (-not $targets) {
        Write-Host "[PersonLLMWiki] 没有发现需要清理的进程。" -ForegroundColor DarkGray
        return
    }

    # 杀 DSH 前先提示（默认要杀）
    if (-not $KeepDsh -and ($targets | Where-Object { $_.Kind -eq 'dsh-web' })) {
        Write-Host "[PersonLLMWiki] 将终止 DSH web（3080，即 DSH 页面）。如需保留请用: .\dev.ps1 stop -KeepDsh" -ForegroundColor Yellow
    }

    # 先杀应用本体（dev-app / desktop-exe），再杀 MCP、DSH
    foreach ($kind in @('dev-app', 'desktop-exe', 'mcp-launcher', 'dsh-web')) {
        foreach ($t in ($targets | Where-Object { $_.Kind -eq $kind })) {
            if (-not $KeepDsh -and $t.Kind -eq 'dsh-web') {
                taskkill /F /PID $t.Id | Out-Null
                Write-Host "[PersonLLMWiki] 已终止 $($t.Kind) PID $($t.Id) ($($t.Name))" -ForegroundColor DarkGray
            } elseif ($t.Kind -ne 'dsh-web') {
                taskkill /F /PID $t.Id | Out-Null
                Write-Host "[PersonLLMWiki] 已终止 $($t.Kind) PID $($t.Id) ($($t.Name))" -ForegroundColor DarkGray
            }
        }
    }

    Start-Sleep -Seconds 1
    Show-PortStatus
}

function Show-PortStatus {
    foreach ($p in @(5000, 3080)) {
        $c = Get-NetTCPConnection -State Listen -LocalPort $p -ErrorAction SilentlyContinue
        if ($c) {
            $ids = ($c | ForEach-Object { $_.OwningProcess } | Sort-Object -Unique) -join ','
            Write-Host "[PersonLLMWiki] 端口 $p 仍被占用 (PID $ids)" -ForegroundColor Red
        } else {
            Write-Host "[PersonLLMWiki] 端口 $p 已释放" -ForegroundColor Green
        }
    }
}

# ─── 开发实例启停（端口 5000）──────────────────────────────

function Stop-Server {
    # 兼容旧用法：仅确保 5000 被释放（完整清理请用 stop）
    $connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    if ($connections) {
        $procIds = $connections | ForEach-Object { $_.OwningProcess } | Sort-Object -Unique
        foreach ($procId in $procIds) {
            if ($procId -eq 0) { continue }
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
            Write-Host "[PersonLLMWiki] 已停止端口 $Port 上的 PID $procId" -ForegroundColor Yellow
        }
        Start-Sleep -Milliseconds 500
    } else {
        Write-Host "[PersonLLMWiki] 端口 $Port 无进程。" -ForegroundColor DarkGray
    }
}

function Start-Server {
    Set-Location $SrcDir
    Write-Host "[PersonLLMWiki] Starting Flask dev server on port $Port..." -ForegroundColor Green
    Write-Host "[PersonLLMWiki] http://127.0.0.1:$Port" -ForegroundColor Green
    Write-Host "[PersonLLMWiki] Press Ctrl+C to stop (残留子进程请用 .\dev.ps1 stop 清理)" -ForegroundColor DarkGray
    Write-Host ""
    & $CondaPython src/app.py
}

# ─── 命令分发 ──────────────────────────────────────────────

switch ($Action.ToLower()) {
    "restart" {
        Write-Host "[PersonLLMWiki] Restarting..." -ForegroundColor Cyan
        Stop-Tree
        Start-Server
    }
    "stop" {
        Stop-Tree
    }
    "status" {
        Write-Host "[PersonLLMWiki] 当前相关进程:" -ForegroundColor Cyan
        $targets = Get-TargetProcesses
        if ($targets) {
            $targets | ForEach-Object { Write-Host "  PID $($_.Id) [$($_.Kind)] $($_.CommandLine)" -ForegroundColor DarkGray }
        } else {
            Write-Host "  （无）" -ForegroundColor DarkGray
        }
        Show-PortStatus
    }
    default {
        $connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
        if ($connections) {
            $existingId = $connections[0].OwningProcess
            $proc = Get-Process -Id $existingId -ErrorAction SilentlyContinue
            Write-Host "[PersonLLMWiki] Port $Port already in use by PID $existingId ($($proc.ProcessName))" -ForegroundColor Yellow
            Write-Host "[PersonLLMWiki] Opening browser..." -ForegroundColor Cyan
            Start-Process "http://127.0.0.1:$Port"
            exit 0
        }
        Start-Server
    }
}
