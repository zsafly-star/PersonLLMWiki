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

# 安装器启动前的等待毫秒数（让主程序完全退出，避免安装器替换正在运行的 exe 失败）
_WAIT_BEFORE_INSTALL_MS = 3000


def build_silent_args(setup_path):
    """构造安装器静默启动命令行。"""
    return [setup_path] + list(SILENT_ARGS)


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

    流程：等待主程序退出 → 静默安装（等待安装器退出）→ 自动重启应用。
    """
    if app_cmd is None:
        app_cmd = restart_command()
    install_cmd = subprocess.list2cmdline(build_silent_args(setup_path))
    restart_cmd = subprocess.list2cmdline(app_cmd)
    return (
        'Set sh = CreateObject("WScript.Shell")\r\n'
        f'WScript.Sleep {_WAIT_BEFORE_INSTALL_MS}\r\n'
        f'sh.Run "{_vbs_quote(install_cmd)}", 0, True\r\n'
        f'sh.Run "{_vbs_quote(restart_cmd)}", 1, False\r\n'
    )


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
