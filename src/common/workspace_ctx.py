"""任务工作空间线程本地上下文。

orchestrator 在运行某个节点前调用 set_workspace(path)，
节点结束后调用 clear_workspace()。
MCP 工作空间工具（list_workspace / read_workspace_file / write_workspace_file）
据此把相对路径锚定到当前任务的工作空间，防止越界写盘。

因为 run_agent_loop 调用工具是同步同线程执行，thread-local 足够安全。
"""
import os
import threading

_local = threading.local()


def set_workspace(path):
    """设置当前线程的任务工作空间（绝对路径）。"""
    _local.workspace = os.path.abspath(path) if path else None


def get_workspace():
    """返回当前线程的任务工作空间绝对路径，未设置返回 None。"""
    return getattr(_local, 'workspace', None)


def clear_workspace():
    """清除当前线程的工作空间。"""
    _local.workspace = None
