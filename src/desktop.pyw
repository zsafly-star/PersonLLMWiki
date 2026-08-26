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
from common.desktop_prefs import get_port, set_port, get_window_state, set_window_state

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
    _maximized = [False]             # 是否处于「最大化到工作区」状态
    _pre_restore_bounds = [None]     # 最大化前的窗口 bounds：(left, top, right, bottom)

    # T6：读取上次保存的窗口状态（位置/尺寸 + 最大化），启动时恢复
    _saved_bounds, _saved_maximized = get_window_state()

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
    SWP_NOSIZE = 0x0001
    SWP_NOZORDER = 0x0004
    SWP_NOACTIVATE = 0x0010
    SPI_GETWORKAREA = 0x0030
    MONITOR_DEFAULTTONEAREST = 2
    SNAP_EDGE_PX = 6   # 顶边吸附判定阈值（像素）：鼠标 Y 距屏幕顶部 ≤ 该值时触发最大化
    SM_XVIRTUALSCREEN = 76   # 虚拟屏幕（所有显示器包围盒）左上角 X
    SM_YVIRTUALSCREEN = 77   # 虚拟屏幕左上角 Y
    SM_CXVIRTUALSCREEN = 78  # 虚拟屏幕宽度
    SM_CYVIRTUALSCREEN = 79  # 虚拟屏幕高度

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
    user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.wintypes.RECT)]
    user32.GetWindowRect.restype = ctypes.c_bool
    user32.GetCursorPos.argtypes = [ctypes.POINTER(ctypes.wintypes.POINT)]
    user32.GetCursorPos.restype = ctypes.c_bool
    user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    user32.GetSystemMetrics.restype = ctypes.c_int

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

    # 工作区（屏幕去任务栏）查询：多显示器时取窗口所在显示器的 workarea
    class MONITORINFO(ctypes.Structure):
        _fields_ = [
            ('cbSize', ctypes.wintypes.DWORD),
            ('rcMonitor', ctypes.wintypes.RECT),
            ('rcWork', ctypes.wintypes.RECT),
            ('dwFlags', ctypes.wintypes.DWORD),
        ]

    user32.SystemParametersInfoW.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
    user32.SystemParametersInfoW.restype = ctypes.c_bool
    user32.MonitorFromWindow.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    user32.MonitorFromWindow.restype = ctypes.c_void_p
    user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(MONITORINFO)]
    user32.GetMonitorInfoW.restype = ctypes.c_bool
    user32.MonitorFromRect.argtypes = [ctypes.POINTER(ctypes.wintypes.RECT), ctypes.c_uint]
    user32.MonitorFromRect.restype = ctypes.c_void_p

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

        # T6：恢复窗口几何（精确位置/尺寸 + 最大化状态），避免二次跳变。
        # 最大化：复用最大化到工作区，还原前 bounds 用保存值（窗口已按 workarea
        # 创建，此处 SetWindowPos 基本为 no-op，不会「先小后大」跳变）。
        # 非最大化：用 SetWindowPos 把外框精确设回保存的 GetWindowRect 值，
        # 消除 create_window(width/height) 语义与窗口外框（含不可见 resize 边框）
        # 不一致带来的尺寸偏移。
        if _saved_maximized:
            _maximize_to_work_area(_saved_bounds)
        elif _validated_bounds:
            left, top, right, bottom = _validated_bounds
            user32.SetWindowPos(
                _hwnd[0], None, left, top, right - left, bottom - top,
                SWP_NOZORDER | SWP_NOACTIVATE,
            )

    def _restore_window():
        """托盘回调：恢复并聚焦窗口。"""
        if _hwnd[0]:
            user32.ShowWindow(_hwnd[0], SW_RESTORE)
            user32.SetForegroundWindow(_hwnd[0])

    def _save_window_state():
        """保存当前窗口 bounds 与最大化状态到 prefs（仅真正退出时调用）。

        最大化时保存「还原前 bounds」（_pre_restore_bounds），确保重启后能
        还原回原位置；非最大化时保存当前窗口 rect。关闭到托盘不在此路径。
        """
        if _maximized[0]:
            bounds = _pre_restore_bounds[0]
            maximized = True
        else:
            bounds = None
            if _hwnd[0]:
                r = ctypes.wintypes.RECT()
                if user32.GetWindowRect(_hwnd[0], ctypes.byref(r)):
                    bounds = (r.left, r.top, r.right, r.bottom)
            maximized = False
        try:
            set_window_state(bounds, maximized)
        except Exception as e:
            print(f"[Desktop] 保存窗口状态失败: {e}")

    def _quit_app():
        """托盘回调：真正退出。"""
        # T6：真正退出前保存窗口状态
        _save_window_state()
        _allow_close[0] = True
        if _hwnd[0]:
            user32.PostMessageW(_hwnd[0], WM_CLOSE, 0, 0)

    def _get_work_area():
        """返回窗口当前所在显示器的 workarea（屏幕去任务栏）矩形。

        多显示器：用 MonitorFromWindow 取窗口所在显示器，再 GetMonitorInfoW 取 rcWork；
        失败时回退到主显示器 SystemParametersInfo(SPI_GETWORKAREA)。
        返回 (left, top, right, bottom)，失败返回 None。
        """
        hwnd = _hwnd[0]
        if hwnd:
            monitor = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
            if monitor:
                mi = MONITORINFO()
                mi.cbSize = ctypes.sizeof(MONITORINFO)
                if user32.GetMonitorInfoW(monitor, ctypes.byref(mi)):
                    return (mi.rcWork.left, mi.rcWork.top, mi.rcWork.right, mi.rcWork.bottom)
        # 兜底：主显示器工作区
        rect = ctypes.wintypes.RECT()
        if user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0):
            return (rect.left, rect.top, rect.right, rect.bottom)
        return None

    def _get_work_area_for_bounds(bounds):
        """返回指定 bounds 所在显示器的 workarea（窗口未创建前可用）。

        bounds: (left, top, right, bottom) 或 None。
        用 MonitorFromRect 定位保存位置所在显示器；None/失败时回退主显示器。
        """
        monitor = None
        if bounds:
            r = ctypes.wintypes.RECT(bounds[0], bounds[1], bounds[2], bounds[3])
            monitor = user32.MonitorFromRect(ctypes.byref(r), MONITOR_DEFAULTTONEAREST)
        if monitor:
            mi = MONITORINFO()
            mi.cbSize = ctypes.sizeof(MONITORINFO)
            if user32.GetMonitorInfoW(monitor, ctypes.byref(mi)):
                return (mi.rcWork.left, mi.rcWork.top, mi.rcWork.right, mi.rcWork.bottom)
        # 兜底：主显示器工作区
        rect = ctypes.wintypes.RECT()
        if user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0):
            return (rect.left, rect.top, rect.right, rect.bottom)
        return None

    def _get_monitor_rect():
        """返回窗口当前所在显示器的完整矩形 (left, top, right, bottom)。

        用于顶边吸附：Aero Snap 的「顶边」是物理屏幕顶边（rcMonitor.top），
        与 workarea（rcWork）不同——任务栏在顶部时 rcWork.top 会被下移。
        多显示器：用 MonitorFromWindow 取窗口所在显示器。
        """
        hwnd = _hwnd[0]
        if hwnd:
            monitor = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
            if monitor:
                mi = MONITORINFO()
                mi.cbSize = ctypes.sizeof(MONITORINFO)
                if user32.GetMonitorInfoW(monitor, ctypes.byref(mi)):
                    return (mi.rcMonitor.left, mi.rcMonitor.top,
                            mi.rcMonitor.right, mi.rcMonitor.bottom)
        return None

    def _validate_window_bounds(bounds):
        """校验保存的窗口 bounds 是否仍落在虚拟屏幕内（多显示器/DPI 容错）。

        用虚拟屏幕（所有显示器包围盒）判断，避免显示器拔掉后窗口跑丢；
        要求至少有足够可见区域（宽≥100、高≥40）才能抓取标题栏。
        返回 (left, top, right, bottom) 或 None（无效 → 回退默认居中）。
        """
        if not bounds:
            return None
        left, top, right, bottom = bounds
        if right <= left or bottom <= top:
            return None
        vx = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        vy = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        vw = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
        vh = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
        vx2 = vx + vw
        vy2 = vy + vh
        ix = max(left, vx)
        iy = max(top, vy)
        ix2 = min(right, vx2)
        iy2 = min(bottom, vy2)
        if (ix2 - ix) >= 100 and (iy2 - iy) >= 40:
            return (left, top, right, bottom)
        return None

    def _maximize_to_work_area(pre_bounds=None):
        """把窗口最大化到「工作区」（不覆盖任务栏），并记录还原前的 bounds。

        pre_bounds：可选，还原时的目标 bounds (left, top, right, bottom)。
        顶边吸附拖动时传入拖动起始 rect，避免把「被拖到屏幕外」的负 top
        记为还原位置；不传则用当前窗口 rect（双击标题栏等静态入口）。
        """
        hwnd = _hwnd[0]
        if not hwnd:
            return
        work = _get_work_area()
        if not work:
            return
        if pre_bounds is not None:
            _pre_restore_bounds[0] = tuple(pre_bounds)
        else:
            r0 = ctypes.wintypes.RECT()
            if user32.GetWindowRect(hwnd, ctypes.byref(r0)):
                _pre_restore_bounds[0] = (r0.left, r0.top, r0.right, r0.bottom)
        left, top, right, bottom = work
        user32.SetWindowPos(
            hwnd, None, left, top, right - left, bottom - top,
            SWP_NOZORDER | SWP_NOACTIVATE,
        )
        _maximized[0] = True
        _notify_win_state(True)

    def _restore_from_work_area():
        """从「最大化到工作区」状态还原到最大化前的 bounds。"""
        hwnd = _hwnd[0]
        if not hwnd:
            return
        bounds = _pre_restore_bounds[0]
        if bounds:
            left, top, right, bottom = bounds
            user32.SetWindowPos(
                hwnd, None, left, top, right - left, bottom - top,
                SWP_NOZORDER | SWP_NOACTIVATE,
            )
        else:
            user32.ShowWindow(hwnd, SW_RESTORE)
        _maximized[0] = False
        _pre_restore_bounds[0] = None
        _notify_win_state(False)

    # F8: 暴露退出入口，供安装版自动升级 launch-installer 调用
    from common.desktop_signals import register_quit
    register_quit(_quit_app)

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
            if not _hwnd[0]:
                return
            if _maximized[0]:
                _restore_from_work_area()
            else:
                _maximize_to_work_area()

        def is_maximized(self):
            return bool(_hwnd[0] and _maximized[0])

        def close(self):
            # 走既有 _wndproc：非退出态隐藏到托盘，与系统 ✕ 语义一致
            if _hwnd[0]:
                user32.PostMessageW(_hwnd[0], WM_CLOSE, 0, 0)

        def start_drag(self):
            """拖动窗口：后台线程跟随鼠标相对位移移动窗口，直到左键松开。

            采用「相对位移」而非一次性绝对偏移：
              - 每帧读取当前窗口 rect 与鼠标增量，窗口只按鼠标 delta 平移，
                不依赖一次性 offset，避免窗口被拖出屏幕后 GetWindowRect/坐标
                空间不一致导致无法继续拖动；
              - 最大化时先还原，并等待还原状态生效后再进入拖动循环，避免读到
                未及时更新的最大化 rect；
              - 顶边吸附（Aero Snap）：拖动过程中若鼠标到达窗口所在显示器的
                物理顶边（rcMonitor.top）附近，松手时最大化到工作区。
            """
            if not _hwnd[0]:
                return

            def _worker():
                # 最大化时先还原（模拟 Windows 拖顶栏还原行为）
                was_maximized = _maximized[0]
                if was_maximized:
                    _restore_from_work_area()
                    # 等待还原状态生效，避免 GetWindowRect 读到旧 rect
                    time.sleep(0.08)

                # 记录拖动起始 rect：顶边吸附时的还原目标，避免把「被拖到
                # 屏幕外」的负 top 记为还原位置（导致还原后标题栏不可见）。
                drag_start_bounds = None
                r0 = ctypes.wintypes.RECT()
                if user32.GetWindowRect(_hwnd[0], ctypes.byref(r0)):
                    drag_start_bounds = (r0.left, r0.top, r0.right, r0.bottom)

                pt_prev = ctypes.wintypes.POINT()
                if not user32.GetCursorPos(ctypes.byref(pt_prev)):
                    return

                # 顶边吸附状态：起始即为最大化（刚还原）时，鼠标仍在顶边，
                # 需先拖离顶边才允许吸附，否则会立刻被判定为「回到顶部」而
                # 重新最大化，破坏「最大化后拖离顶部还原」的语义。
                snap_to_max = False
                snap_armed = not was_maximized

                while True:
                    pt = ctypes.wintypes.POINT()
                    if not user32.GetCursorPos(ctypes.byref(pt)):
                        break
                    dx = pt.x - pt_prev.x
                    dy = pt.y - pt_prev.y
                    if dx or dy:
                        r = ctypes.wintypes.RECT()
                        if not user32.GetWindowRect(_hwnd[0], ctypes.byref(r)):
                            break
                        user32.SetWindowPos(
                            _hwnd[0], None, r.left + dx, r.top + dy, 0, 0,
                            SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE,
                        )

                    # 顶边吸附检测：以窗口所在显示器的物理顶边为准
                    mon = _get_monitor_rect()
                    if mon:
                        at_top = pt.y <= mon[1] + SNAP_EDGE_PX
                        if at_top:
                            if snap_armed:
                                snap_to_max = True
                        else:
                            snap_armed = True  # 离开顶边后，允许后续吸附

                    pt_prev.x = pt.x
                    pt_prev.y = pt.y
                    if not (user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000):
                        break
                    time.sleep(0.01)

                # 松手时命中顶边吸附 → 最大化到工作区（不挡任务栏）
                if snap_to_max and not _maximized[0]:
                    _maximize_to_work_area(drag_start_bounds)

            threading.Thread(target=_worker, name="win-drag", daemon=True).start()

        def start_resize(self, direction):
            """边缘缩放：后台线程按方向拖动窗口边/角，直到鼠标左键松开。"""
            if not _hwnd[0]:
                return
            if _maximized[0]:
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

    # T6：计算恢复目标几何（多显示器/DPI 容错，无效则回退默认 1280×800 居中）
    _validated_bounds = _validate_window_bounds(_saved_bounds)
    if _saved_maximized:
        # 最大化：直接用目标显示器 workarea 创建，避免「先小后大」的可见跳变
        _work = _get_work_area_for_bounds(_validated_bounds or _saved_bounds)
        if _work:
            _win_x, _win_y = _work[0], _work[1]
            _win_w = _work[2] - _work[0]
            _win_h = _work[3] - _work[1]
        else:
            _win_x = _win_y = None
            _win_w, _win_h = 1280, 800
    elif _validated_bounds:
        _win_x, _win_y = _validated_bounds[0], _validated_bounds[1]
        _win_w = max(_validated_bounds[2] - _validated_bounds[0], 1024)
        _win_h = max(_validated_bounds[3] - _validated_bounds[1], 600)
    else:
        _win_x = _win_y = None
        _win_w, _win_h = 1280, 800

    _win_kwargs = dict(
        url=url,
        title='PersonLLMWiki',
        width=_win_w,
        height=_win_h,
        min_size=(1024, 600),
        frameless=True,
        easy_drag=False,
        js_api=window_api,
    )
    if _win_x is not None and _win_y is not None:
        _win_kwargs['x'] = _win_x
        _win_kwargs['y'] = _win_y
    window = webview.create_window(**_win_kwargs)
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
