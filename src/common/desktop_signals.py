"""桌面壳退出信号：供 Flask 路由（如安装版自动升级）请求主窗口优雅退出。

desktop.pyw 在 main() 里通过 register_quit() 注册 _quit_app 回调；
settings/routes.py 的 launch-installer 通过 request_quit() 触发，
避免跨线程直接操作窗口句柄 / _allow_close 闭包状态。
"""

_quit_callback = None


def register_quit(callback):
    """注册退出回调（desktop.pyw 启动时调用一次）。"""
    global _quit_callback
    _quit_callback = callback


def request_quit():
    """请求桌面壳退出。返回 True 表示已触发退出；False 表示无回调（非桌面壳）。"""
    if _quit_callback is not None:
        _quit_callback()
        return True
    return False
