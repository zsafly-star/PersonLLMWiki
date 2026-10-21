"""PersonLLMWiki 桌面入口。

单进程双线程：
  - 后台线程：Flask 后端（import 现有 app）
  - 主线程：PyWebView 原生窗口

窗口壳管理（自绘顶栏 + 原生行为回归）已抽到 common/window_chrome.py，
本文件只负责装配：Flask / 托盘 / 单实例 / 首次启动 / MCP launcher。

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

# ── 冻结包固定 pythonnet 走 .NET Framework（netfx）────────────────
# pythonnet 3.1 在 PyInstaller 冻结包里会选到 CoreCLR（用 _internal/pythonnet/runtime
# 那套 netstandard 门面），而本机只有 .NET 6 运行时、没有 WindowsDesktop 共享框架：
# clr.AddReference('System.Windows.Forms') → FileNotFoundException → pywebview 的
# winforms 后端初始化失败 → webview.start() 抛错 → 窗口没出来、进程启动几秒后退出。
# 源码态 pythonnet 默认就走 netfx，所以只有安装版复现（1.2.3.005 实测）。
# setdefault：不覆盖用户/环境显式设置。必须早于任何 clr/webview 导入。
os.environ.setdefault('PYTHONNET_RUNTIME', 'netfx')

# 禁用 fastmcp 的启动版本检查（check_for_updates）。打包版 MCP 子进程启动时若联网
# 检查 PyPI，会走 httpx → ssl.create_default_context()，缺 certifi CA 证书会直接崩，
# 离线环境还会拖慢启动 2 秒。桌面应用无需检查 fastmcp 新版本。
os.environ.setdefault('FASTMCP_CHECK_FOR_UPDATES', 'off')

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

import threading
import urllib.request
import socket

# 确保能 import 项目模块
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from common.port_utils import find_free_port
from common.desktop_prefs import get_port, set_port, get_window_state, set_window_state
from common.window_chrome import WindowChrome, WINDOW_TITLE

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


def _ensure_first_launch_setup():
    from common.desktop_prefs import is_first_launch, mark_launched
    from config import Config

    if not is_first_launch():
        return False

    # .env 写入用户数据目录
    env_path = os.path.join(Config.USER_DATA_DIR, '.env')
    os.makedirs(Config.USER_DATA_DIR, exist_ok=True)
    if not os.path.isfile(env_path):
        with open(env_path, 'w', encoding='utf-8') as f:
            f.write(f"RESOURCE_BASE_PATH={Config.RESOURCE_BASE_PATH}\n")

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
        hwnd = user32.FindWindowW(None, WINDOW_TITLE)
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
    _ensure_first_launch_setup()

    # ========== 窗口壳（WindowChrome 承载自绘顶栏 + 原生行为） ==========

    chrome = WindowChrome()

    # T6：读取上次保存的窗口状态（位置/尺寸 + 最大化），计算恢复目标几何
    _saved_bounds, _saved_maximized = get_window_state()
    _win_x, _win_y, _win_w, _win_h, _validated_bounds = chrome.compute_initial_geometry(
        _saved_bounds, _saved_maximized
    )

    def _quit_app():
        """托盘/升级入口：真正退出。"""
        # T6：真正退出前保存窗口状态
        try:
            bounds, maximized = chrome.save_state()
            set_window_state(bounds, maximized)
        except Exception as e:
            print(f"[Desktop] 保存窗口状态失败: {e}")
        # 停止 PLW 拉起的 DSH（只杀本进程拉起的，用户自启的不误杀；绝不阻塞退出）
        try:
            from common import dsh_bridge
            dsh_bridge.stop()
        except Exception as e:
            print(f"[Desktop] 停止 DSH 失败: {e}")
        chrome.request_close()

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
        on_show_window=chrome.restore_window,
        on_quit=_quit_app,
        on_toggle_mode=_toggle_mode,
    )

    url = f"http://127.0.0.1:{port}/shell"
    print(f"[Desktop] 创建窗口: {url}")

    class WindowApi:
        """注入到 JS 的窗口控制桥（window.pywebview.api.*）。纯委托给 WindowChrome。"""

        def __init__(self, chrome):
            self._chrome = chrome

        def minimize(self):
            self._chrome.minimize()

        def toggle_maximize(self):
            self._chrome.toggle_maximize()

        def is_maximized(self):
            return self._chrome.is_maximized()

        def close(self):
            self._chrome.close()

        def start_drag(self):
            self._chrome.start_drag()

        def start_resize(self, direction):
            self._chrome.start_resize(direction)

        def snap_maximize(self):
            self._chrome.snap_maximize()

    window_api = WindowApi(chrome)

    _win_kwargs = dict(
        url=url,
        title=WINDOW_TITLE,
        width=_win_w,
        height=_win_h,
        min_size=(1024, 600),
        # KL-1.2.3-04 路线①：保留原生窗体样式集（WS_CAPTION/WS_THICKFRAME/
        # WS_SYSMENU/最小最大化按钮 → 系统菜单、Win+方向键贴靠、原生循环整批
        # 回归），可见边框由 WM_NCCALCSIZE 抹掉；hidden 创建避免原生标题栏
        # 闪现，样式/几何就绪后再 install 里 show()
        frameless=False,
        hidden=True,
        js_api=window_api,
    )
    if _win_x is not None and _win_y is not None:
        _win_kwargs['x'] = _win_x
        _win_kwargs['y'] = _win_y
    window = webview.create_window(**_win_kwargs)
    chrome.pywebview_window = window

    def _notify_win_state(maximized):
        """窗口最大化/还原时，通知 shell 刷新 □/❐ 图标（覆盖原生双击最大化等非 JS 入口）。"""
        try:
            window.evaluate_js(
                "window.__setWinState && window.__setWinState(%s)"
                % ('true' if maximized else 'false')
            )
        except Exception as e:
            print(f"[Desktop] 通知窗口状态失败: {e}")

    def _on_closing():
        # 关闭：非退出态隐藏到托盘并取消关闭，退出态放行
        if chrome.allow_close:
            return True
        chrome.hide_to_tray()
        return False

    window.events.closing += _on_closing
    window.events.maximized += lambda: _notify_win_state(True)
    window.events.restored += lambda: _notify_win_state(False)

    # 窗口图标 + 子类化：线程延迟执行，确保窗口已创建
    def _init_window_hook():
        time.sleep(2)
        chrome.install(window, _get_icon_path(), _validated_bounds, _saved_maximized)
    threading.Thread(target=_init_window_hook, name="win-hook", daemon=True).start()

    tray.start()
    print("[Desktop] 托盘已启动")

    # 阻塞直到用户点击托盘"退出"
    # private_mode=False：让 WebView2 持久化 cookie/local storage。DSH 0.1.5 起 web
    # 需 token 认证，认证后靠持久签名 cookie 维持会话；private_mode 下 cookie 每次
    # 启动清空，跨 PLW 重启后（尤其 DSH 由其他进程拉起、本进程拿不到 stdout token）
    # iframe 只能 401。持久化后只要成功认证过一次即可跨重启复用。
    # 注意：private_mode 是 start() 的参数（非 create_window()），传错位置会直接
    # TypeError（1.2.3.012 实测）。
    webview.start(private_mode=False)
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
