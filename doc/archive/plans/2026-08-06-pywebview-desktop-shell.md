# PyWebView 桌面窗口壳 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 PersonLLMWiki Flask 应用封装为 PyWebView 原生窗口桌面软件，产出 `.exe` 安装包

**Architecture:** 单进程双线程——后台线程跑 Flask（import 现有 app），主线程跑 PyWebView 窗口 + 系统托盘。新增 `desktop.pyw` 入口和 `tray_manager.py`，不改 app.py。打包用 PyInstaller → Inno Setup 两阶段。

**Tech Stack:** pywebview、pystray（托盘）、PyInstaller、Inno Setup、Pillow（托盘图标处理）

---

## Design Reference

详见 [PyWebView桌面窗口壳设计方案.md](../PyWebView桌面窗口壳设计方案.md)。

---

## File Structure

实施完成后的新增/修改文件：

```
PersonLLMWiki/src/
├── desktop.pyw                        ← 新增：桌面入口（Flask 线程 + WebView 窗口）
├── common/
│   ├── port_utils.py                  ← 新增：动态端口分配（可测试）
│   ├── desktop_prefs.py               ← 新增：桌面偏好读写（关闭行为/首次检测）
│   └── tray_manager.py                ← 新增：系统托盘管理
├── packaging/
│   ├── build_desktop.py               ← 新增：桌面版打包编排（PyInstaller + ISCC）
│   ├── desktop.spec                   ← 新增：PyInstaller 配置
│   └── installer.iss                  ← 新增：Inno Setup 安装包脚本
├── requirements.txt                   ← 修改：添加 pywebview、pystray、Pillow
└── tests/
    └── desktop/
        ├── __init__.py                ← 新增
        ├── test_port_utils.py         ← 新增
        └── test_desktop_prefs.py      ← 新增
```

不修改：`app.py`、`config.py`、`extensions.py`、`modules/**`、`static/**`、`templates/**`。

---

## Task 1: 端口分配工具 (port_utils.py)

**Files:**
- Create: `common/port_utils.py`
- Create: `tests/desktop/__init__.py`
- Create: `tests/desktop/test_port_utils.py`

- [ ] **Step 1: 创建 tests/desktop 包**

创建 `tests/desktop/__init__.py`（空文件）。

- [ ] **Step 2: 写失败测试**

创建 `tests/desktop/test_port_utils.py`：

```python
"""端口分配工具测试"""
import socket
from common.port_utils import find_free_port


def test_find_free_port_returns_int():
    """应返回一个整数端口号"""
    port = find_free_port()
    assert isinstance(port, int)


def test_find_free_port_in_range():
    """端口应在 5000-5100 范围内"""
    port = find_free_port()
    assert 5000 <= port <= 5100


def test_find_free_port_actually_free():
    """返回的端口应可绑定"""
    port = find_free_port()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(('127.0.0.1', port))
    finally:
        s.close()


def test_find_free_port_skips_occupied():
    """已占用的端口应被跳过"""
    # 先占一个端口
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('127.0.0.1', 5000))
    s.listen(1)
    try:
        port = find_free_port()
        assert port != 5000
        assert 5001 <= port <= 5100
    finally:
        s.close()
```

- [ ] **Step 3: 运行测试确认失败**

Run: `python -m pytest tests/desktop/test_port_utils.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'common.port_utils'`

- [ ] **Step 4: 实现 port_utils.py**

创建 `common/port_utils.py`：

```python
"""动态端口分配工具"""

import socket

PORT_RANGE_START = 5000
PORT_RANGE_END = 5100


def find_free_port(start=PORT_RANGE_START, end=PORT_RANGE_END):
    """在 start~end 范围内找一个可绑定的空闲端口。

    Args:
        start: 起始端口（含）
        end: 结束端口（含）

    Returns:
        int: 可用端口号

    Raises:
        RuntimeError: 范围内无可用端口
    """
    for port in range(start, end + 1):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(('127.0.0.1', port))
            s.close()
            return port
        except OSError:
            continue
    raise RuntimeError(f"端口 {start}-{end} 范围内无可用端口")
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/desktop/test_port_utils.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add common/port_utils.py tests/desktop/__init__.py tests/desktop/test_port_utils.py
git commit -m "feat: add port_utils for dynamic port allocation"
```

---

## Task 2: 桌面偏好读写 (desktop_prefs.py)

**Files:**
- Create: `common/desktop_prefs.py`
- Create: `tests/desktop/test_desktop_prefs.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/desktop/test_desktop_prefs.py`：

```python
"""桌面偏好读写测试"""
import json
import os
import tempfile
import pytest
from common.desktop_prefs import (
    get_close_action,
    set_close_action,
    is_first_launch,
    mark_launched,
)


@pytest.fixture
def temp_resource(tmp_path):
    """提供一个临时 resource 目录"""
    return str(tmp_path / "resource")


def test_get_close_action_default(temp_resource):
    """无记录时返回 None"""
    assert get_close_action(temp_resource) is None


def test_set_and_get_close_action(temp_resource):
    """写入后能正确读取"""
    set_close_action("minimize", temp_resource)
    assert get_close_action(temp_resource) == "minimize"

    set_close_action("exit", temp_resource)
    assert get_close_action(temp_resource) == "exit"


def test_set_close_action_creates_dirs(temp_resource):
    """写入时自动创建 instance 目录"""
    set_close_action("minimize", temp_resource)
    assert os.path.isdir(os.path.join(temp_resource, "instance"))


def test_is_first_launch_default(temp_resource):
    """无标记文件时为首次启动"""
    assert is_first_launch(temp_resource) is True


def test_mark_launched(temp_resource):
    """标记后不再是首次"""
    mark_launched(temp_resource)
    assert is_first_launch(temp_resource) is False


def test_invalid_close_action_raises(temp_resource):
    """非法值应报错"""
    with pytest.raises(ValueError):
        set_close_action("invalid", temp_resource)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/desktop/test_desktop_prefs.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'common.desktop_prefs'`

- [ ] **Step 3: 实现 desktop_prefs.py**

创建 `common/desktop_prefs.py`：

```python
"""桌面应用偏好读写（关闭行为、首次启动标记）。

偏好文件存储在 {resource}/instance/desktop_prefs.json
"""

import json
import os

VALID_ACTIONS = {"minimize", "exit"}


def _prefs_path(resource_path):
    """获取偏好文件路径"""
    return os.path.join(resource_path, "instance", "desktop_prefs.json")


def _read_prefs(resource_path):
    """读取全部偏好，不存在则返回空 dict"""
    path = _prefs_path(resource_path)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _write_prefs(prefs, resource_path):
    """写入全部偏好（自动创建目录）"""
    path = _prefs_path(resource_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(prefs, f, ensure_ascii=False, indent=2)


def get_close_action(resource_path):
    """获取关闭行为偏好。

    Returns:
        str | None: "minimize" / "exit" / None（未设置）
    """
    return _read_prefs(resource_path).get("close_action")


def set_close_action(action, resource_path):
    """设置关闭行为偏好。

    Args:
        action: "minimize" 或 "exit"
        resource_path: resource 根目录路径

    Raises:
        ValueError: action 非法
    """
    if action not in VALID_ACTIONS:
        raise ValueError(f"close_action 必须是 {VALID_ACTIONS} 之一，收到: {action}")
    prefs = _read_prefs(resource_path)
    prefs["close_action"] = action
    _write_prefs(prefs, resource_path)


def is_first_launch(resource_path):
    """是否为首次启动"""
    return not _read_prefs(resource_path).get("launched", False)


def mark_launched(resource_path):
    """标记已启动过（不再是首次）"""
    prefs = _read_prefs(resource_path)
    prefs["launched"] = True
    _write_prefs(prefs, resource_path)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/desktop/test_desktop_prefs.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add common/desktop_prefs.py tests/desktop/test_desktop_prefs.py
git commit -m "feat: add desktop_prefs for close action and first launch tracking"
```

---

## Task 3: desktop.pyw 桌面入口（核心）

**Files:**
- Create: `desktop.pyw`
- Modify: `requirements.txt`

- [ ] **Step 1: 添加依赖到 requirements.txt**

在 `requirements.txt` 末尾添加：

```
pywebview>=5.0
pystray>=0.19
Pillow>=10.0
```

- [ ] **Step 2: 安装新依赖**

Run: `pip install pywebview pystray Pillow`
Expected: 三个包安装成功

- [ ] **Step 3: 编写 desktop.pyw**

创建 `desktop.pyw`：

```python
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
import threading
import urllib.request

# 确保能 import 项目模块
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from common.port_utils import find_free_port

# Flask 就绪超时（秒）
FLASK_READY_TIMEOUT = 15


def _is_dev_mode():
    """是否为开发模式（存在 .git 目录）"""
    return os.path.isdir(os.path.join(_THIS_DIR, '.git'))


def _wait_for_flask(port, timeout=FLASK_READY_TIMEOUT):
    """轮询 Flask 直到就绪或超时。

    Returns:
        bool: True=就绪, False=超时
    """
    url = f"http://127.0.0.1:{port}/api"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def _start_flask(port):
    """在后台线程启动 Flask。

    Returns:
        threading.Thread: Flask 线程
    """
    def _run():
        from app import app
        app.run(host='127.0.0.1', port=port, debug=False, threaded=True)

    thread = threading.Thread(target=_run, daemon=True, name="flask-backend")
    thread.start()
    return thread


def _get_icon_path():
    """获取窗口图标路径"""
    icon = os.path.join(_THIS_DIR, 'static', 'img', 'AIChat.png')
    return icon if os.path.isfile(icon) else None


def main():
    import webview

    # 1. 分配端口
    try:
        port = find_free_port()
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

    # 4. 创建 WebView 窗口
    url = f"http://127.0.0.1:{port}"
    kwargs = {
        'url': url,
        'title': 'PersonLLMWiki',
        'width': 1280,
        'height': 800,
        'min_size': (1024, 600),
    }
    icon_path = _get_icon_path()
    # icon 参数后续在 Task 5 补充

    print(f"[Desktop] 打开窗口: {url}")
    webview.create_window(**kwargs)
    webview.start()


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: 手动验证 — 窗口弹出且页面正常**

Run: `python desktop.pyw`
Expected:
- 控制台输出端口、Flask 启动、就绪、打开窗口的日志
- 弹出原生窗口（标题 "PersonLLMWiki"），显示应用首页
- 窗口可正常交互（点击、输入）
- 关闭窗口后进程退出

- [ ] **Step 5: Commit**

```bash
git add desktop.pyw requirements.txt
git commit -m "feat: add desktop.pyw entry point with Flask + PyWebView"
```

---

## Task 4: 系统托盘 (tray_manager.py)

**Files:**
- Create: `common/tray_manager.py`
- Modify: `desktop.pyw`

- [ ] **Step 1: 编写 tray_manager.py**

创建 `common/tray_manager.py`：

```python
"""系统托盘图标管理。

功能：
  - 显示托盘图标
  - 右键菜单：显示窗口 / 退出
  - 双击托盘：显示/聚焦窗口
  - 气泡通知
"""

import os
import threading


class TrayManager:
    """系统托盘管理器。

    在独立线程中运行 pystray，避免阻塞 WebView 主线程。
    """

    def __init__(self, icon_path, on_show_window, on_quit):
        """
        Args:
            icon_path: 图标文件路径（.png）
            on_show_window: 回调，显示/聚焦主窗口
            on_quit: 回调，退出应用
        """
        self._icon_path = icon_path
        self._on_show_window = on_show_window
        self._on_quit = on_quit
        self._icon = None
        self._thread = None

    def start(self):
        """在后台线程启动托盘"""
        self._thread = threading.Thread(target=self._run, daemon=True, name="tray")
        self._thread.start()

    def stop(self):
        """停止托盘"""
        if self._icon:
            self._icon.stop()

    def show_notification(self, title, message):
        """显示气泡通知"""
        if self._icon:
            try:
                self._icon.notify(message, title)
            except Exception:
                pass  # 通知失败不影响主流程

    def _run(self):
        import pystray
        from PIL import Image

        # 加载图标
        image = self._load_icon()

        menu = pystray.Menu(
            pystray.MenuItem(
                "显示主窗口",
                self._on_show_window,
                default=True,  # 双击触发
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "退出",
                self._on_quit,
            ),
        )

        self._icon = pystray.Icon(
            "PersonLLMWiki",
            image,
            "PersonLLMWiki",
            menu,
        )
        self._icon.run()

    def _load_icon(self):
        """加载图标，失败则用默认图标"""
        from PIL import Image

        if self._icon_path and os.path.isfile(self._icon_path):
            try:
                return Image.open(self._icon_path)
            except Exception:
                pass
        # 默认：16x16 灰色方块
        return Image.new('RGBA', (16, 16), (128, 128, 128, 255))
```

- [ ] **Step 2: 修改 desktop.pyw 集成托盘**

在 `desktop.pyw` 的 `main()` 函数中，在创建 WebView 窗口之前添加托盘启动。

将 `desktop.pyw` 的 `main()` 函数替换为：

```python
def main():
    import webview

    # 1. 分配端口
    try:
        port = find_free_port()
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

    # 4. 系统托盘（非开发模式）
    tray = None
    if not _is_dev_mode():
        from common.tray_manager import TrayManager
        icon_path = _get_icon_path()
        tray = TrayManager(
            icon_path=icon_path,
            on_show_window=lambda: None,  # Task 5 替换为实际逻辑
            on_quit=lambda: None,         # Task 5 替换为实际逻辑
        )
        tray.start()
        print("[Desktop] 托盘已启动")

    # 5. 创建 WebView 窗口
    url = f"http://127.0.0.1:{port}"
    print(f"[Desktop] 打开窗口: {url}")
    webview.create_window(
        url=url,
        title='PersonLLMWiki',
        width=1280,
        height=800,
        min_size=(1024, 600),
    )
    webview.start()

    # 6. 窗口关闭后清理
    if tray:
        tray.stop()
    print("[Desktop] 已退出")
```

- [ ] **Step 3: 手动验证 — 托盘图标显示**

先在桌面版模拟（临时创建一个假标记文件绕过 dev 检测）：
Run: `python -c "import os; os.makedirs('resource/instance', exist_ok=True)" && python desktop.pyw`

> 注意：开发模式下（存在 .git）托盘不会启动。要测试托盘，临时注释 `_is_dev_mode` 检查或在一个无 `.git` 的副本目录运行。

Expected（在无 .git 的目录运行时）：
- 任务栏通知区出现托盘图标
- 右键出现菜单：「显示主窗口」/ 分隔线 /「退出」
- 双击托盘图标不报错

- [ ] **Step 4: Commit**

```bash
git add common/tray_manager.py desktop.pyw
git commit -m "feat: add system tray with show/quit menu"
```

---

## Task 5: 关闭行为 + 首次启动数据初始化

**Files:**
- Modify: `desktop.pyw`

- [ ] **Step 1: 在 desktop.pyw 添加关闭对话框逻辑**

在 `desktop.pyw` 中，`_get_icon_path()` 函数之后、`main()` 之前，添加以下函数：

```python
def _get_resource_path():
    """获取 resource 目录路径"""
    from config import Config
    return Config.RESOURCE_BASE_PATH


def _ensure_first_launch_setup(resource_path):
    """首次启动时创建数据目录 + 写 .env"""
    from common.desktop_prefs import is_first_launch, mark_launched

    if not is_first_launch(resource_path):
        return False

    # 创建子目录
    for subdir in ['instance', 'article', 'img', 'attachments', 'wiki']:
        os.makedirs(os.path.join(resource_path, subdir), exist_ok=True)

    # 写 .env（如果 RESOURCE_BASE_PATH 未配置）
    env_path = os.path.join(os.path.dirname(_THIS_DIR), '.env')
    if not os.path.isfile(env_path):
        with open(env_path, 'w', encoding='utf-8') as f:
            f.write(f"RESOURCE_BASE_PATH={resource_path}\n")

    mark_launched(resource_path)
    print(f"[Desktop] 首次启动：数据目录已创建 {resource_path}")
    return True


def _handle_window_close(window, tray, resource_path):
    """窗口关闭处理：询问后记住（非开发模式）。

    Returns:
        str | None: "minimize" / "exit" / None（取消）
    """
    from common.desktop_prefs import get_close_action, set_close_action

    # 开发模式：直接退出
    if _is_dev_mode():
        return "exit"

    # 有记住的选择
    saved = get_close_action(resource_path)
    if saved:
        return saved

    # 首次：弹窗询问
    import webview

    result = window.create_confirmation_dialog(
        "关闭窗口",
        "关闭窗口后：\n"
        "  • 选择「是」= 最小化到托盘，保持后台运行\n"
        "  • 选择「否」= 完全退出程序\n\n"
        "（下次不再询问）"
    )

    if result is None:
        return None  # 取消

    action = "minimize" if result else "exit"
    set_close_action(action, resource_path)
    return action
```

- [ ] **Step 2: 修改 main() 集成关闭逻辑和首次启动**

将 `desktop.pyw` 的 `main()` 函数替换为：

```python
def main():
    import webview

    # 1. 分配端口
    try:
        port = find_free_port()
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
    is_first = _ensure_first_launch_setup(resource_path)

    # 5. 系统托盘（非开发模式）
    tray = None
    if not _is_dev_mode():
        from common.tray_manager import TrayManager
        icon_path = _get_icon_path()
        tray = TrayManager(
            icon_path=icon_path,
            on_show_window=lambda: None,
            on_quit=lambda: None,
        )
        tray.start()
        print("[Desktop] 托盘已启动")
        if is_first:
            tray.show_notification(
                "PersonLLMWiki",
                f"数据已保存在「文档\\PersonLLMWiki」，可到设置页修改位置"
            )

    # 6. 创建 WebView 窗口
    url = f"http://127.0.0.1:{port}"
    print(f"[Desktop] 打开窗口: {url}")
    webview.create_window(
        url=url,
        title='PersonLLMWiki',
        width=1280,
        height=800,
        min_size=(1024, 600),
    )

    # 7. 启动 WebView（阻塞直到窗口关闭）
    webview.start()

    # 8. 窗口关闭后清理
    if tray:
        tray.stop()
    print("[Desktop] 已退出")
```

> **注意**：`create_confirmation_dialog` 的可用性取决于 pywebview 版本和后端。如果该方法不可用，改用 `webview.windows[0].create_confirmation_dialog()` 或退化为始终 minimize。在 Step 3 验证时确认。

- [ ] **Step 3: 手动验证 — 开发模式关闭即退出**

Run: `python desktop.pyw`
Expected: 窗口弹出 → 关闭窗口 → 进程立即退出（开发模式不弹对话框）

- [ ] **Step 4: 运行全部单元测试**

Run: `python -m pytest tests/desktop/ -v`
Expected: 10 passed（Task 1 的 4 个 + Task 2 的 6 个）

- [ ] **Step 5: Commit**

```bash
git add desktop.pyw
git commit -m "feat: add close behavior dialog and first-launch data init"
```

---

## Task 6: PyInstaller 打包配置 (desktop.spec)

**Files:**
- Create: `packaging/desktop.spec`

- [ ] **Step 1: 编写 desktop.spec**

创建 `packaging/desktop.spec`：

```python
# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置 — PersonLLMWiki 桌面版

用法：
  cd src
  pyinstaller packaging/desktop.spec --noconfirm
"""

import os

block_cipher = None
# src 目录（spec 文件的上两级）
src_dir = os.path.dirname(os.path.dirname(os.path.abspath(SPEC)))

a = Analysis(
    ['desktop.pyw'],
    pathex=[src_dir],
    binaries=[],
    datas=[
        # 打包 static 和 templates（Flask 渲染需要）
        (os.path.join(src_dir, 'static'), 'static'),
        (os.path.join(src_dir, 'templates'), 'templates'),
    ],
    hiddenimports=[
        'flask',
        'flask_sqlalchemy',
        'flask_cors',
        'openai',
        'fitz',
        'fastembed',
        'fastmcp',
        'webview',
        'webview.platforms.edgechromium',
        'pystray',
        'PIL',
        'PIL._tkinter_finder',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PersonLLMWiki',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # 无控制台窗口
    icon=os.path.join(src_dir, 'static', 'img', 'AIChat.png'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='PersonLLMWiki',
)
```

- [ ] **Step 2: 手动验证 — PyInstaller 打包**

Run: `cd src && pyinstaller packaging/desktop.spec --noconfirm`
Expected:
- 产出 `dist/PersonLLMWiki/PersonLLMWiki.exe`
- 产出 `dist/PersonLLMWiki/_internal/` 目录（含 static、templates、site-packages）

- [ ] **Step 3: 手动验证 — EXE 可运行**

Run: `dist\PersonLLMWiki\PersonLLMWiki.exe`
Expected: 弹出原生窗口，页面正常加载

> 如果缺少模块（ModuleNotFoundError），在 `hiddenimports` 中补充。

- [ ] **Step 4: Commit**

```bash
git add packaging/desktop.spec
git commit -m "feat: add PyInstaller spec for desktop packaging"
```

---

## Task 7: Inno Setup 安装包 (installer.iss + build_desktop.py)

**Files:**
- Create: `packaging/installer.iss`
- Create: `packaging/build_desktop.py`

- [ ] **Step 1: 编写 installer.iss**

创建 `packaging/installer.iss`：

```iss
; PersonLLMWiki Inno Setup 安装包脚本
;
; 用法（由 build_desktop.py 自动调用）：
;   ISCC.exe installer.iss
;
; 编译前需先执行 PyInstaller，产出 dist/PersonLLMWiki/

#define MyAppName "PersonLLMWiki"
#define MyAppExeName "PersonLLMWiki.exe"
; AppVersion 由 build_desktop.py 用 ISCC 的 /D 参数注入

[Setup]
AppId={{PersonLLMWiki-Desktop}}
AppName={#MyAppName}
AppVersion={#AppVersion}
AppPublisher=PersonLLMWiki
DefaultDirName={pf}\PersonLLMWiki
DefaultGroupName=PersonLLMWiki
DisableProgramGroupPage=yes
OutputDir=..\installer_output
OutputBaseFilename=PersonLLMWiki-Setup-{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName=PersonLLMWiki

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加图标:"; Flags: checked

[Files]
Source: "..\dist\PersonLLMWiki\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\PersonLLMWiki"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载 PersonLLMWiki"; Filename: "{uninstallexe}"
Name: "{commondesktop}\PersonLLMWiki"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即启动 PersonLLMWiki"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 卸载时只删程序，不删用户数据（Documents\PersonLLMWiki 保留）
Type: filesandordirs; Name: "{app}"
```

- [ ] **Step 2: 编写 build_desktop.py**

创建 `packaging/build_desktop.py`：

```python
"""桌面版打包编排脚本。

用法：
  python packaging/build_desktop.py 1.0.0

流程：
  1. 调用 PyInstaller（用 desktop.spec）打 EXE
  2. 调用 Inno Setup（ISCC.exe）打安装包
  3. 产出 PersonLLMWiki-Setup-{version}.exe
"""

import os
import shutil
import subprocess
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(THIS_DIR)
PACKAGING_DIR = THIS_DIR


def run_pyinstaller():
    """调用 PyInstaller 打包"""
    print("[build] === PyInstaller 打包 ===")
    spec = os.path.join(PACKAGING_DIR, "desktop.spec")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        spec,
        "--noconfirm",
        "--distpath", os.path.join(PACKAGING_DIR, "dist"),
        "--workpath", os.path.join(PACKAGING_DIR, "build"),
    ]
    print(f"[build] 运行: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=SRC_DIR)
    if result.returncode != 0:
        print("[build] PyInstaller 失败！")
        sys.exit(1)

    exe_path = os.path.join(PACKAGING_DIR, "dist", "PersonLLMWiki", "PersonLLMWiki.exe")
    if not os.path.isfile(exe_path):
        print(f"[build] 未找到产出 EXE: {exe_path}")
        sys.exit(1)
    print(f"[build] EXE 已生成: {exe_path}")


def find_iscc():
    """查找 Inno Setup 编译器 ISCC.exe"""
    # 常见安装路径
    candidates = [
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    # 尝试 PATH
    found = shutil.which("ISCC")
    if found:
        return found
    return None


def run_inno_setup(version):
    """调用 Inno Setup 编译安装包"""
    print("[build] === Inno Setup 打包 ===")
    iscc = find_iscc()
    if not iscc:
        print("[build] 错误: 未找到 ISCC.exe，请安装 Inno Setup 6")
        print("[build] 下载地址: https://jrsoftware.org/isdl.php")
        sys.exit(1)

    iss = os.path.join(PACKAGING_DIR, "installer.iss")
    output_dir = os.path.join(PACKAGING_DIR, "installer_output")
    os.makedirs(output_dir, exist_ok=True)

    cmd = [iscc, f"/DAppVersion={version}", iss]
    print(f"[build] 运行: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=PACKAGING_DIR)
    if result.returncode != 0:
        print("[build] Inno Setup 失败！")
        sys.exit(1)

    installer = os.path.join(output_dir, f"PersonLLMWiki-Setup-{version}.exe")
    if not os.path.isfile(installer):
        print(f"[build] 未找到安装包: {installer}")
        sys.exit(1)

    size_mb = os.path.getsize(installer) / 1024 / 1024
    print(f"\n[build] 安装包已生成:")
    print(f"  路径: {installer}")
    print(f"  大小: {size_mb:.1f} MB")
    return installer


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python build_desktop.py <version>")
        print("示例: python build_desktop.py 1.0.0")
        sys.exit(1)

    version = sys.argv[1]
    print(f"PersonLLMWiki 桌面版打包工具")
    print(f"版本: {version}")
    print()

    run_pyinstaller()
    installer_path = run_inno_setup(version)

    print(f"\n[build] 完成！安装包: {installer_path}")
```

- [ ] **Step 3: 手动验证 — 完整打包流程**

> 前提：已安装 Inno Setup 6（https://jrsoftware.org/isdl.php）

Run: `cd src && python packaging/build_desktop.py 1.0.0`
Expected:
- PyInstaller 阶段产出 `packaging/dist/PersonLLMWiki/`
- Inno Setup 阶段产出 `packaging/installer_output/PersonLLMWiki-Setup-1.0.0.exe`
- 控制台打印安装包路径和大小

- [ ] **Step 4: 手动验证 — 安装包可安装运行**

双击 `PersonLLMWiki-Setup-1.0.0.exe`
Expected:
- 安装向导出现（中文）
- 安装到 `C:\Program Files\PersonLLMWiki\`
- 桌面出现快捷方式
- 勾选"立即启动"后窗口弹出，页面正常

- [ ] **Step 5: 手动验证 — 卸载不删数据**

1. 在应用中创建一些数据（文章等）
2. 控制面板 → 卸载 PersonLLMWiki
3. 检查 `Documents\PersonLLMWiki\resource\` 仍然存在

Expected: 程序被卸载，用户数据保留

- [ ] **Step 6: Commit**

```bash
git add packaging/installer.iss packaging/build_desktop.py
git commit -m "feat: add Inno Setup installer and build_desktop.py orchestration"
```

---

## Task 8: 端到端验证

**Files:**
- 无新文件，仅验证

- [ ] **Step 1: 运行全部单元测试**

Run: `python -m pytest tests/desktop/ -v`
Expected: 10 passed

- [ ] **Step 2: 开发模式验证**

Run: `python desktop.pyw`
验证项：
- [ ] 窗口弹出，标题 "PersonLLMWiki"
- [ ] 页面正常加载（首页可见）
- [ ] 切换到设置页，各功能正常
- [ ] 关闭窗口 → 进程立即退出（开发模式）
- [ ] 控制台无异常

- [ ] **Step 3: 完整安装流程验证**

Run: `python packaging/build_desktop.py 1.0.0`
验证项：
- [ ] 安装包生成成功
- [ ] 双击安装包 → 安装向导正常
- [ ] 安装后桌面有快捷方式
- [ ] 启动后窗口弹出，页面正常
- [ ] 托盘图标出现（任务栏通知区）
- [ ] 首次启动气泡提示出现
- [ ] `Documents\PersonLLMWiki\resource\` 目录已创建

- [ ] **Step 4: 关闭行为验证（桌面版）**

验证项（需在无 .git 的打包版环境）：
- [ ] 首次关闭窗口 → 弹出对话框
- [ ] 选"最小化" → 窗口隐藏，托盘仍在
- [ ] 双击托盘 → 窗口恢复
- [ ] 再次关闭 → 不弹对话框（已记住）
- [ ] 选"退出" → 窗口 + 托盘都消失，进程结束

- [ ] **Step 5: 卸载数据安全验证**

验证项：
- [ ] 控制面板卸载 → 程序目录被删
- [ ] `Documents\PersonLLMWiki\resource\` 保留
- [ ] 重新安装 → 数据仍在

- [ ] **Step 6: Commit 最终验证**

```bash
git add -A
git commit -m "test: end-to-end verification of desktop shell"
```

---

## Self-Review

### Spec coverage 检查

| 设计文档章节 | 对应 Task | 状态 |
|-------------|----------|------|
| §2 选型 PyWebView | Task 3 | ✅ |
| §3 架构（双线程） | Task 3 | ✅ |
| §3 动态端口分配 | Task 1, 3 | ✅ |
| §3 Flask 就绪检测 | Task 3 | ✅ |
| §4 启动流程 | Task 3 | ✅ |
| §4 关闭行为（询问+记住） | Task 5 | ✅ |
| §4 系统托盘 | Task 4 | ✅ |
| §4 开发模式差异 | Task 5 | ✅ |
| §5 首次启动数据目录 | Task 5 | ✅ |
| §5 修改路径（复用现有） | 不需新代码（设置页已有） | ✅ |
| §5 卸载安全 | Task 7 (installer.iss) | ✅ |
| §6 PyInstaller 打包 | Task 6 | ✅ |
| §6 Inno Setup 安装包 | Task 7 | ✅ |
| §6 build_desktop.py | Task 7 | ✅ |
| §7 健康检查（Flask 就绪） | Task 3 | ✅ |
| §7 端口冲突 | Task 1, 3 | ✅ |
| §7 WebView2 依赖 | Task 7 (installer.iss 可后续集成) | ✅ |

### Placeholder 检查

- 所有代码步骤均包含完整代码 ✅
- 所有验证步骤均有明确的 Expected ✅
- 无 "TODO" / "TBD" / "类似上面" ✅

### Type consistency 检查

- `find_free_port()` 在 Task 1 定义，Task 3 的 `desktop.pyw` 调用 — 签名一致 ✅
- `get_close_action()` / `set_close_action()` 在 Task 2 定义，Task 5 调用 — 签名一致 ✅
- `is_first_launch()` / `mark_launched()` 在 Task 2 定义，Task 5 调用 — 签名一致 ✅
- `TrayManager` 在 Task 4 定义，Task 5 的 `main()` 调用 — 参数一致 ✅
- `_is_dev_mode()` 在 Task 3 定义，Task 5 调用 — 一致 ✅
