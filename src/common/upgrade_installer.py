"""安装版静默升级编排：静默安装参数、重启命令、升级 watcher。

供 settings/routes.py 的 launch-installer 复用：
- 静默安装参数（Inno Setup）：不弹向导、不弹消息框、不自动重启系统；
- 升级 watcher：作为独立进程（wscript.exe + VBS）运行，等主程序退出后启动安装器，
  安装完成后自动重启应用。用 WScript.Shell.Run 的 waitOnReturn 等待 GUI 安装器退出，
  避免 cmd 的 start 命令把 /VERYSILENT 等 / 开关当成 start 自身选项吞掉。
  watcher 用系统 wscript.exe 运行、不持有本应用 exe，安装器才能替换正在运行的 exe。
"""

import os
import sys
import subprocess
import tempfile

# Inno Setup 静默参数
SILENT_ARGS = ['/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART']

# 等待主程序退出 + exe 可被替换的轮询参数（超时后交给安装器 CloseApplications 兜底）
_WAIT_APP_EXIT_TIMEOUT_S = 30
_WAIT_APP_EXIT_STEP_MS = 200
# 等待提权安装器完成的上限与轮询步长
_WAIT_INSTALLER_TIMEOUT_S = 120
_WAIT_INSTALLER_STEP_MS = 500


def _current_install_dir():
    """返回当前安装目录（仅打包态有意义）。

    PyInstaller one-folder 打包：exe 位于安装目录，_internal 与其平级。
    若 exe 恰好落在 _internal 子目录内，回退到 _internal 的父级。
    """
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    if os.path.basename(exe_dir).lower() == '_internal':
        return os.path.dirname(exe_dir)
    return exe_dir


def build_silent_args(setup_path):
    """构造安装器静默启动命令行。

    打包态（sys.frozen）显式追加 /DIR=<当前安装目录>，确保静默升级替换
    运行中的同目录应用，而不是默认安装到 Program Files 产生副本。
    """
    args = [setup_path] + list(SILENT_ARGS)
    if getattr(sys, 'frozen', False):
        args.append('/DIR=' + _current_install_dir())
    return args


def restart_command():
    """返回重启应用所需的命令行。

    打包版（sys.frozen）：直接重启自身 EXE；
    开发/源码模式：用当前解释器重新拉起 desktop.pyw（仅测试用，开发模式禁止真实静默升级）。
    """
    if getattr(sys, 'frozen', False):
        return [sys.executable]
    entry = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'desktop.pyw'
    )
    return [sys.executable, entry]


def _vbs_quote(s):
    """把双引号转义为 VBS 字符串字面量里的 ""。"""
    return s.replace('"', '""')


def build_watcher_vbs(setup_path, app_cmd=None):
    """生成升级 watcher 的 VBS 脚本内容。

    流程：
    1. 轮询等待主程序进程退出、且 exe 可被替换（带上限，超时交给安装器 CloseApplications 兜底）；
    2. 以管理员身份拉起安装器（ShellExecute "runas"），并等待安装完成；
    3. 自动重启应用。
    """
    if app_cmd is None:
        app_cmd = restart_command()

    args = build_silent_args(setup_path)
    setup_exe = args[0]
    setup_args = subprocess.list2cmdline(args[1:])
    setup_name = os.path.basename(setup_exe)

    restart_cmd = subprocess.list2cmdline(app_cmd)
    app_exe = os.path.abspath(app_cmd[0])
    app_name = os.path.basename(app_exe)

    # 轮询迭代上限（按步长换算），避免 VBS 依赖 Timer 跨午夜出错
    wait_app_iters = (_WAIT_APP_EXIT_TIMEOUT_S * 1000) // _WAIT_APP_EXIT_STEP_MS
    wait_installer_iters = (_WAIT_INSTALLER_TIMEOUT_S * 1000) // _WAIT_INSTALLER_STEP_MS

    lines = [
        "' PLW upgrade watcher: wait app exit -> elevated silent install -> restart",
        'Set sh = CreateObject("WScript.Shell")',
        'Set fso = CreateObject("Scripting.FileSystemObject")',
        '',
        f'appExe = "{_vbs_quote(app_exe)}"',
        f'appName = "{_vbs_quote(app_name)}"',
        f'setupExe = "{_vbs_quote(setup_exe)}"',
        f'setupArgs = "{_vbs_quote(setup_args)}"',
        f'setupName = "{_vbs_quote(setup_name)}"',
        f'restartCmd = "{_vbs_quote(restart_cmd)}"',
        '',
        "' 1. wait for the app process to fully exit and the exe to be replaceable",
        'WaitAppExit appExe, appName',
        '',
        "' 2. launch installer elevated (runas) and wait for completion",
        'RunElevatedAndWait setupExe, setupArgs, setupName',
        '',
        "' 3. restart the app",
        'sh.Run restartCmd, 1, False',
        '',
        'Sub WaitAppExit(exePath, procName)',
        '    Dim i',
        f'    For i = 1 To {wait_app_iters}',
        '        If Not ProcessRunning(procName) And Not FileLocked(exePath) Then Exit For',
        f'        WScript.Sleep {_WAIT_APP_EXIT_STEP_MS}',
        '    Next',
        'End Sub',
        '',
        'Function ProcessRunning(procName)',
        '    Dim wmi, items',
        r'    Set wmi = GetObject("winmgmts:\\.\root\cimv2")',
        '    Set items = wmi.ExecQuery("SELECT ProcessId FROM Win32_Process WHERE Name = \'" & procName & "\'")',
        '    ProcessRunning = (items.Count > 0)',
        'End Function',
        '',
        'Function FileLocked(path)',
        '    Dim tmp',
        '    If Not fso.FileExists(path) Then',
        '        FileLocked = False',
        '        Exit Function',
        '    End If',
        '    tmp = path & ".plwlock"',
        '    On Error Resume Next',
        '    fso.MoveFile path, tmp',
        '    If Err.Number = 0 Then fso.MoveFile tmp, path',
        '    FileLocked = (Err.Number <> 0)',
        '    Err.Clear',
        '    On Error GoTo 0',
        'End Function',
        '',
        'Sub RunElevatedAndWait(exePath, args, procName)',
        '    Dim sa, i, seen',
        '    Set sa = CreateObject("Shell.Application")',
        '    sa.ShellExecute exePath, args, "", "runas", 0',
        '    seen = False',
        f'    For i = 1 To {wait_installer_iters}',
        '        If ProcessRunning(procName) Then',
        '            seen = True',
        '        ElseIf seen Then',
        '            Exit For',
        '        End If',
        f'        WScript.Sleep {_WAIT_INSTALLER_STEP_MS}',
        '    Next',
        'End Sub',
    ]
    return '\r\n'.join(lines) + '\r\n'


def spawn_watcher(setup_path, app_cmd=None):
    """启动升级 watcher 进程（wscript.exe + VBS），返回其 Popen 对象。

    watcher 用系统 wscript.exe 运行，不持有本应用 exe，因此安装器可以替换正在运行的 exe。
    """
    vbs = build_watcher_vbs(setup_path, app_cmd)
    fd, vbs_path = tempfile.mkstemp(prefix='plw_upgrade_', suffix='.vbs')
    with os.fdopen(fd, 'wb') as f:
        f.write(vbs.encode('ascii'))
    return subprocess.Popen(
        ['wscript.exe', '//B', vbs_path],
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
    )
