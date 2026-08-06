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
                default=True,  # 左键单击触发
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
