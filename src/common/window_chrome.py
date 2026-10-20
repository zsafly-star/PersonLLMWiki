"""原生窗口壳管理（Win32 子类化 + 自绘顶栏 + 原生行为回归）。

从 desktop.pyw 抽出：用一个 WindowChrome 类承载窗口状态与消息/几何逻辑，
替换原先分散在 main() 里的 9 个单元素列表共享状态。模块级只声明 Win32
常量/结构/API（无副作用），pywebview 仅在 _set_webview_visible 内按需
import（无模块级硬依赖）。纯几何逻辑仍在 window_geometry.py。

设计取舍（见 doc/02-设计/06 与 tasks/KL-1.2.3-04-返工.md）：
  自绘顶栏需要「自定义外观 + 原生行为（贴靠/系统菜单/最大化动画/边缘缩放）」
  二者兼得，故采用 frameless=False 保留 WS_CAPTION 样式 + WM_NCCALCSIZE
  return 0 抹掉视觉标题栏。这套混合体本质上是「和 WinForms 抢消息」，本模块
  的职责是把这层冲突封装收敛，避免继续摊在 desktop.pyw 里牵一发动全身。
"""

import ctypes
import ctypes.wintypes
import os
import threading
import time

from common.window_geometry import clamp_drag_position, validate_restore_bounds

# ── 诊断日志（与原 desktop.pyw 的 _dbg 同路径/同行为）─────────────────
_DEBUG_LOG = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'desktop_debug.log',
)
# 窗口壳调试开关：默认静默，设置 PERSONLLMWIKI_DEBUG_WINDOW=1 时输出
# 高频消息（NCCALCSIZE/MINMAXINFO/WebView2 Visible 切换）与诊断信息。
_DEBUG = os.environ.get('PERSONLLMWIKI_DEBUG_WINDOW') == '1'


def _dbg(msg, force=False):
    """写诊断日志。默认静默；force=True（如切换失败）始终输出。"""
    if not (_DEBUG or force):
        return
    try:
        with open(_DEBUG_LOG, 'a', encoding='utf-8') as f:
            f.write('%s %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), msg))
    except Exception:
        pass
    print(msg, flush=True)


# ── Win32 常量 ──────────────────────────────────────────────────────
WM_CLOSE = 0x0010
WM_SETICON = 0x0080
WM_SIZE = 0x0005
WM_GETMINMAXINFO = 0x0024
WM_NCCALCSIZE = 0x0083
GWL_WNDPROC = -4
SW_HIDE = 0
SW_SHOWNORMAL = 1
SW_MAXIMIZE = 3
SW_SHOWMAXIMIZED = 3  # SetWindowPlacement.showCmd 用名（值同 SW_MAXIMIZE）
SW_RESTORE = 9
ICON_SMALL = 0
ICON_BIG = 1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
SPI_GETWORKAREA = 0x0030
MONITOR_DEFAULTTONULL = 0
MONITOR_DEFAULTTONEAREST = 2
MONITOR_DEFAULTTOPRIMARY = 1
SM_XVIRTUALSCREEN = 76   # 虚拟屏幕（所有显示器包围盒）左上角 X
SM_YVIRTUALSCREEN = 77   # 虚拟屏幕左上角 Y
SM_CXVIRTUALSCREEN = 78  # 虚拟屏幕宽度
SM_CYVIRTUALSCREEN = 79  # 虚拟屏幕高度
MIN_TRACK_W, MIN_TRACK_H = 1024, 600
WINDOW_TITLE = 'PersonLLMWiki'  # 原生窗口标题：desktop.pyw 创建窗口 / FindWindow 查找句柄共用
# JS 驱动拖动：轮询松键 + 边界钳制参数
VK_LBUTTON = 0x01
MIN_VISIBLE_W = 120  # 水平边界钳制：窗口至少保留的可见宽度（像素）


# ── ctypes 结构 ─────────────────────────────────────────────────────
class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ('cbSize', ctypes.wintypes.DWORD),
        ('rcMonitor', ctypes.wintypes.RECT),
        ('rcWork', ctypes.wintypes.RECT),
        ('dwFlags', ctypes.wintypes.DWORD),
    ]


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


# ── Win32 API ───────────────────────────────────────────────────────
user32 = ctypes.windll.user32
dwmapi = ctypes.windll.dwmapi

WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_longlong,          # LRESULT
    ctypes.c_void_p,            # HWND
    ctypes.c_uint,              # UINT msg
    ctypes.c_ulonglong,         # WPARAM (UINT_PTR on 64-bit)
    ctypes.c_longlong,          # LPARAM (LONG_PTR on 64-bit)
)

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
user32.IsIconic.argtypes = [ctypes.c_void_p]
user32.IsIconic.restype = ctypes.c_bool
user32.GetWindowPlacement.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
user32.GetWindowPlacement.restype = ctypes.c_bool
user32.SetWindowPlacement.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
user32.SetWindowPlacement.restype = ctypes.c_bool
user32.MonitorFromPoint.argtypes = [ctypes.wintypes.POINT, ctypes.c_uint]
user32.MonitorFromPoint.restype = ctypes.c_void_p
user32.SystemParametersInfoW.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
user32.SystemParametersInfoW.restype = ctypes.c_bool
user32.MonitorFromWindow.argtypes = [ctypes.c_void_p, ctypes.c_uint]
user32.MonitorFromWindow.restype = ctypes.c_void_p
user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(MONITORINFO)]
user32.GetMonitorInfoW.restype = ctypes.c_bool
user32.MonitorFromRect.argtypes = [ctypes.POINTER(ctypes.wintypes.RECT), ctypes.c_uint]
user32.MonitorFromRect.restype = ctypes.c_void_p

dwmapi.DwmSetWindowAttribute.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
dwmapi.DwmSetWindowAttribute.restype = ctypes.c_long


class WindowChrome:
    """承载原生窗口壳的全部状态与消息/几何逻辑。

    状态（原 9 个单元素列表）收敛为实例属性；desktop.pyw 只负责装配
    （Flask/托盘/单实例/首次启动/MCP）并把 pywebview Window 注入进来。
    """

    def __init__(self):
        self.hwnd = None                     # 父窗口句柄（FindWindowW 找到后写入）
        self.allow_close = False             # closing 事件里是否真正关闭（否则隐藏到托盘）
        self.last_normal_bounds = None       # 最近正常态外框（屏幕物理像素）——□ 还原的确定性目标
        self.was_minimized = False           # 是否处于最小化（WM_SIZE 跟踪，区分「从最小化恢复」与普通 resize）
        self.last_work_area = None           # 窗口非最小化时最近一次 workarea 缓存（最小化态回退用）
        self.pywebview_window = None         # pywebview Window（用于切换 WebView2 Visible / maximize / minimize）
        self._wndproc_callback = None        # WNDPROC 回调引用（防 GC）
        self._original_wndproc = None        # 子类化前原始 WndProc（CallWindowProcW 链回 WinForms）

    # ── 对外（desktop.pyw / 托盘 / JS 桥调用）────────────────────────

    def install(self, window, icon_path, restore_bounds, restore_maximized):
        """找句柄 → 设图标 → 子类化父窗口 → SWP_FRAMECHANGED → 圆角 → show → 几何恢复。

        R2 兜底：整体包 try/finally —— 任何一步抛异常或找不到句柄提前 return
        都不能跳过 window.show()，否则 hidden 创建的窗口永不显示、托盘也救不回来。
        """
        try:
            print("[Desktop] _install_hook: 开始查找窗口...", flush=True)
            for i in range(15):
                self.hwnd = user32.FindWindowW(None, WINDOW_TITLE)
                if self.hwnd:
                    print(f"[Desktop] _install_hook: 找到窗口句柄 {self.hwnd} (第{i + 1}次尝试)", flush=True)
                    break
                time.sleep(0.2)
            if not self.hwnd:
                print("[Desktop] 警告: 未找到窗口句柄", flush=True)
                return

            # 设置标题栏/任务栏图标
            if icon_path:
                hicon = user32.LoadImageW(
                    None, icon_path, 1, 0, 0, 0x0010 | 0x0040
                )
                if hicon:
                    user32.SendMessageW(self.hwnd, WM_SETICON, ICON_SMALL, hicon)
                    user32.SendMessageW(self.hwnd, WM_SETICON, ICON_BIG, hicon)

            # 子类化父窗口（WM_NCCALCSIZE / WM_GETMINMAXINFO）
            self._wndproc_callback = WNDPROC(self._wndproc)
            self._original_wndproc = user32.SetWindowLongPtrW(
                self.hwnd, GWL_WNDPROC, self._wndproc_callback
            )
            print("[Desktop] 父窗口子类化完成", flush=True)

            # 强制重算非客户区：WM_NCCALCSIZE 子类 return 0 已把客户区=整窗，
            # 但窗口以 frameless=False(WS_CAPTION) 创建后，首次 Show() 不会重新
            # 计算框架 → 仍按 WS_CAPTION 画出原生标题栏，与自绘顶栏叠成上下两个
            # 菜单栏。SWP_FRAMECHANGED 触发一次 WM_NCCALCSIZE，让抹边框在首次
            # 显示即生效（实测 client_top_offset 30→0）。
            user32.SetWindowPos(
                self.hwnd, None, 0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
            )

            # Win11 圆角（DWMWA_WINDOW_CORNER_PREFERENCE=33，DWMWCP_ROUND=2）
            _corner = ctypes.c_int(2)
            try:
                dwmapi.DwmSetWindowAttribute(self.hwnd, 33, ctypes.byref(_corner), 4)
            except Exception as e:
                print(f"[Desktop] 设置圆角失败: {e}")
        finally:
            # hidden 创建 → 样式集/图标就绪后再显示，避免原生标题栏闪现
            try:
                window.show()
            except Exception as e:
                print(f"[Desktop] 显示窗口失败: {e}")

        # 几何恢复在 window.show() 之后统一走 _apply_normal_placement
        if not self.hwnd:
            return
        if restore_bounds:
            if self._apply_normal_placement(
                restore_bounds,
                SW_SHOWMAXIMIZED if restore_maximized else SW_SHOWNORMAL,
            ):
                self.last_normal_bounds = tuple(restore_bounds)
        elif restore_maximized:
            user32.ShowWindow(self.hwnd, SW_MAXIMIZE)

    def restore_window(self):
        """托盘回调：恢复并聚焦窗口。"""
        if self.hwnd:
            user32.ShowWindow(self.hwnd, SW_RESTORE)
            user32.SetForegroundWindow(self.hwnd)

    def hide_to_tray(self):
        """关闭到托盘：隐藏窗口（window.events.closing 回调调用）。"""
        if self.hwnd:
            user32.ShowWindow(self.hwnd, SW_HIDE)

    def request_close(self):
        """真正退出：放行 closing 并投递关闭消息（不再隐藏到托盘）。"""
        self.allow_close = True
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)

    def minimize(self):
        if self.pywebview_window:
            self.pywebview_window.minimize()

    def toggle_maximize(self):
        if not self.hwnd:
            return
        if user32.IsZoomed(self.hwnd):
            # □ 还原：SetWindowPlacement 的 realize 会把窗口矩形放大一次帧边距，
            # 故先设 placement 再用 SetWindowPos（不经帧换算）纠偏钉回意图矩形；
            # 无意图记录才回退 SW_RESTORE
            bounds = self.last_normal_bounds
            if bounds:
                if self._apply_normal_placement(bounds, SW_SHOWNORMAL):
                    user32.SetWindowPos(
                        self.hwnd, None,
                        bounds[0], bounds[1],
                        bounds[2] - bounds[0], bounds[3] - bounds[1],
                        SWP_NOZORDER | SWP_NOACTIVATE,
                    )
                else:
                    user32.ShowWindow(self.hwnd, SW_RESTORE)
            else:
                user32.ShowWindow(self.hwnd, SW_RESTORE)
        else:
            # 最大化：走 WinForms 状态机（window.maximize → WindowState=Maximized），
            # 而非原生 ShowWindow(SW_MAXIMIZE)。原生 ShowWindow 绕过状态机、WinForms
            # 不知窗口已最大化 → 后续「最小化→点任务栏恢复」时按 Normal 恢复。
            if self.pywebview_window:
                self.pywebview_window.maximize()
            else:
                user32.ShowWindow(self.hwnd, SW_MAXIMIZE)

    def is_maximized(self):
        return bool(self.hwnd and user32.IsZoomed(self.hwnd))

    def close(self):
        # 走 closing 事件：非退出态隐藏到托盘，与系统 ✕ 语义一致
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)

    def start_drag(self):
        """拖动窗口（JS 驱动）：后台线程跟随鼠标相对位移移动窗口，直到左键松开。"""
        if not self.hwnd:
            return

        def _worker():
            was_maximized = user32.IsZoomed(self.hwnd)
            last_bounds = None
            if was_maximized:
                grab_pt = ctypes.wintypes.POINT()
                user32.GetCursorPos(ctypes.byref(grab_pt))
                max_rect = ctypes.wintypes.RECT()
                user32.GetWindowRect(self.hwnd, ctypes.byref(max_rect))
                user32.ShowWindow(self.hwnd, SW_RESTORE)
                time.sleep(0.08)
                r_restored = ctypes.wintypes.RECT()
                if not user32.GetWindowRect(self.hwnd, ctypes.byref(r_restored)):
                    return
                intent = self.last_normal_bounds
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
                    self.hwnd, None, new_left, max_rect.top,
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
                    if not user32.GetWindowRect(self.hwnd, ctypes.byref(r)):
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
                        self.hwnd, None, new_left, new_top, 0, 0,
                        SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE,
                    )
                    last_bounds = (new_left, new_top,
                                   new_left + w, new_top + h)
                pt_prev.x = pt.x
                pt_prev.y = pt.y
                if not (user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000):
                    break
                time.sleep(0.01)

            # 意图真源：拖动结束时更新
            if last_bounds:
                self.last_normal_bounds = last_bounds
            else:
                self._record_normal_bounds()

        threading.Thread(target=_worker, name="win-drag", daemon=True).start()

    def start_resize(self, direction):
        """边缘缩放（JS 驱动）：后台线程按方向拖动窗口边/角，直到左键松开。"""
        if not self.hwnd:
            return
        if user32.IsZoomed(self.hwnd):
            return
        direction = str(direction or '').lower()
        if direction not in ('n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw'):
            return

        def _worker():
            r0 = ctypes.wintypes.RECT()
            if not user32.GetWindowRect(self.hwnd, ctypes.byref(r0)):
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
                    self.hwnd, None, left, top, right - left, bottom - top,
                    SWP_NOZORDER | SWP_NOACTIVATE,
                )
                if not (user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000):
                    break
                time.sleep(0.01)

            self._record_normal_bounds()

        threading.Thread(target=_worker, name="win-resize", daemon=True).start()

    def snap_maximize(self):
        """顶边吸附：拖动松手时光标位于主屏物理顶边时调用（原生最大化）。"""
        if self.hwnd and not user32.IsZoomed(self.hwnd):
            user32.ShowWindow(self.hwnd, SW_MAXIMIZE)

    def save_state(self):
        """返回当前窗口状态 (bounds, maximized)，由调用方落盘。

        最大化状态由系统维护（IsZoomed）；bounds：普通态读 GetWindowRect，
        最大化态取 last_normal_bounds（意图矩形——SetWindowPlacement 的 realize
        会把窗口矩形放大一次帧边距，系统 rcNormalPosition 会被同步污染，不可作
        真源；意图无记录时才回退读 rcNormalPosition）。关闭到托盘不在此路径。
        """
        maximized = bool(self.hwnd and user32.IsZoomed(self.hwnd))
        bounds = None
        if maximized:
            if self.last_normal_bounds:
                bounds = tuple(self.last_normal_bounds)
            else:
                wp = WINDOWPLACEMENT()
                wp.length = ctypes.sizeof(WINDOWPLACEMENT)
                if user32.GetWindowPlacement(self.hwnd, ctypes.byref(wp)):
                    rc = wp.rcNormalPosition
                    ox, oy = self._primary_work_area_origin()
                    bounds = (rc.left + ox, rc.top + oy,
                              rc.right + ox, rc.bottom + oy)
        elif self.hwnd:
            r = ctypes.wintypes.RECT()
            if user32.GetWindowRect(self.hwnd, ctypes.byref(r)):
                bounds = (r.left, r.top, r.right, r.bottom)
        if bounds:
            bounds = self._validate_window_bounds(bounds)
        return (bounds, maximized)

    def compute_initial_geometry(self, saved_bounds, saved_maximized):
        """计算 create_window 用的初始几何（多显示器/DPI 容错）。

        返回 (x, y, w, h, validated_bounds)：x/y 为 None 表示由系统居中；
        validated_bounds 供 install 阶段 SetWindowPlacement 精确恢复。
        """
        validated = self._validate_window_bounds(saved_bounds)
        if saved_maximized:
            # 最大化：直接用目标显示器 workarea 创建，避免「先小后大」的可见跳变
            work = self._get_work_area_for_bounds(validated or saved_bounds)
            if work:
                return (work[0], work[1], work[2] - work[0], work[3] - work[1], validated)
            return (None, None, 1280, 800, validated)
        if validated:
            return (validated[0], validated[1],
                    max(validated[2] - validated[0], 1024),
                    max(validated[3] - validated[1], 600),
                    validated)
        return (None, None, 1280, 800, validated)

    # ── 消息处理 ────────────────────────────────────────────────────

    def _set_webview_visible(self, visible):
        """切换 WebView2 控件可见性（WinForms Visible），强制恢复重绘。

        窗口最小化时 WebView2 子窗口不自动收窗口消息，恢复后不重绘 → 白屏。
        .NET WinForms 后端不暴露 CoreWebView2Controller.IsVisible，改用控件
        自身 Visible：最小化置 False、恢复置 True，WebView2 内部据 Visible 变化
        同步底层 controller 可见性并触发重绘。
        """
        try:
            from webview.platforms import winforms as _wf
            w = self.pywebview_window
            if not w:
                _dbg("[Desktop] WebView2 Visible: 无 pywebview window")
                return
            bv = _wf.BrowserView.instances.get(w.uid)
            if not bv:
                _dbg("[Desktop] WebView2 Visible: 无 BrowserView")
                return
            wv = getattr(bv, 'webview', None)
            if wv is None:
                _dbg("[Desktop] WebView2 Visible: 无 webview 控件")
                return
            before = wv.Visible
            wv.Visible = bool(visible)
            _dbg(f"[Desktop] WebView2 Visible: {before} -> {bool(visible)}")
        except Exception as e:
            _dbg(f"[Desktop] 切换 WebView2 Visible 失败: {e}", force=True)

    def _wndproc(self, hwnd, msg, wparam, lparam):
        """父窗口子类化消息处理。

        只处理逃不掉的原生消息：WM_NCCALCSIZE（抹边框）、WM_GETMINMAXINFO（最小尺寸）、
        WM_SIZE（最小化白屏重绘）。WM_CLOSE（关闭到托盘）已改用 window.events.closing
        （见 desktop.pyw）——它是 should_lock=True 事件，在 UI 线程同步回调。
        minimized/restored 事件是后台线程异步回调，而 _set_webview_visible 需在
        UI 线程操作 WinForms 控件，故最小化白屏仍保留 WM_SIZE 子类化。
        """
        if msg == WM_SIZE:
            if wparam == 1:  # SIZE_MINIMIZED
                self.was_minimized = True
                self._set_webview_visible(False)
            elif wparam in (0, 2) and self.was_minimized:  # SIZE_RESTORED / SIZE_MAXIMIZED
                self.was_minimized = False
                self._set_webview_visible(True)
            # 不 return：WM_SIZE 必须继续交给 WinForms 更新内部状态
        if msg == WM_NCCALCSIZE:
            if wparam and user32.IsZoomed(hwnd):
                # 最大化时把 rgrc[0] 钉在工作区，避免四边溢出、底部压住任务栏
                work = self._get_work_area()
                if work:
                    _dbg(f"[Desktop] NCCALCSIZE zoom work=({work[0]},{work[1]})-({work[2]},{work[3]})")
                    rc = ctypes.cast(
                        ctypes.c_void_p(lparam),
                        ctypes.POINTER(ctypes.wintypes.RECT),
                    ).contents
                    rc.left, rc.top, rc.right, rc.bottom = work
            # 两分支统一 return 0（客户区=整窗，抹掉原生边框/标题栏）
            return 0
        if msg == WM_GETMINMAXINFO:
            self._fill_minmaxinfo(hwnd, lparam)
            return 0
        return user32.CallWindowProcW(
            self._original_wndproc, hwnd, msg, wparam, lparam
        )

    # ── 几何辅助 ────────────────────────────────────────────────────

    def _primary_work_area_origin(self):
        """主显示器 workarea 左上角（rcNormalPosition 的 workspace 坐标原点）。"""
        pt = ctypes.wintypes.POINT(0, 0)
        monitor = user32.MonitorFromPoint(pt, MONITOR_DEFAULTTOPRIMARY)
        if monitor:
            mi = MONITORINFO()
            mi.cbSize = ctypes.sizeof(MONITORINFO)
            if user32.GetMonitorInfoW(monitor, ctypes.byref(mi)):
                return (mi.rcWork.left, mi.rcWork.top)
        return (0, 0)

    def _record_normal_bounds(self):
        """把当前窗口外框记为意图矩形 last_normal_bounds（拖动/缩放结束调用）。"""
        hwnd = self.hwnd
        if not hwnd or user32.IsZoomed(hwnd):
            return
        r = ctypes.wintypes.RECT()
        if user32.GetWindowRect(hwnd, ctypes.byref(r)):
            self.last_normal_bounds = (r.left, r.top, r.right, r.bottom)

    def _apply_normal_placement(self, bounds, show_cmd):
        """把 bounds 设为窗口正常矩形 + showCmd。返回是否成功。"""
        hwnd = self.hwnd
        if not hwnd or not bounds:
            return False
        ox, oy = self._primary_work_area_origin()
        wp = WINDOWPLACEMENT()
        wp.length = ctypes.sizeof(WINDOWPLACEMENT)
        wp.showCmd = show_cmd
        wp.rcNormalPosition.left = bounds[0] - ox
        wp.rcNormalPosition.top = bounds[1] - oy
        wp.rcNormalPosition.right = bounds[2] - ox
        wp.rcNormalPosition.bottom = bounds[3] - oy
        return bool(user32.SetWindowPlacement(hwnd, ctypes.byref(wp)))

    def _get_work_area(self):
        """返回窗口当前所在显示器的 workarea（屏幕去任务栏）矩形。

        用 MONITOR_DEFAULTTONULL 语义：窗口矩形不与任何显示器相交（最小化在
        (-32000,-32000) 或恢复过渡态）时返回 NULL——此时不能据窗口定位显示器
        （NEAREST 会就近误取邻屏），回退到 last_work_area 缓存；缓存也无才退回
        主显示器 SPI_GETWORKAREA。返回 (left, top, right, bottom)，失败 None。
        """
        hwnd = self.hwnd
        if hwnd:
            monitor = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONULL)
            if monitor:
                mi = MONITORINFO()
                mi.cbSize = ctypes.sizeof(MONITORINFO)
                if user32.GetMonitorInfoW(monitor, ctypes.byref(mi)):
                    wa = (mi.rcWork.left, mi.rcWork.top,
                          mi.rcWork.right, mi.rcWork.bottom)
                    self.last_work_area = wa
                    return wa
        if self.last_work_area:
            return self.last_work_area
        rect = ctypes.wintypes.RECT()
        if user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0):
            return (rect.left, rect.top, rect.right, rect.bottom)
        return None

    def _get_work_area_for_bounds(self, bounds):
        """返回指定 bounds 所在显示器的 workarea（窗口未创建前可用）。"""
        monitor = None
        if bounds:
            r = ctypes.wintypes.RECT(bounds[0], bounds[1], bounds[2], bounds[3])
            monitor = user32.MonitorFromRect(ctypes.byref(r), MONITOR_DEFAULTTONEAREST)
        if monitor:
            mi = MONITORINFO()
            mi.cbSize = ctypes.sizeof(MONITORINFO)
            if user32.GetMonitorInfoW(monitor, ctypes.byref(mi)):
                return (mi.rcWork.left, mi.rcWork.top, mi.rcWork.right, mi.rcWork.bottom)
        rect = ctypes.wintypes.RECT()
        if user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0):
            return (rect.left, rect.top, rect.right, rect.bottom)
        return None

    def _fill_minmaxinfo(self, hwnd, lparam):
        """WM_GETMINMAXINFO：原生最大化按窗口所在显示器工作区 + 拖拽尺寸约束。"""
        work = self._get_work_area()
        if not work:
            return
        left, top, right, bottom = work
        _dbg(f"[Desktop] MINMAXINFO work=({left},{top})-({right},{bottom}) iconic={bool(self.hwnd and user32.IsIconic(self.hwnd))}")
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

    def _validate_window_bounds(self, bounds):
        """校验保存的窗口 bounds 是否仍落在虚拟屏幕内（多显示器/DPI 容错）。"""
        if not bounds:
            return None
        vx = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        vy = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        vw = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
        vh = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
        return validate_restore_bounds(
            bounds, vx=vx, vy=vy, vx2=vx + vw, vy2=vy + vh,
        )
