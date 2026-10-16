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
import time


def _setup_frozen_logging():
    """打包版（console=False）无控制台，print/traceback 不可见。
    将 stdout/stderr 重定向到可执行文件旁的 desktop.log，便于排查启动失败。
    必须放在最前面：--mcp-launcher 子进程分支也在 windowed 模式下运行，
    若 stderr 为 None，fastmcp/uvicorn/rich 写日志会失败甚至挂起。"""
    if not getattr(sys, 'frozen', False):
        return None
    candidates = []
    try:
        candidates.append(os.path.dirname(sys.executable))
    except Exception:
        pass
    candidates.append(os.environ.get('TEMP', ''))
    candidates.append(os.environ.get('TMP', ''))
    candidates.append(os.getcwd())
    for base in candidates:
        if not base:
            continue
        try:
            log_path = os.path.join(base, 'desktop.log')
            log_file = open(log_path, 'a', encoding='utf-8')
            sys.stdout = log_file
            sys.stderr = log_file
            print(f"[Desktop] ==== 启动 {time.strftime('%Y-%m-%d %H:%M:%S')} (frozen={getattr(sys, 'frozen', False)}) ====")
            print(f"[Desktop] executable={sys.executable} _MEIPASS={getattr(sys, '_MEIPASS', None)}")
            return log_file
        except Exception:
            continue
    return None


_setup_frozen_logging()

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
from common.window_geometry import clamp_drag_position, validate_restore_bounds

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

    # ========== Win32 窗口子类化（KL-1.2.3-04 原生能力回归） ==========

    # 共享状态
    _hwnd = [None]
    _allow_close = [False]
    _wndproc_callback = [None]
    _original_wndproc = [None]
    _hit_regions = [[]]     # JS 上报的语义命中区（物理像素、客户区坐标），作 WM_NCHITTEST 数据源
    _last_normal_bounds = [None]  # 最近正常态外框（屏幕物理像素）——□ 还原的确定性目标

    # T6：读取上次保存的窗口状态（位置/尺寸 + 最大化），启动时恢复
    _saved_bounds, _saved_maximized = get_window_state()

    # Win32 常量
    WM_CLOSE = 0x0010
    WM_SETICON = 0x0080
    WM_GETMINMAXINFO = 0x0024
    WM_NCCALCSIZE = 0x0083
    WM_NCHITTEST = 0x0084
    GWL_WNDPROC = -4
    SW_HIDE = 0
    SW_SHOWNORMAL = 1
    SW_MAXIMIZE = 3
    SW_SHOWMAXIMIZED = 3  # SetWindowPlacement.showCmd 用名（值同 SW_MAXIMIZE）
    SW_RESTORE = 9
    ICON_SMALL = 0
    ICON_BIG = 1
    SWP_NOSIZE = 0x0001
    SWP_NOZORDER = 0x0004
    SWP_NOACTIVATE = 0x0010
    SPI_GETWORKAREA = 0x0030
    MONITOR_DEFAULTTONEAREST = 2
    MONITOR_DEFAULTTOPRIMARY = 1
    SM_XVIRTUALSCREEN = 76   # 虚拟屏幕（所有显示器包围盒）左上角 X
    SM_YVIRTUALSCREEN = 77   # 虚拟屏幕左上角 Y
    SM_CXVIRTUALSCREEN = 78  # 虚拟屏幕宽度
    SM_CYVIRTUALSCREEN = 79  # 虚拟屏幕高度
    # WM_NCHITTEST 命中码
    HTCLIENT = 1
    HTCAPTION = 2
    HTMINBUTTON = 8
    HTMAXBUTTON = 9
    HTLEFT = 10
    HTRIGHT = 11
    HTTOP = 12
    HTTOPLEFT = 13
    HTTOPRIGHT = 14
    HTBOTTOM = 15
    HTBOTTOMLEFT = 16
    HTBOTTOMRIGHT = 17
    HTCLOSE = 20
    # 命中区几何（CSS 像素，换算物理像素需乘 DPI 缩放）
    TITLEBAR_CSS_PX = 40   # shell.html .shell-bar 高度
    EDGE_PX = 8            # 边缘缩放命中带宽
    CORNER_PX = 14         # 角部缩放命中区
    MIN_TRACK_W, MIN_TRACK_H = 1024, 600
    # JS 驱动拖动（R0 恢复）：轮询松键 + 边界钳制参数
    VK_LBUTTON = 0x01
    MIN_VISIBLE_W = 120  # 水平边界钳制：窗口至少保留的可见宽度（像素）

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
    user32.IsZoomed.argtypes = [ctypes.c_void_p]
    user32.IsZoomed.restype = ctypes.c_bool
    user32.GetDpiForWindow.argtypes = [ctypes.c_void_p]
    user32.GetDpiForWindow.restype = ctypes.c_uint
    user32.GetWindowPlacement.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    user32.GetWindowPlacement.restype = ctypes.c_bool
    user32.SetWindowPlacement.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    user32.SetWindowPlacement.restype = ctypes.c_bool
    user32.MonitorFromPoint.argtypes = [ctypes.wintypes.POINT, ctypes.c_uint]
    user32.MonitorFromPoint.restype = ctypes.c_void_p

    dwmapi = ctypes.windll.dwmapi
    dwmapi.DwmSetWindowAttribute.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
    dwmapi.DwmSetWindowAttribute.restype = ctypes.c_long

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

    class MINMAXINFO(ctypes.Structure):
        _fields_ = [
            ('ptReserved', ctypes.wintypes.POINT),
            ('ptMaxSize', ctypes.wintypes.POINT),
            ('ptMaxPosition', ctypes.wintypes.POINT),
            ('ptMinTrackSize', ctypes.wintypes.POINT),
            ('ptMaxTrackSize', ctypes.wintypes.POINT),
        ]

    class WINDOWPLACEMENT(ctypes.Structure):
        _fields_ = [
            ('length', ctypes.wintypes.UINT),
            ('flags', ctypes.wintypes.UINT),
            ('showCmd', ctypes.wintypes.UINT),
            ('ptMinPosition', ctypes.wintypes.POINT),
            ('ptMaxPosition', ctypes.wintypes.POINT),
            ('rcNormalPosition', ctypes.wintypes.RECT),
        ]

    def _wndproc(hwnd, msg, wparam, lparam):
        """父窗口子类化（KL-1.2.3-04 原生能力回归）：
        - WM_CLOSE → 隐藏到托盘（除非 _allow_close）
        - WM_NCCALCSIZE → 抹掉原生边框/标题栏（客户区=整窗，外观与自绘壳一致，
          wParam 两个分支都 return 0）；最大化时把客户区钳到工作区，保证不
          挡任务栏
        - WM_GETMINMAXINFO → 原生最大化按窗口所在显示器工作区 + 拖拽尺寸约束
        - WM_NCHITTEST → 自绘顶栏/边缘命中表（兜底通路；主通路为 JS mousedown →
          api.start_drag/start_resize 后台线程驱动，因为 WebView2 子窗口覆盖整个
          客户区，鼠标事件优先由 WebView 处理，顶层窗口通常收不到本消息）
        """
        if msg == WM_CLOSE and not _allow_close[0]:
            user32.ShowWindow(hwnd, SW_HIDE)
            return 0
        if msg == WM_NCCALCSIZE:
            if wparam and user32.IsZoomed(hwnd):
                # 最大化时把 rgrc[0] 钉在工作区：Windows 最大化窗口矩形 =
                # 工作区 + 帧边距，不覆盖则四边溢出 ~11px、底部压住任务栏
                # （R1b 曾误删并归因为累加根因，D 侧复测证伪——累加真因是
                # 下面的 wParam==FALSE 漏拦截）
                work = _get_work_area()
                if work:
                    rc = ctypes.cast(
                        ctypes.c_void_p(lparam),
                        ctypes.POINTER(ctypes.wintypes.RECT),
                    ).contents
                    rc.left, rc.top, rc.right, rc.bottom = work
            # 两分支统一 return 0（客户区=整窗）：wParam==FALSE 时漏给
            # DefWindowProc 会让它按 WS_CAPTION/WS_THICKFRAME 改写矩形，
            # 每次 realize 累加一次帧边距（150% DPI 实测每循环 +22/+56）
            return 0
        if msg == WM_GETMINMAXINFO:
            _fill_minmaxinfo(hwnd, lparam)
            return 0
        if msg == WM_NCHITTEST:
            hit = _hit_test(hwnd, lparam)
            if hit is not None:
                return hit
        return user32.CallWindowProcW(
            _original_wndproc[0], hwnd, msg, wparam, lparam
        )

    def _install_hook():
        """窗口显示后：找句柄 → 设图标 → 子类化父窗口（WM_CLOSE → 托盘）。"""
        # R2：钩子整体包 try/finally —— 找不到句柄提前 return 或任何一步抛
        # 异常，都不能跳过 window.show()，否则 hidden 创建的窗口永不显示、
        # 托盘也救不回来（应用「无窗口假死」）。
        try:
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

            # Win11 圆角（DWMWA_WINDOW_CORNER_PREFERENCE=33，DWMWCP_ROUND=2）
            _corner = ctypes.c_int(2)
            try:
                dwmapi.DwmSetWindowAttribute(_hwnd[0], 33, ctypes.byref(_corner), 4)
            except Exception as e:
                print(f"[Desktop] 设置圆角失败: {e}")
        finally:
            # 路线①：hidden 创建 → 样式集/图标就绪后再显示，避免原生标题栏闪现
            try:
                window.show()
            except Exception as e:
                print(f"[Desktop] 显示窗口失败: {e}")

        # R1：几何恢复在 window.show() 之后统一走 _apply_normal_placement
        # （SetWindowPlacement：rcNormalPosition + showCmd 一次设定，最大化
        # 态与还原位置同帧生效）。注：曾怀疑「WinForms Show 覆盖 hidden 期
        # SetWindowPos 导致 150% DPI 几何 ÷1.5」，后经 D 侧探针升级
        # per-monitor DPI 感知实测证伪——无感知探针的读数假象；本路径无害
        # 且为 □ 还原提供确定性目标（_last_normal_bounds），保留。
        if not _hwnd[0]:
            return
        if _validated_bounds:
            if _apply_normal_placement(
                _validated_bounds,
                SW_SHOWMAXIMIZED if _saved_maximized else SW_SHOWNORMAL,
            ):
                _last_normal_bounds[0] = tuple(_validated_bounds)
        elif _saved_maximized:
            user32.ShowWindow(_hwnd[0], SW_MAXIMIZE)

    def _restore_window():
        """托盘回调：恢复并聚焦窗口。"""
        if _hwnd[0]:
            user32.ShowWindow(_hwnd[0], SW_RESTORE)
            user32.SetForegroundWindow(_hwnd[0])

    def _primary_work_area_origin():
        """主显示器 workarea 左上角：GetWindowPlacement 的 rcNormalPosition 以
        主显示器工作区为原点（workspace 坐标系），转屏幕坐标需加该偏移。"""
        pt = ctypes.wintypes.POINT(0, 0)
        monitor = user32.MonitorFromPoint(pt, MONITOR_DEFAULTTOPRIMARY)
        if monitor:
            mi = MONITORINFO()
            mi.cbSize = ctypes.sizeof(MONITORINFO)
            if user32.GetMonitorInfoW(monitor, ctypes.byref(mi)):
                return (mi.rcWork.left, mi.rcWork.top)
        return (0, 0)

    def _record_normal_bounds():
        """把当前窗口外框记为意图矩形 _last_normal_bounds——只在用户拖动/缩放
        结束时调用（进入最大化前不刷新：realize 会把窗口矩形放大一次帧边距，
        用 GetWindowRect 刷新会把放大结果记进去，□ 还原逐次累加 +22/+56）。"""
        hwnd = _hwnd[0]
        if not hwnd or user32.IsZoomed(hwnd):
            return
        r = ctypes.wintypes.RECT()
        if user32.GetWindowRect(hwnd, ctypes.byref(r)):
            _last_normal_bounds[0] = (r.left, r.top, r.right, r.bottom)

    def _log_winrect(tag):
        """R1b-3 诊断日志：打印当前窗口外框，定位还原漂移由哪一步引入。"""
        hwnd = _hwnd[0]
        if not hwnd:
            return
        r = ctypes.wintypes.RECT()
        if user32.GetWindowRect(hwnd, ctypes.byref(r)):
            print(f"[Desktop] {tag}: ({r.left},{r.top})-({r.right},{r.bottom})",
                  flush=True)

    def _apply_normal_placement(bounds, show_cmd):
        """把 bounds 设为窗口正常矩形 + showCmd（启动恢复与 □ 还原共用一条
        路径）：rcNormalPosition 用 workspace 坐标（屏幕坐标 − 主显示器
        workarea 原点，与 _save_window_state 落盘公式互逆）。返回是否成功。"""
        hwnd = _hwnd[0]
        if not hwnd or not bounds:
            return False
        ox, oy = _primary_work_area_origin()
        wp = WINDOWPLACEMENT()
        wp.length = ctypes.sizeof(WINDOWPLACEMENT)
        wp.showCmd = show_cmd
        wp.rcNormalPosition.left = bounds[0] - ox
        wp.rcNormalPosition.top = bounds[1] - oy
        wp.rcNormalPosition.right = bounds[2] - ox
        wp.rcNormalPosition.bottom = bounds[3] - oy
        return bool(user32.SetWindowPlacement(hwnd, ctypes.byref(wp)))

    def _save_window_state():
        """保存当前窗口 bounds 与最大化状态到 prefs（仅真正退出时调用）。

        最大化状态由系统维护（IsZoomed）；bounds：普通态读 GetWindowRect，
        最大化态取 _last_normal_bounds（意图矩形——SetWindowPlacement 的
        realize 会把窗口矩形放大一次帧边距，系统 rcNormalPosition 会被同步
        污染，不可作真源；意图无记录时才回退读 rcNormalPosition）。关闭到
        托盘不在此路径。
        """
        maximized = bool(_hwnd[0] and user32.IsZoomed(_hwnd[0]))
        bounds = None
        if maximized:
            if _last_normal_bounds[0]:
                bounds = tuple(_last_normal_bounds[0])
            else:
                wp = WINDOWPLACEMENT()
                wp.length = ctypes.sizeof(WINDOWPLACEMENT)
                if user32.GetWindowPlacement(_hwnd[0], ctypes.byref(wp)):
                    rc = wp.rcNormalPosition
                    ox, oy = _primary_work_area_origin()
                    bounds = (rc.left + ox, rc.top + oy,
                              rc.right + ox, rc.bottom + oy)
        elif _hwnd[0]:
            r = ctypes.wintypes.RECT()
            if user32.GetWindowRect(_hwnd[0], ctypes.byref(r)):
                bounds = (r.left, r.top, r.right, r.bottom)
        # 落盘前再校验一次 bounds，避免外部改坏／历史坏值被继续沿用
        if bounds:
            bounds = _validate_window_bounds(bounds)
        try:
            set_window_state(bounds, maximized)
        except Exception as e:
            print(f"[Desktop] 保存窗口状态失败: {e}")

    def _quit_app():
        """托盘回调：真正退出。"""
        # T6：真正退出前保存窗口状态
        _save_window_state()
        # 停止 PLW 拉起的 DSH（只杀本进程拉起的，用户自启的不误杀；绝不阻塞退出）
        try:
            from common import dsh_bridge
            dsh_bridge.stop()
        except Exception as e:
            print(f"[Desktop] 停止 DSH 失败: {e}")
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

    def _fill_minmaxinfo(hwnd, lparam):
        """WM_GETMINMAXINFO：原生最大化按窗口所在显示器工作区（不挡任务栏，
        多显示器正确），拖拽尺寸约束 1024×600 ~ 工作区尺寸。"""
        work = _get_work_area()
        if not work:
            return
        left, top, right, bottom = work
        mmi = ctypes.cast(
            ctypes.c_void_p(lparam), ctypes.POINTER(MINMAXINFO)
        ).contents
        mmi.ptMaxSize.x = right - left
        mmi.ptMaxSize.y = bottom - top
        mmi.ptMaxPosition.x = left
        mmi.ptMaxPosition.y = top
        mmi.ptMinTrackSize.x = MIN_TRACK_W
        mmi.ptMinTrackSize.y = MIN_TRACK_H
        mmi.ptMaxTrackSize.x = right - left
        mmi.ptMaxTrackSize.y = bottom - top

    def _hit_test(hwnd, lparam):
        """WM_NCHITTEST 命中表：返回命中码，或 None 交给系统默认处理。

        优先级：JS 上报语义区（按钮/交互排除）→ 边缘 8px/角 14px（原生缩放）
        → 自绘顶栏 40×DPI（HTCAPTION）→ 客户区。
        注：WebView2 覆盖客户区时顶层收不到本消息，此表为兜底；主通路是
        shell.html mousedown → api.start_drag()/start_resize()。
        """
        if user32.IsZoomed(hwnd):
            return None  # 最大化态交给系统默认（无边缘缩放）
        x = ctypes.c_int16(lparam & 0xFFFF).value
        y = ctypes.c_int16((lparam >> 16) & 0xFFFF).value
        r = ctypes.wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
            return None
        # 1) JS 上报的语义命中区（物理像素、客户区坐标；NCCALCSIZE 抹边框后
        #    客户区原点 = 窗口左上，直接平移到屏幕坐标）
        for reg in _hit_regions[0]:
            try:
                rx = r.left + int(reg.get('x', 0))
                ry = r.top + int(reg.get('y', 0))
                rw = int(reg.get('w', 0))
                rh = int(reg.get('h', 0))
            except (TypeError, ValueError):
                continue
            if rx <= x < rx + rw and ry <= y < ry + rh:
                if reg.get('kind') == 'button':
                    return {
                        'min': HTMINBUTTON, 'max': HTMAXBUTTON, 'close': HTCLOSE,
                    }.get(reg.get('name'))
                return HTCLIENT  # 交互排除区：不拖动
        # 2) 边缘/角（原生缩放；角 14px 优先于边 8px）
        if x < r.left + CORNER_PX and y < r.top + CORNER_PX:
            return HTTOPLEFT
        if x >= r.right - CORNER_PX and y < r.top + CORNER_PX:
            return HTTOPRIGHT
        if x < r.left + CORNER_PX and y >= r.bottom - CORNER_PX:
            return HTBOTTOMLEFT
        if x >= r.right - CORNER_PX and y >= r.bottom - CORNER_PX:
            return HTBOTTOMRIGHT
        if y < r.top + EDGE_PX:
            return HTTOP
        if y >= r.bottom - EDGE_PX:
            return HTBOTTOM
        if x < r.left + EDGE_PX:
            return HTLEFT
        if x >= r.right - EDGE_PX:
            return HTRIGHT
        # 3) 自绘顶栏空白 → 原生可拖动
        scale = 1.0
        try:
            scale = user32.GetDpiForWindow(hwnd) / 96.0 or 1.0
        except Exception:
            pass
        if y < r.top + int(TITLEBAR_CSS_PX * scale):
            return HTCAPTION
        return None  # 其余交给系统（客户区）

    def _validate_window_bounds(bounds):
        """校验保存的窗口 bounds 是否仍落在虚拟屏幕内（多显示器/DPI 容错）。

        用虚拟屏幕（所有显示器包围盒）判断，避免显示器拔掉后窗口跑丢；
        要求至少有足够可见区域（宽≥100、高≥40）才能抓取标题栏。
        返回 (left, top, right, bottom) 或 None（无效 → 回退默认居中）。
        """
        if not bounds:
            return None
        vx = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        vy = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        vw = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
        vh = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
        return validate_restore_bounds(
            bounds, vx=vx, vy=vy, vx2=vx + vw, vy2=vy + vh,
        )

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
            # 原生最大化：动画、贴靠语义、IsZoomed 状态由系统维护，铺满工作区
            # 不挡任务栏由 WM_GETMINMAXINFO 保证。进入最大化不刷新意图矩形
            # （_last_normal_bounds 只在初始化/拖动缩放结束时更新——若用
            # GetWindowRect 刷新会把 realize 放大后的结果记进去，逐次累加）。
            if user32.IsZoomed(_hwnd[0]):
                # □ 还原：SetWindowPlacement 的 realize 会把窗口矩形放大一次
                # WS_CAPTION|WS_THICKFRAME 帧边距（150% DPI 实测 +22/+56），
                # 故先设 placement 再用 SetWindowPos（不经帧换算）纠偏钉回
                # 意图矩形；无意图记录（钩子失败等）才回退 SW_RESTORE
                bounds = _last_normal_bounds[0]
                if bounds:
                    _log_winrect("R1b-3 还原前")
                    if _apply_normal_placement(bounds, SW_SHOWNORMAL):
                        _log_winrect("R1b-3 placement后")
                        user32.SetWindowPos(
                            _hwnd[0], None,
                            bounds[0], bounds[1],
                            bounds[2] - bounds[0], bounds[3] - bounds[1],
                            SWP_NOZORDER | SWP_NOACTIVATE,
                        )
                        _log_winrect("R1b-3 纠偏后")
                    else:
                        user32.ShowWindow(_hwnd[0], SW_RESTORE)
                else:
                    user32.ShowWindow(_hwnd[0], SW_RESTORE)
            else:
                user32.ShowWindow(_hwnd[0], SW_MAXIMIZE)

        def is_maximized(self):
            return bool(_hwnd[0] and user32.IsZoomed(_hwnd[0]))

        def close(self):
            # 走既有 _wndproc：非退出态隐藏到托盘，与系统 ✕ 语义一致
            if _hwnd[0]:
                user32.PostMessageW(_hwnd[0], WM_CLOSE, 0, 0)

        def start_drag(self):
            """拖动窗口（R0 恢复 JS 驱动）：后台线程跟随鼠标相对位移移动窗口，
            直到左键松开。

            KL-1.2.3-04 曾改走原生模态循环（转发 WM_NCLBUTTONDOWN），D 侧实机
            探针否定：WebView2 子窗口铺满客户区且 Chromium 持有鼠标捕获，顶层
            窗口的模态循环收不到鼠标移动（Δ=0），窗口纹丝不动。

              - 每帧读当前窗口 rect + 鼠标增量平移，并经 clamp_drag_position
                钳制（顶边不越虚拟屏幕、水平至少保留 MIN_VISIBLE_W 可见宽）；
              - 最大化时先原生 SW_RESTORE，再把抓点按比例对准光标（避免还原后
                窗口「跳回」原还原位而不跟光标）；
              - 顶边吸附不在此处理：shell.html 在松手时检测光标位于主屏物理
                顶边 → api.snap_maximize()（原生最大化，不挡任务栏由
                WM_GETMINMAXINFO/WM_NCCALCSIZE 保证）。
            """
            if not _hwnd[0]:
                return

            def _worker():
                # 最大化时先还原（模拟 Windows 拖顶栏还原行为）
                was_maximized = user32.IsZoomed(_hwnd[0])
                last_bounds = None
                if was_maximized:
                    grab_pt = ctypes.wintypes.POINT()
                    user32.GetCursorPos(ctypes.byref(grab_pt))
                    max_rect = ctypes.wintypes.RECT()
                    user32.GetWindowRect(_hwnd[0], ctypes.byref(max_rect))
                    user32.ShowWindow(_hwnd[0], SW_RESTORE)
                    # 等待还原状态生效，避免 GetWindowRect 读到旧 rect
                    time.sleep(0.08)
                    # 抓点贴光标：按最大化时抓点的水平比例定位还原窗口，
                    # 垂直贴最大化时的顶边（此时光标就在顶边附近）。
                    # 尺寸取意图矩形（realize 会放大一次帧边距，直接用
                    # 还原后的 GetWindowRect 会把放大值带入后续拖动）
                    r_restored = ctypes.wintypes.RECT()
                    if not user32.GetWindowRect(_hwnd[0], ctypes.byref(r_restored)):
                        return
                    intent = _last_normal_bounds[0]
                    if intent:
                        w_restored = intent[2] - intent[0]
                        h_restored = intent[3] - intent[1]
                    else:
                        w_restored = r_restored.right - r_restored.left
                        h_restored = r_restored.bottom - r_restored.top
                    max_w = max_rect.right - max_rect.left
                    frac_x = ((grab_pt.x - max_rect.left) / max_w
                              if max_w > 0 else 0.5)
                    new_left = int(round(grab_pt.x - frac_x * w_restored))
                    user32.SetWindowPos(
                        _hwnd[0], None, new_left, max_rect.top,
                        w_restored, h_restored,
                        SWP_NOZORDER | SWP_NOACTIVATE,
                    )
                    last_bounds = (new_left, max_rect.top,
                                   new_left + w_restored,
                                   max_rect.top + h_restored)

                pt_prev = ctypes.wintypes.POINT()
                if not user32.GetCursorPos(ctypes.byref(pt_prev)):
                    return

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
                        w = r.right - r.left
                        h = r.bottom - r.top
                        svx = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
                        svy = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
                        vx2 = svx + user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
                        vy2 = svy + user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
                        new_left, new_top = clamp_drag_position(
                            r.left, r.top, w, dx, dy,
                            vx=svx, vy=svy, vx2=vx2, vy2=vy2,
                            min_visible_w=MIN_VISIBLE_W,
                        )
                        user32.SetWindowPos(
                            _hwnd[0], None, new_left, new_top, 0, 0,
                            SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE,
                        )
                        last_bounds = (new_left, new_top,
                                       new_left + w, new_top + h)
                    pt_prev.x = pt.x
                    pt_prev.y = pt.y
                    if not (user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000):
                        break
                    time.sleep(0.01)

                # 意图真源：拖动结束时更新。用循环内跟踪的矩形而非
                # GetWindowRect——避免与 snap_maximize（顶边松手即最大化）
                # 竞态时把最大化矩形记成意图
                if last_bounds:
                    _last_normal_bounds[0] = last_bounds
                else:
                    _record_normal_bounds()

            threading.Thread(target=_worker, name="win-drag", daemon=True).start()

        def start_resize(self, direction):
            """边缘缩放（R0 恢复 JS 驱动）：后台线程按方向拖动窗口边/角，
            直到左键松开。最小尺寸 1024×600（与 WM_GETMINMAXINFO 一致）；
            最大化时禁用（与原生行为一致）。"""
            if not _hwnd[0]:
                return
            if user32.IsZoomed(_hwnd[0]):
                return
            direction = str(direction or '').lower()
            if direction not in ('n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw'):
                return

            def _worker():
                r0 = ctypes.wintypes.RECT()
                if not user32.GetWindowRect(_hwnd[0], ctypes.byref(r0)):
                    return
                left0, top0, right0, bottom0 = r0.left, r0.top, r0.right, r0.bottom
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
                    if right - left < MIN_TRACK_W:
                        if 'e' in direction:
                            right = left + MIN_TRACK_W
                        else:
                            left = right - MIN_TRACK_W
                    if bottom - top < MIN_TRACK_H:
                        if 's' in direction:
                            bottom = top + MIN_TRACK_H
                        else:
                            top = bottom - MIN_TRACK_H
                    user32.SetWindowPos(
                        _hwnd[0], None, left, top, right - left, bottom - top,
                        SWP_NOZORDER | SWP_NOACTIVATE,
                    )
                    if not (user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000):
                        break
                    time.sleep(0.01)

                # 意图真源：缩放结束时更新（缩放全程 SetWindowPos，外框即意图）
                _record_normal_bounds()

            threading.Thread(target=_worker, name="win-resize", daemon=True).start()

        def snap_maximize(self):
            """T5 顶边吸附：shell.html 检测拖动松手时光标位于主屏物理顶边时
            调用。直接原生最大化（SW_MAXIMIZE），铺满工作区不挡任务栏由
            WM_GETMINMAXINFO 保证；不刷新意图矩形（拖动结束时已更新）。"""
            if _hwnd[0] and not user32.IsZoomed(_hwnd[0]):
                user32.ShowWindow(_hwnd[0], SW_MAXIMIZE)

        def set_drag_exclusions(self, items):
            """接收 shell.html 上报的语义命中区（物理像素、客户区坐标），
            作为 WM_NCHITTEST 命中表数据源：
              [{'kind': 'button', 'name': 'min'|'max'|'close', 'x','y','w','h'},
               {'kind': 'exclude', 'name': '...', 'x','y','w','h'}]
            """
            try:
                _hit_regions[0] = [it for it in (items or []) if isinstance(it, dict)]
            except Exception:
                _hit_regions[0] = []

    window_api = WindowApi()

    # T6：计算恢复目标几何（多显示器/DPI 容错，无效则回退默认 1280×800 居中）。
    # R1 注：这里的 x/y/w/h 仅作 hidden 创建期的第一帧近似与兜底（pywebview
    # 按逻辑像素 × DPI 解释，150% 下与保存的物理像素有偏差）；精确几何由
    # _install_hook 在 window.show() 之后用 SetWindowPlacement 设定。
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
        # KL-1.2.3-04 路线①：保留原生窗体样式集（WS_CAPTION/WS_THICKFRAME/
        # WS_SYSMENU/最小最大化按钮 → 系统菜单、Win+方向键贴靠、原生循环整批
        # 回归），可见边框由 WM_NCCALCSIZE 抹掉；hidden 创建避免原生标题栏
        # 闪现，样式/几何就绪后再 _install_hook 里 show()
        frameless=False,
        hidden=True,
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

    # 兜底：覆盖其它退出路径，幂等停止 PLW 拉起的 DSH（用户自启的不杀）
    try:
        from common import dsh_bridge
        dsh_bridge.stop()
    except Exception as e:
        print(f"[Desktop] 停止 DSH 失败: {e}")

    tray.stop()


if __name__ == '__main__':
    main()
