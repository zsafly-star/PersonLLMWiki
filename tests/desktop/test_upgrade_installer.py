"""upgrade_installer 静默升级编排测试。

覆盖：
1. 打包态 build_silent_args() 追加 /DIR=<当前安装目录>
2. 非打包态（开发）不追加 /DIR
3. exe 位于 _internal 子目录时取 _internal 的父级
4. watcher VBS 包含等待轮询 + 提权（runas）逻辑
"""

import pytest

from common import upgrade_installer


def _set_frozen(monkeypatch, exe_path):
    """mock 打包态：sys.frozen=True 且 sys.executable 指向安装目录下的 exe。"""
    monkeypatch.setattr(upgrade_installer.sys, 'frozen', True, raising=False)
    monkeypatch.setattr(upgrade_installer.sys, 'executable', exe_path)


def test_build_silent_args_frozen_appends_dir(monkeypatch):
    """打包态应在参数中追加 /DIR=<exe 所在目录>。"""
    _set_frozen(monkeypatch, r'D:\PersonLLMWiki\PersonLLMWiki.exe')
    args = upgrade_installer.build_silent_args(r'C:\tmp\setup.exe')

    assert args[0] == r'C:\tmp\setup.exe'
    assert '/DIR=' + r'D:\PersonLLMWiki' in args
    # 保留原有静默参数
    for flag in upgrade_installer.SILENT_ARGS:
        assert flag in args


def test_build_silent_args_dev_no_dir(monkeypatch):
    """非打包态（开发）不追加 /DIR。"""
    monkeypatch.setattr(upgrade_installer.sys, 'frozen', False, raising=False)
    args = upgrade_installer.build_silent_args(r'C:\tmp\setup.exe')
    assert not any(a.startswith('/DIR=') for a in args)


def test_build_silent_args_internal_parent_dir(monkeypatch):
    """exe 位于 _internal 子目录时，/DIR 应指向 _internal 的父级。"""
    _set_frozen(monkeypatch, r'D:\PersonLLMWiki\_internal\PersonLLMWiki.exe')
    args = upgrade_installer.build_silent_args(r'C:\tmp\setup.exe')
    assert '/DIR=' + r'D:\PersonLLMWiki' in args


def test_watcher_vbs_contains_wait_and_elevation(monkeypatch):
    """watcher VBS 应包含等待轮询与提权（runas）逻辑。"""
    _set_frozen(monkeypatch, r'D:\PersonLLMWiki\PersonLLMWiki.exe')
    vbs = upgrade_installer.build_watcher_vbs(r'C:\tmp\setup.exe')

    # 等待轮询逻辑：WMI 进程检测 + 睡眠轮询 + 可替换检测
    assert 'Win32_Process' in vbs
    assert 'WScript.Sleep' in vbs
    assert 'FileLocked' in vbs

    # 提权逻辑：ShellExecute "runas"
    assert 'ShellExecute' in vbs
    assert 'runas' in vbs
