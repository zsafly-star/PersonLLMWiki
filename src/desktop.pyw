"""PersonLLMWiki 桌面入口。

单进程双线程：
  - 后台线程：Flask 后端（import 现有 app）
  - 主线程：PyWebView 原生窗口

用法：
  开发模式：python desktop.pyw
  打包后：双击 PersonLLMWiki.exe
"""

import os
import sys

# ── MCP 子进程入口 ──────────────────────────────────────────────
# 打包模式下，builtin_mcp_manager 以 --mcp-launcher=<path> 参数启动 EXE，
# 此时只运行指定 MCP 服务器脚本，不启动完整桌面应用。
if len(sys.argv) >= 2 and sys.argv[1].startswith('--mcp-launcher='):
    _mcp_launcher_path = sys.argv[1].split('=', 1)[1]
    _mcp_launcher_dir = os.path.dirname(os.path.abspath(_mcp_launcher_path))
    # 确保能导入项目模块（_internal/ 在 sys._MEIPASS）
    if getattr(sys, 'frozen', False) and sys._MEIPASS not in sys.path:
        sys.path.insert(0, sys._MEIPASS)
    sys.path.insert(0, _mcp_launcher_dir)
    # PyInstaller 子进程中 importlib.metadata 找不到 dist-info，
    # 在 sys.path 最前面挂载假元数据目录，确保 version() 调用不崩溃
    import tempfile
    _fmd = tempfile.mkdtemp(prefix='mcp_fake_meta_')
    for _pkg_name, _pkg_ver in [('fastmcp-slim', '3.4.5'), ('fastmcp', '3.4.5')]:
        _dist = os.path.join(_fmd, '%s-%s.dist-info' % (_pkg_name.replace('-', '_'), _pkg_ver))
        os.makedirs(_dist, exist_ok=True)
        with open(os.path.join(_dist, 'METADATA'), 'w', encoding='utf-8') as _mf:
            _mf.write('Name: %s\nVersion: %s\n' % (_pkg_name, _pkg_ver))
    sys.path.insert(0, _fmd)
    import runpy
    runpy.run_path(_mcp_launcher_path, run_name='__main__')  # 必须指定，否则 launcher 的 if __name__ == '__main__' 不触发
    sys.exit(0)

import time
import ctypes
import threading
import urllib.request
import socket

# 确保能 import 项目模块
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from common.port_utils import find_free_port
from common.desktop_prefs import get_port, set_port

# Flask 就绪超时（秒）
FLASK_READY_TIMEOUT = 30


def _wait_for_flask(port, timeout=FLASK_READY_TIMEOUT):
    url = f"http://127.0.0.1:{port}/api"
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                if resp.status == 200:
                    return True
        except Exception as e:
            last_error = e
        time.sleep(0.3)
    print(f"[Desktop] Flask 启动失败，最后错误: {last_error}")
    return False


def _start_flask(port):
    def _run():
        try:
            from app import app
            app.run(host='127.0.0.1', port=port, debug=False, threaded=True)
        except Exception as e:
            print(f"[Desktop] Flask 线程异常: {e}", flush=True)
            import traceback
            traceback.print_exc()

    thread = threading.Thread(target=_run, name="flask-backend", daemon=True)
    thread.start()
    return thread


def _get_icon_path():
    """获取窗口图标路径"""
    icon = os.path.join(_THIS_DIR, 'static', 'img', 'app.ico')
    return icon if os.path.isfile(icon) else None

def _get_resource_path():
    from config import Config
    return Config.RESOURCE_BASE_PATH


def _ensure_first_launch_setup(resource_path):
    from common.desktop_prefs import is_first_launch, mark_launched
    from config import Config

    if not is_first_launch():
        return False

    # .env 写入用户数据目录
    env_path = os.path.join(Config.USER_DATA_DIR, '.env')
    os.makedirs(Config.USER_DATA_DIR, exist_ok=True)
    if not os.path.isfile(env_path):
        with open(env_path, 'w', encoding='utf-8') as f:
            f.write(f"RESOURCE_BASE_PATH={resource_path}\n")

    mark_launched()
    print(f"[Desktop] 首次启动：数据目录 {Config.USER_DATA_DIR}")
    return True


def _check_single_instance():
    """检查是否已有实例运行。有则激活已有窗口并返回 False，否则返回 True。"""
    import ctypes.wintypes

    kernel32 = ctypes.windll.kernel32
    user32 = ctypes.windll.user32

    mutex_name = "PersonLLMWiki_SingleInstance_Mutex"
    mutex = kernel32.CreateMutexW(None, False, mutex_name)
    if not mutex:
        return True  # 连 mutex 都创建不了，继续启动

    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        # 找到已有窗口并激活
        hwnd = user32.FindWindowW(None, "PersonLLMWiki")
        if hwnd:
            # 如果最小化了，先恢复
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            user32.SetForegroundWindow(hwnd)
        return False

    return True


def main():
    import webview

    # ========== 单实例检查 ==========
    if not _check_single_instance():
        print("[Desktop] 已有实例运行，退出")
        sys.exit(0)

    # ========== 一次性初始化 ==========

    # 1. 分配端口（固定默认 5000，与 DSH 插件 MCP 地址对齐；被占用则回退动态端口并持久化）
    try:
        port = get_port()
        _probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            _probe.bind(('127.0.0.1', port))
        finally:
            _probe.close()
    except OSError:
        try:
            port = find_free_port()
            set_port(port)
        except RuntimeError as e:
            print(f"[Desktop] 错误: {e}")
            sys.exit(1)
    print(f"[Desktop] 使用端口 {port}")

    # 2. 启动 Flask 后端
    print("[Desktop] 启动 Flask 后端...")
    flask_thread = _start_flask(port)

    # 3. 等待 Flask 就绪
    print(f"[Desktop] 等待 Flask 就绪（超时 {FLASK_READY_TIMEOUT}s）...")
    if not _wait_for_flask(port):
        print("[Desktop] 错误: Flask 启动超时")
        sys.exit(1)
    print("[Desktop] Flask 已就绪")

    # 4. 首次启动数据目录初始化
    resource_path = _get_resource_path()
    _ensure_first_launch_setup(resource_path)

    # ========== Win32 窗口子类化（拦截 X 按钮 → 最小化） ==========

    # 共享状态
    _hwnd = [None]
    _allow_close = [False]
    _wndproc_callback = [None]
    _original_wndproc = [None]

    # Win32 常量
    WM_CLOSE = 0x0010
    WM_SETICON = 0x0080
    GWL_WNDPROC = -4
    SW_HIDE = 0
    SW_MINIMIZE = 6
    SW_RESTORE = 9
    ICON_SMALL = 0
    ICON_BIG = 1
    VK_LBUTTON = 0x01
    SWP_NOZORDER = 0x0004
    SWP_NOACTIVATE = 0x0010

    import ctypes.wintypes

    user32 = ctypes.windll.user32

    # 确保 64 位兼容：显式声明常用 Win32 API 的参数/返回类型
    user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
    user32.FindWindowW.restype = ctypes.c_void_p
    user32.LoadImageW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    user32.LoadImageW.restype = ctypes.c_void_p
    user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_ulonglong, ctypes.c_void_p]
    user32.SendMessageW.restype = ctypes.c_longlong
    user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user32.ShowWindow.restype = ctypes.c_bool
    user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
    user32.SetForegroundWindow.restype = ctypes.c_bool
    user32.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_ulonglong, ctypes.c_longlong]
    user32.PostMessageW.restype = ctypes.c_bool
    user32.IsZoomed.argtypes = [ctypes.c_void_p]
    user32.IsZoomed.restype = ctypes.c_bool
    user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.wintypes.RECT)]
    user32.GetWindowRect.restype = ctypes.c_bool
    user32.GetCursorPos.argtypes = [ctypes.POINTER(ctypes.wintypes.POINT)]
    user32.GetCursorPos.restype = ctypes.c_bool

    WNDPROC = ctypes.WINFUNCTYPE(
        ctypes.c_longlong,          # LRESULT
        ctypes.c_void_p,            # HWND
        ctypes.c_uint,              # UINT msg
        ctypes.c_ulonglong,         # WPARAM (UINT_PTR on 64-bit)
        ctypes.c_longlong,          # LPARAM (LONG_PTR on 64-bit)
    )

    user32.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, WNDPROC]
    user32.SetWindowLongPtrW.restype = ctypes.c_void_p
    user32.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user32.GetWindowLongPtrW.restype = ctypes.c_void_p
    user32.CallWindowProcW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_ulonglong, ctypes.c_longlong]
    user32.CallWindowProcW.restype = ctypes.c_longlong
    user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    user32.GetAsyncKeyState.restype = ctypes.c_short
    user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    user32.SetWindowPos.restype = ctypes.c_bool

    def _wndproc(hwnd, msg, wparam, lparam):
        """父窗口子类化：仅 WM_CLOSE → 隐藏到托盘（除非 _allow_close）。"""
        if msg == WM_CLOSE and not _allow_close[0]:
            user32.ShowWindow(hwnd, SW_HIDE)
            return 0
        return user32.CallWindowProcW(
            _original_wndproc[0], hwnd, msg, wparam, lparam
        )

    def _install_hook():
        """窗口显示后：找句柄 → 设图标 → 子类化父窗口（WM_CLOSE → 托盘）。"""
        icon_path = _get_icon_path()
        print("[Desktop] _install_hook: 开始查找窗口...", flush=True)
        for i in range(15):
            _hwnd[0] = user32.FindWindowW(None, "PersonLLMWiki")
            if _hwnd[0]:
                print(f"[Desktop] _install_hook: 找到窗口句柄 {_hwnd[0]} (第{i+1}次尝试)", flush=True)
                break
            time.sleep(0.2)
        if not _hwnd[0]:
            print("[Desktop] 警告: 未找到窗口句柄", flush=True)
            return

        # 设置标题栏/任务栏图标
        if icon_path:
            hicon = user32.LoadImageW(
                None, icon_path, 1, 0, 0, 0x0010 | 0x0040
            )
            if hicon:
                user32.SendMessageW(_hwnd[0], WM_SETICON, ICON_SMALL, hicon)
                user32.SendMessageW(_hwnd[0], WM_SETICON, ICON_BIG, hicon)

        # 子类化父窗口（WM_CLOSE → 托盘）
        _wndproc_callback[0] = WNDPROC(_wndproc)
        _original_wndproc[0] = user32.SetWindowLongPtrW(
            _hwnd[0], GWL_WNDPROC, _wndproc_callback[0]
        )
        print("[Desktop] 父窗口子类化完成", flush=True)

    def _restore_window():
        """托盘回调：恢复并聚焦窗口。"""
        if _hwnd[0]:
            user32.ShowWindow(_hwnd[0], SW_RESTORE)
            user32.SetForegroundWindow(_hwnd[0])

    def _quit_app():
        """托盘回调：真正退出。"""
        _allow_close[0] = True
        if _hwnd[0]:
            user32.PostMessageW(_hwnd[0], WM_CLOSE, 0, 0)

    # ========== 托盘 + 窗口 ==========

    from common.tray_manager import TrayManager

    def _toggle_mode():
        """托盘回调：切换 shell 页的 Wiki/DSH 模式（iframe 聚焦时键盘快捷键无效，托盘兜底）。"""
        try:
            window.evaluate_js("window.__shellToggleMode && window.__shellToggleMode()")
        except Exception as e:
            print(f"[Desktop] 切换模式失败: {e}")

    tray = TrayManager(
        icon_path=_get_icon_path(),
        on_show_window=_restore_window,
        on_quit=_quit_app,
        on_toggle_mode=_toggle_mode,
    )

    url = f"http://127.0.0.1:{port}/shell"
    print(f"[Desktop] 创建窗口: {url}")

    class WindowApi:
        """注入到 JS 的窗口控制桥（window.pywebview.api.*，shell 顶层窗口注入）。"""

        def __init__(self):
            self._window = None  # create_window 返回后赋值

        def minimize(self):
            if self._window:
                self._window.minimize()

        def toggle_maximize(self):
            if not self._window:
                return
            if _hwnd[0] and user32.IsZoomed(_hwnd[0]):
                self._window.restore()
            else:
                self._window.maximize()

        def is_maximized(self):
            return bool(_hwnd[0] and user32.IsZoomed(_hwnd[0]))

        def close(self):
            # 走既有 _wndproc：非退出态隐藏到托盘，与系统 ✕ 语义一致
            if _hwnd[0]:
                user32.PostMessageW(_hwnd[0], WM_CLOSE, 0, 0)

        def start_drag(self):
            """拖动窗口：后台线程跟随鼠标移动窗口，直到左键松开（直接 SetWindowPos，不依赖消息处理）。"""
            if not _hwnd[0]:
                return

            def _worker():
                # 最大化时先还原（模拟 Windows 拖顶栏还原行为）
                if user32.IsZoomed(_hwnd[0]):
                    user32.ShowWindow(_hwnd[0], SW_RESTORE)
                    time.sleep(0.08)
                r0 = ctypes.wintypes.RECT()
                if not user32.GetWindowRect(_hwnd[0], ctypes.byref(r0)):
                    return
                pt0 = ctypes.wintypes.POINT()
                user32.GetCursorPos(ctypes.byref(pt0))
                offset_x = r0.left - pt0.x
                offset_y = r0.top - pt0.y
                w = r0.right - r0.left
                h = r0.bottom - r0.top
                while True:
                    pt = ctypes.wintypes.POINT()
                    user32.GetCursorPos(ctypes.byref(pt))
                    user32.SetWindowPos(
                        _hwnd[0], None, pt.x + offset_x, pt.y + offset_y, w, h,
                        SWP_NOZORDER | SWP_NOACTIVATE,
                    )
                    if not (user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000):
                        break
                    time.sleep(0.01)

            threading.Thread(target=_worker, name="win-drag", daemon=True).start()

        def start_resize(self, direction):
            """边缘缩放：后台线程按方向拖动窗口边/角，直到鼠标左键松开。"""
            if not _hwnd[0]:
                return
            if user32.IsZoomed(_hwnd[0]):
                return  # 最大化时禁边缘缩放
            direction = str(direction or '').lower()
            if direction not in ('n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw'):
                return

            def _worker():
                r0 = ctypes.wintypes.RECT()
                if not user32.GetWindowRect(_hwnd[0], ctypes.byref(r0)):
                    return
                left0, top0, right0, bottom0 = r0.left, r0.top, r0.right, r0.bottom
                MIN_W, MIN_H = 1024, 600
                while True:
                    pt = ctypes.wintypes.POINT()
                    user32.GetCursorPos(ctypes.byref(pt))
                    cx, cy = pt.x, pt.y
                    left, top, right, bottom = left0, top0, right0, bottom0
                    if 'n' in direction:
                        top = cy
                    if 's' in direction:
                        bottom = cy
                    if 'e' in direction:
                        right = cx
                    if 'w' in direction:
                        left = cx
                    # 强制最小尺寸 1024×600
                    if right - left < MIN_W:
                        if 'e' in direction:
                            right = left + MIN_W
                        else:
                            left = right - MIN_W
                    if bottom - top < MIN_H:
                        if 's' in direction:
                            bottom = top + MIN_H
                        else:
                            top = bottom - MIN_H
                    user32.SetWindowPos(
                        _hwnd[0], None, left, top, right - left, bottom - top,
                        SWP_NOZORDER | SWP_NOACTIVATE,
                    )
                    if not (user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000):
                        break
                    time.sleep(0.01)

            threading.Thread(target=_worker, name="win-resize", daemon=True).start()

    window_api = WindowApi()
    window = webview.create_window(
        url=url,
        title='PersonLLMWiki',
        width=1280,
        height=800,
        min_size=(1024, 600),
        frameless=True,
        easy_drag=False,
        js_api=window_api,
    )
    window_api._window = window

    def _notify_win_state(maximized):
        """窗口最大化/还原时，通知 shell 刷新 □/❐ 图标（覆盖原生双击最大化等非 JS 入口）。"""
        try:
            window.evaluate_js(
                "window.__setWinState && window.__setWinState(%s)"
                % ('true' if maximized else 'false')
            )
        except Exception as e:
            print(f"[Desktop] 通知窗口状态失败: {e}")

    window.events.maximized += lambda: _notify_win_state(True)
    window.events.restored += lambda: _notify_win_state(False)

    # 窗口图标 + 子类化：线程延迟执行，确保窗口已创建
    def _init_window_hook():
        time.sleep(2)
        _install_hook()
    threading.Thread(target=_init_window_hook, name="win-hook", daemon=True).start()

    tray.start()
    print("[Desktop] 托盘已启动")

    # 阻塞直到用户点击托盘"退出"
    webview.start()
    print("[Desktop] 已退出")

    tray.stop()


if __name__ == '__main__':
    main()
