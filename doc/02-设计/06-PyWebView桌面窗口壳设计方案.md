# PyWebView 桌面窗口壳 设计文档

> 日期：2026-08-06
> 状态：待批准
> 目标：把 PersonLLMWiki（Flask Web 应用）封装为原生窗口桌面软件，产出 `.exe` 安装包，分发给非技术用户。

---

## 1. 背景与目标

### 现状

PersonLLMWiki 是一个 Flask Web 应用，目前：
- 开发时：用 `dev.ps1` 启动 conda Flask 环境，浏览器访问 `http://127.0.0.1:5000`。
- 打包时：`build_release.py` 产出 zip 包（含嵌入式 Python runtime + app 代码），用户解压后双击 `启动.bat`，通过浏览器使用。

已有能力：嵌入式 Python runtime（`fetch_runtime.py`）、全量/增量打包（`build_release.py`）、`.bat` 启动脚本（环境自检、依赖修复、桌面快捷方式）、embedded 模式识别、在线升级接口。

### 问题

分发形态是「zip + .bat + 浏览器」，对非技术用户不够友好：需要解压、看不到原生窗口、任务栏是浏览器图标、关闭浏览器标签页不会停后台服务。

### 目标

- 最终产物是 `.exe` 安装包（Inno Setup），非技术用户双击安装、开始菜单/桌面快捷方式启动。
- 启动后是原生窗口（系统 WebView），不再是浏览器标签页。
- 开发时也能用原生窗口调试（`python desktop.pyw`）。
- 不重写现有代码，只加一层「壳」。

---

## 2. 选型：PyWebView

| 维度 | PyWebView（选定） | FlaskWebGUI/Eel | Tauri (Rust) |
|------|------------------|-----------------|--------------|
| 改动量 | 新增 1 入口文件 | 新增 1 入口文件 | 跨语言重写 |
| 技术栈 | 纯 Python | 纯 Python | Python + Rust |
| 体验 | 原生窗口（系统 WebView2） | Chrome App Mode（有浏览器痕迹） | 原生窗口 |
| 体积增量 | ~3MB（用系统 WebView） | 依赖用户已装 Chrome | ~10MB 壳 |
| 维护 | 单技术栈，低 | 低 | 双技术栈，高 |

**选 PyWebView**：纯 Python、改动最小、原生体验、体积可控。

---

## 3. 架构

### 进程模型：单进程双线程

```
desktop.pyw (主入口)
│
├── Thread 1: Flask 后端 (后台线程)
│   └── app.run(host='127.0.0.1', port=动态分配)
│        ├── 所有现有 API 路由
│        ├── MCP 服务
│        ├── Scheduler 定时任务
│        └── SQLite + 文件系统
│
└── Thread 2 (主线程): PyWebView 窗口
    └── webview.create_window(url='http://127.0.0.1:{port}')
         └── 系统 WebView2 渲染界面
```

### 设计原则

1. **不改 app.py** — Flask 入口保持不变，浏览器仍能直接访问。`desktop.pyw` 是额外的壳入口，通过 import 引用 Flask app。
2. **动态端口分配** — 启动时找空闲端口，避免 5000 被占用时冲突。
3. **单入口双模式** — 同一个 `desktop.pyw`，开发时 `python desktop.pyw` 弹窗口；打包后双击 EXE 同样弹窗口。

### 新增文件

| 文件 | 职责 | 行数估计 |
|------|------|---------|
| `src/desktop.pyw` | 桌面入口：启动 Flask 线程 + 创建 WebView 窗口 + 系统托盘 | ~120 |
| `src/common/tray_manager.py` | 托盘图标逻辑（显示/退出/记住选择） | ~80 |
| `src/packaging/build_desktop.py` | 桌面版打包脚本（调用 PyInstaller + Inno Setup） | ~80 |
| `src/packaging/desktop.spec` | PyInstaller 打包配置 | ~60 |
| `src/packaging/installer.iss` | Inno Setup 安装包脚本 | ~80 |

### 不修改的文件

`app.py`、`config.py`、`extensions.py`、`modules/**`、`common/**`（除新增 `tray_manager.py`）、`static/**`、`templates/**`。

---

## 4. 窗口与托盘行为

### 启动流程

```
用户启动 PersonLLMWiki.exe
│
├─ 启动 Flask 后端线程（等就绪 /api 返回 200）
├─ 创建系统托盘图标（AIChat.png）
├─ 创建 PyWebView 主窗口（1280×800，最小 1024×600）
│    └── 标题: "PersonLLMWiki"
│    └── 加载 http://127.0.0.1:{port}
```

### 关闭行为：询问后记住

```
用户点窗口关闭按钮 (×)
│
├─ 读取 resource/instance/window_pref.json
│
├─ 无记录（首次）
│   └─ 弹对话框：
│        ┌──────────────────────────────────┐
│        │ 关闭窗口后：                      │
│        │  ○ 最小化到托盘，保持运行        │
│        │  ● 完全退出程序                   │
│        │  ☑ 记住选择（下次不再询问）       │
│        │         [确定]  [取消]            │
│        └──────────────────────────────────┘
│   └─ 选"取消" → 不关闭，返回窗口
│   └─ 选"最小化" → 隐藏窗口 + 托盘气泡提示
│   └─ 选"退出" → 停 Flask + 移除托盘 + 退出
│   └─ 记住选择写入 window_pref.json
│
└─ 有记录（非首次）
    └─ 直接执行记录的动作（最小化 or 退出）
```

### 记住选择存储

```json
// {RESOURCE_BASE_PATH}/instance/window_pref.json
{
  "close_action": "minimize"
}
```
取值：`"minimize"`（最小化到托盘）或 `"exit"`（完全退出）。

### 系统托盘

- 图标：`app/static/img/AIChat.png`
- 双击托盘图标：显示/聚焦主窗口。
- 右键菜单：「显示主窗口」/ 分隔线 /「退出」。
- 最小化时气泡提示：「PersonLLMWiki 正在后台运行」。

### 开发模式差异

开发模式（`_is_dev_mode()` 为 true，即存在 `.git` 目录）下：
- 关闭窗口 = 直接退出（不弹询问、不缩托盘），方便快速重启调试。

---

## 5. 数据目录策略

### 首次启动

桌面版首次运行，检测 `.env` 不存在或 `RESOURCE_BASE_PATH` 为空时：

1. 在用户文档目录创建：`C:\Users\{user}\Documents\PersonLLMWiki\resource\`（及子目录 article/img/attachments/wiki/instance）。
2. 在 `Documents\PersonLLMWiki\.env` 写入 `RESOURCE_BASE_PATH=<上述路径>`。
3. 托盘气泡提示：「数据已保存在「文档\PersonLLMWiki」，可到设置页修改位置」。

### 修改路径（两种方式，复用现有机制）

- **设置页改**：`/settings` →「路径设置」→ 保存。后端 `POST /api/settings/path` 写 `.env` + 创建新目录。已有功能，不改。
- **手动改 .env**：直接编辑 `Documents\PersonLLMWiki\.env` 的 `RESOURCE_BASE_PATH`。

### 卸载安全

- 程序装在 `C:\Program Files\PersonLLMWiki\`，数据装在 `Documents\PersonLLMWiki\`。
- 卸载只删 Program Files，数据保留。升级安装不覆盖数据。

---

## 6. 打包流程

### 两阶段构建

```
阶段 1: PyInstaller（打 EXE）
━━━━━━━━━━━━━━━━━━━━━━━━━━
desktop.pyw + app/ + runtime/
  ──→ dist/PersonLLMWiki/PersonLLMWiki.exe
        ├── PersonLLMWiki.exe  (入口)
        ├── _internal/          (PyInstaller 依赖)
        │   ├── app/            (全部源码)
        │   └── site-packages
        └── resource/           (空，首次运行创建)

阶段 2: Inno Setup（做安装包）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
dist/PersonLLMWiki/
  ──→ PersonLLMWiki-Setup-1.0.0.exe
        ├── 安装到 C:\Program Files\PersonLLMWiki\
        ├── 开始菜单快捷方式
        ├── 桌面快捷方式
        ├── 安装完可选启动
        └── 带卸载入口
```

### 与现有 build_release.py 并存

- `build_release.py`（zip 包）→ 开发者 / 内测用户
- `build_desktop.py`（安装包）→ 最终非技术用户

两种分发形态对比：

| 维度 | zip 包（build_release.py） | 安装包（build_desktop.py） |
|------|---------------------------|--------------------------|
| 分发物 | PersonLLMWiki-v1.0.zip | PersonLLMWiki-Setup-1.0.exe |
| 安装方式 | 手动解压 | 双击安装向导 |
| 启动方式 | 双击 .bat → 浏览器 | 双击快捷方式 → 原生窗口 |
| 数据位置 | zip 解压目录/resource | Documents/PersonLLMWiki/resource |
| 卸载 | 删文件夹 | 控制面板卸载（数据保留） |
| 适用人群 | 开发者 / 内测 | 最终非技术用户 |

### build_desktop.py 流程

```python
# 用法: python build_desktop.py 1.0.0

def build_desktop(version):
    # 1. 准备资源（确保 runtime 已构建）
    # 2. 调用 PyInstaller（用 desktop.spec 配置）
    #    pyinstaller desktop.spec --noconfirm
    # 3. 清理 PyInstaller 临时文件
    # 4. 调用 Inno Setup 编译器
    #    ISCC installer.iss
    # 5. 产出: dist/PersonLLMWiki-Setup-{version}.exe
    # 6. 统计大小
```

### Inno Setup 配置要点（installer.iss）

| 配置项 | 值 |
|--------|-----|
| AppName | PersonLLMWiki |
| AppVersion | {version} |
| DefaultDirName | {pf}\PersonLLMWiki |
| DefaultGroupName | PersonLLMWiki |
| DesktopIcon | yes |
| RunOnFinish | PersonLLMWiki.exe（可选启动） |
| Uninstallable | yes |
| PrivilegesRequired | admin |
| Compression | lzma（最大压缩） |

### 版本管理与升级

| 场景 | 方案 |
|------|------|
| 全量安装 | 下载新 `PersonLLMWiki-Setup-1.1.0.exe`，直接安装覆盖（数据在 Documents 不受影响） |
| 增量更新 | 现有 `/api/settings/upgrade/check` + `build_release.py --update` 机制保留，桌面版也可用 |

### 体积预估

| 组件 | 大小 |
|------|------|
| Python Embedded + 依赖 | ~90 MB |
| PyWebView + WebView2Loader | ~3 MB |
| app 源码 + static | ~5 MB |
| PyInstaller 开销 | ~10 MB |
| **安装包压缩后** | **~80-100 MB** |

---

## 7. 健康检查与错误处理

### Flask 就绪检测

`desktop.pyw` 启动 Flask 线程后，轮询 `http://127.0.0.1:{port}/api` 直到返回 200 或超时（10 秒）。
超时则弹原生错误对话框：「服务启动失败，请检查日志」并退出。

### 端口冲突

动态端口分配：尝试 5000-5100 范围找空闲端口。若全被占用，报错退出。

### WebView2 依赖

Windows 10+ 默认含 WebView2 Runtime。Win7/8 需引导安装 Evergreen Bootstrapper（Inno Setup 可集成检查）。

---

## 8. 不做的事（YAGNI）

- 不做「首次使用向导」（设置页已够用）。
- 不做自动更新安装包本身（用户手动下载新版安装包；增量代码更新走现有升级接口）。
- 不做 macOS/Linux 桌面版（当前只面向 Windows 用户）。
- 不做多窗口/标签页。
- ~~不做自定义标题栏（用系统默认标题栏）~~ → **已被 F4（单栏无边框）推翻，见 §9**。

---

## 9. 演进：单栏无边框窗口（F4，2026-08-24 决定本次实施）

**目标**：去掉系统标题栏，SPA 顶栏升级为窗口标题栏——**顶部只有一条栏**：
`[Wiki | DSH 开关] [状态点] ────────── [—][□][✕]`（窗口控制按钮右对齐）。

### 9.1 依据（pywebview 6.2.1 源码实测）

| 事实 | 结论 |
|---|---|
| `frameless=True` → WinForms `FormBorderStyle.None` | 无标题栏；**无边缘拖拽缩放**（已知限制） |
| `easy_drag` 未在 WinForms 后端实现（仅 cocoa/gtk/qt/mshtml） | **拖拽必须自实现**（不能靠 easy_drag） |
| JS 侧 `window.pywebview` 仅暴露 `api` 桥（无 minimize/maximize/destroy 直调） | **窗口控制全部走 `js_api`** |
| Python 侧 `Window.minimize() / maximize() / restore()` 可用 | 按钮直接映射这些方法 |
| `desktop.pyw` 已有 Win32 子类化 `_wndproc`（WM_CLOSE→隐藏托盘）、`_hwnd`、ctypes user32 | 拖拽/关闭按钮复用现有基建，无需另起炉灶 |

### 9.2 实现清单（Trae）

**A. `src/desktop.pyw`**

1. `webview.create_window(..., frameless=True)`——保留 `title='PersonLLMWiki'`（托盘/单实例 FindWindowW 依赖）、`width/height/min_size`、`shadow` 默认（圆角）。
2. 新增 `WindowApi` 类，经 `js_api=WindowApi()` 注入；`create_window` 返回后把 `Window` 引用赋给 Api。方法：
   - `minimize()` → `window.minimize()`
   - `toggle_maximize()` → `user32.IsZoomed(_hwnd[0])` 为真则 `window.restore()`，否则 `window.maximize()`
   - `is_maximized()` → `bool(user32.IsZoomed(_hwnd[0]))`（按钮图标初始化）
   - `close()` → `user32.PostMessageW(_hwnd[0], WM_CLOSE, 0, 0)`——**走既有 `_wndproc`**：非退出态隐藏到托盘，语义与系统 ✕ 一致
   - `start_drag()` → `user32.ReleaseCapture()` + `user32.SendMessageW(_hwnd[0], WM_NCLBUTTONDOWN, HTCAPTION, 0)`——经典无边框拖拽；最大化状态下拖拽自动还原为普通拖拽（Windows 原生行为，无需特判）
   - 新增常量：`WM_NCLBUTTONDOWN = 0x00A1`、`HTCAPTION = 2`；补 `user32.ReleaseCapture` / `user32.IsZoomed` 的 argtypes/restype 声明（与现有 64 位兼容风格一致）。
3. **（建议一并，低成本）边缘缩放**：`_wndproc` 中处理 `WM_NCHITTEST = 0x0084`——光标落在窗口边缘 6px 带内时返回 `HTLEFT/HTRIGHT/HTTOP/HTBOTTOM/HTTOPLEFT/HTTOPRIGHT/HTBOTTOMLEFT/HTBOTTOMRIGHT`，其余交原过程。弥补 frameless 无边缘缩放；与 JS 拖拽区（仅顶栏内）互不冲突。若实现有风险可先跳过，窗口仍可用最大化/还原。

**B. `src/templates/base.html`（SPA 顶栏，唯一可见栏）**

1. 顶栏右侧新增窗口控制区：`—`（最小化）、`□/❐`（最大化/还原，按 `is_maximized()` 切换图标）、`✕`（关闭，hover 红 `#e81123`）。按钮 `user-select:none`。
2. 拖拽：顶栏空白区（非按钮/开关/状态区）`mousedown` → `start_drag()`；`dblclick` → `toggle_maximize()`；按钮与开关区 `stopPropagation()` 防误触。
3. JS 桥：**`window.parent.pywebview.api.*`**（pywebview 注入在 shell 顶层窗口；同源 iframe 可访问），兜底 `(window.pywebview || window.parent.pywebview)?.api`；Web 模式（无 shell 父窗口）顶栏本就不显示，天然安全。
4. 最大化图标状态：点击后乐观切换；启动时调 `is_maximized()` 初始化。
5. 高度不变，按钮区 ≈46px 宽，hover 背景色与现有顶栏风格一致。

### 9.3 验证路径

1. 开发验证：`flask\python.exe src/desktop.pyw`（pywebview 6.2.1 已装 flask 环境）→ 单栏观感 / 顶栏拖拽 / 双击最大化 / 三按钮 / 关闭→托盘 / 托盘恢复·退出 / DSH 模式切换（Wiki↔DSH、←返回）全部正常。
2. 打包复验：构建 .004 后按任务书 2.5 复验，2.5.2 更新为「单栏含窗口控制按钮、无系统标题栏」。

### 9.4 已知限制

- ~~frameless 无边缘拖拽缩放~~ → 已由 §12 覆盖条 + `SetWindowPos` 方案解决（2026-08-24 R4 实测通过）；
- 最大化/还原无系统过渡动画（WinForms `FormBorderStyle.None` 特性，可接受）；
- 窗口控制按钮在 Web 浏览器模式不可见/隐藏（无 pywebview 桥时静默降级），属预期。

---

## 10. R2 修订：持久顶栏 + 原生 NCHITTEST（2026-08-24 GUI 实测后）

§9 方案实装后开发壳 GUI 实测，发现 5 个问题，本修订全部重做相关部分。

### 10.1 实测问题与根因

| # | 现象 | 根因 |
|---|---|---|
| R2-1 | 顶栏**不能拖动** | JS→`WM_NCLBUTTONDOWN(HTCAPTION)` 技巧在 pywebview+WebView2 组合下不可靠（桥线程与消息泵时序）。**放弃合成消息方案** |
| R2-2 | **边缘缩放无效** | WebView2 子窗口铺满整个客户区，`WM_NCHITTEST` 由子窗口自行应答（返回 HTCLIENT），**父 Form 永远收不到该消息**——父窗口子类里的边缘 HT* 逻辑永不触发 |
| R2-3 | 切到 DSH 模式**顶栏消失** | 顶栏放在 app iframe（base.html）内，DSH 模式隐藏该 iframe → frameless 窗口在 DSH 模式**没有任何标题栏/窗口按钮** |
| R2-4 | 少 logo、Wiki\|DSH 开关不在左边 | 顶栏应像系统标题栏：左侧 logo+开关，右侧窗口按钮 |
| R2-5 | — □ ✕ 按钮 UI 不对 | 文本字形 + 无 Windows 观感 → 改 SVG 图标 + Win11 风格悬停 |

### 10.2 R2 方案

1. **持久顶栏搬回 shell 层（shell.html）**：`.shell-bar` 置于 `.shell-stage` 上方，Wiki/DSH **两种模式都常驻**（内容始终在栏下方，即"自绘系统标题栏"）。
   - `base.html`、`layout.css` **回退到 f1a5a25^ 状态**（`git checkout f1a5a25^ -- src/templates/base.html src/static/css/layout.css`）——app 内不再有顶栏；
   - shell.html 删除 `.shell-float`（栏上开关即返回入口）；`<span class="brand">PersonLLMWiki</span>` 与 `appicon.svg`（20px）作左端品牌。
2. **原生命中测试（一次解决拖动+缩放）**：子类化 **WebView2 子窗口**（`EnumChildWindows` 找 `Chrome_WidgetWin_*`，兜底取面积≈客户区的最大子窗口），在其 `WM_NCHITTEST` 中：
   - 边缘 6px 带 → 返回 8 个 `HT*` 方向码（`IsZoomed` 时跳过）；
   - 光标 y < 栏高（设备像素，JS 上报）**且**不在交互排除矩形内 → 返回 **`HTCAPTION`**（原生拖动 + 原生双击最大化 + 最大化时拖拽自动还原，全免费）；
   - 其余 → `HTCLIENT`。
   - 交互排除矩形：shell JS 在加载/`ResizeObserver` 时经 js_api 上报 `set_drag_exclusions([[x,y,w,h],...])`（设备像素，相对窗口客户区 = 栏的 `getBoundingClientRect()` × `devicePixelRatio`）。
   - 父窗口 `_wndproc` 移除 WM_NCHITTEST/边缘逻辑（无效冗余），保留 WM_CLOSE→托盘。
3. **窗口按钮（栏右侧）**：内联 SVG 图标（minimize=横线、maximize=方框、restore=双框、close=✕），46px 宽 × 栏高，hover 背景、close hover `#e81123` 白字；**图标状态**由 Python `window.events.maximized / restored` 回调 → `window.evaluate_js(...)` 推送刷新（覆盖原生双击最大化等非 JS 入口）。
4. **栏布局**：`[appicon.svg + PersonLLMWiki] [Wiki|DSH 开关] [DSH 状态点] ──── [— □ ✕]`，高 40px，白底 + 底边线，仿系统标题栏；开关/状态点样式沿用 base.html 中被回退的 `.dsh-seg / .dsh-status-badge`（迁入 shell.html 的 `<style>`）。
5. **保留全部既有行为**：localStorage 模式记忆、双 iframe 懒加载与 display 切换、状态轮询（2s×3 → 10s）、starting 文案、未装/版本低遮罩与「启动 DSH」、键盘快捷键、托盘 `__shellToggleMode`、message 监听（base.html 移除顶栏后不再发 `dsh-switch`，可保留监听以兼容）。

### 10.3 desktop.pyw 改动清单（Trae）

- `WindowApi`：移除 `start_drag()`；保留 `minimize / toggle_maximize / is_maximized / close`；**新增 `set_drag_exclusions(rects)`**（Python 侧存列表，供 NCHITTEST 用）。
- `_install_hook` 扩展：`EnumChildWindows` 找 WebView2 子窗口 → 用现有 `SetWindowLongPtrW` 机制子类化（同一 `_wndproc` 内按 hwnd 分流，或第二个 WNDPROC）。
- 子窗口 `WM_NCHITTEST`：`GetCursorPos` + `ScreenToClient` → 边缘 HT* / 栏区 HTCAPTION（排除矩形内 HTCLIENT）/ 其余 HTCLIENT。
- `window.events.maximized/restored` → `evaluate_js` 通知 shell 刷新图标（`window.__setWinState(max)`）。
- 常量/API 补充：`EnumChildWindows`（回调签名）、`GetCursorPos`、`ScreenToClient`、`HTCLIENT=1` 等，argtypes/restype 沿用 64 位声明风格。
- 父窗口 `_wndproc`：删 WM_NCHITTEST/`_edge_hit_test`，只留 WM_CLOSE。

### 10.4 Fallback（若子窗口子类化不生效）

1. 拖动：JS mousedown → `SendMessage(WM_SYSCOMMAND, SC_MOVE|HTCAPTION(0xF012), 0)`（WinForms 无边框经典方案）；
2. 缩放：JS 边缘 6px 透明条 mousedown → Python 循环 `SetWindowPos` 跟随 `GetCursorPos` 直至鼠标松开。
3. 若两者均失败：回退为**保留系统标题栏**（去掉 frameless），接受双栏（与 F4 目标冲突，仅作底线）。

### 10.5 验证路径

1. 开发壳（`flask\python.exe src/desktop.pyw`）：单栏常驻（Wiki/DSH 模式都在）、logo+开关在左、SVG 三按钮、**拖动/双击最大化/边缘缩放**全部原生生效、✕ 到托盘、DSH 切换正常、启动 DSH 无 cmd 框；
2. .004 构建后按任务书 2.5 复验。

---

## 11. R3 修订：实测根因与确定性实现（2026-08-24 R2 GUI 实测后）

R2 实装后 GUI 实测：拖动 ✅、单栏外观 ✅、DSH 切换 ✅、F1 无 cmd 框 ✅；**边缘缩放 ❌、双击最大化 ❌、✕ 后无托盘图标 ❌、http://localhost:5000 无法访问 ❌**。

### 11.1 根因

| 现象 | 根因 |
|---|---|
| 边缘缩放/双击无效（拖动却正常） | ① **pywebview frameless 默认启用 `easy_drag`**（`customize.js` 给整个窗口挂 mousedown → `pywebviewMoveWindow` 增量移动），与自绘机制并存干扰；② 边缘 HT* 与标题栏双击依赖 Chromium/WebView2 对非客户区消息的传导，实测不可靠。**放弃依赖，改确定性 JS 实现** |
| ✕ 后进程在跑但**无托盘图标** | 开发环境 flask env **缺 pystray**：`TrayManager._run()` 内 `import pystray` 失败，daemon 线程静默死亡；EXE 打包了 pystray 所以安装版正常（属开发环境问题，已装修复） |
| `localhost:5000` 无法访问 | 5000 被占时顺延到 5001 并**持久化**（`~/.personllmwiki/instance/desktop_prefs.json` 的 `flask_port`），之后每次启动读 5001——5000 已空也不回弹（属使用问题，已重置回 5000） |

### 11.2 R3 改动清单（Trae）

**A. `src/desktop.pyw`**
1. `webview.create_window(...)` 增加 **`easy_drag=False`**——关闭 pywebview 自带 JS 拖拽劫持。
2. 子窗口 `WM_NCHITTEST`：**只保留栏区 `HTCAPTION`**（拖动已实测原生生效）；**移除边缘 HT\* 分支**（与 JS 边缘缩放冲突且不可靠）。
3. `WindowApi` 新增 **`start_resize(dir)`**：`dir ∈ n/s/e/w/ne/nw/se/sw`。后台线程循环：`GetCursorPos` → 按方向锚定对边/对角计算新 rect（**强制 min 1024×600**）→ `SetWindowPos(hwnd, ..., SWP_NOZORDER|SWP_NOACTIVATE)` → 直到 `GetAsyncKeyState(VK_LBUTTON)` 松开。
4. （可选）`TrayManager._run` 包 try/except + 打印失败原因，便于将来排查。

**B. `src/modules/agent/templates/shell.html`**
1. **双击最大化**：栏上 `dblclick`（target 不在交互区）→ `api.toggle_maximize()`；交互区 `stopPropagation`。
2. **边缘缩放**：`document` 级 `mousemove` 检测距视口边缘 ≤8 CSS px → 设置对应 resize 光标并记录方向；边缘带内 `mousedown` → `api.start_resize(dir)` + `preventDefault()`。
3. **Web 模式降级**：无 `window.pywebview.api` 时**隐藏窗口按钮区**（浏览器直连更干净、不报错）。

**C. 环境（已处理）**：flask env 已装 pystray 0.19.5；`desktop_prefs.json` 的 `flask_port` 已重置回 5000。

### 11.3 验证路径

1. 开发壳：单栏常驻（两模式）、logo+开关在左、SVG 按钮、**拖动/双击最大化/四边四角边缘缩放**、✕→**托盘图标出现**→恢复/退出、DSH 切换、启动 DSH 无 cmd 框；
2. Web 模式（浏览器直连 127.0.0.1:5000 或 5001）：页面正常、窗口按钮隐藏、无报错；
3. tests/desktop 45 passed → .004 构建后按任务书 2.5 复验。

---

## 12. R4 修订：放弃原生 NCHITTEST，全面 JS 驱动窗口操作（R4 定稿：2026-08-24 开发壳 GUI 实测全部通过，commit `637284c`）

R3 实装后 GUI 实测：双击 ✅、托盘 ✅、DSH 切换 ✅、Web 模式 ✅；**拖动 ❌（回归）、边缘缩放 ❌**。

### 12.1 关键结论（R3 实测证明）

| 结论 | 依据 |
|---|---|
| **原生 WM_NCHITTEST 对 WebView2 子窗口始终无效** | R2「拖动正常」实为 pywebview `easy_drag` 的 JS 增量移动在起作用；R3 `easy_drag=False` 后原生 HTCAPTION **没有接管拖动** → 拖动失效。子窗口子类化方案（§10/§11）整体废弃 |
| 边缘缩放 document 级 mousemove 覆盖不全 | shell 舞台被两个全屏 iframe（wiki/DSH）铺满，鼠标在左/右/下边缘时事件落在 iframe 内，**到不了 shell 父文档**；仅顶边（40px 栏内）可触发。Trae 已预判，实测证实 |
| JS 双击最大化 ✅ | 与 OS 消息传导无关，直接调 `toggle_maximize()`，确定性生效 |

### 12.2 R4 方案：窗口操作 = JS 事件 + Python Win32 直控

**A. `src/desktop.pyw`**
1. **删除整套无效原生 NCHITTEST**：`_child_hit_test`、`_child_wndproc`、`_find_webview2_child`、`EnumChildWindows`、`_install_hook` 中的子窗口子类化、`set_drag_exclusions`、`_drag_exclusions`、`_bar_height`、`_in_drag_exclusion`、`WM_NCHITTEST/HT*` 常量及相关 ctypes 声明。父窗口 `_wndproc` 只留 `WM_CLOSE→托盘`。
2. `WindowApi` 新增 `start_drag()`：`ReleaseCapture()` + `SendMessageW(_hwnd[0], WM_SYSCOMMAND, SC_MOVE|HTCAPTION, 0)`（`WM_SYSCOMMAND=0x0112`、`SC_MOVE=0xF010`）——WinForms 无边框经典拖动；最大化时拖动自动还原（原生行为）。**若实测 SC_MOVE 无效，fallback：发 `WM_NCLBUTTONDOWN(0x00A1)` wParam=HTCAPTION**（R1 失败系 easy_drag 干扰，现已关停，可再试）。
3. `start_resize(dir)` 开头：`IsZoomed` 时直接返回（最大化禁边缘缩放）。
4. 保留：`easy_drag=False`、`minimize/toggle_maximize/is_maximized/close`、`start_resize` 循环、`events.maximized/restored → __setWinState`。

**B. `src/modules/agent/templates/shell.html`**
1. **拖动**：`shellBar` mousedown（button 0 且 target 非交互区：`!e.target.closest('button, .seg, .badge, .win-btn')`）→ `api.start_drag()`；交互区 stopPropagation 保持。
2. **边缘缩放改固定覆盖条**（替代 document mousemove，解决 iframe 遮挡）：
   - 4 边条 + 4 角块：`position:fixed`、z-index 高于 iframe、透明背景：
     - top/bottom 高 8px 全宽；left/right 宽 8px 全高；角块 14×14；
   - 每条 `data-dir`；hover 显示对应 resize 光标；mousedown → `api.start_resize(dir)` + `preventDefault()`；
   - 顶边条压栏最上 8px（该带 resize-n 而非拖动，与 Windows 行为一致）；
   - **最大化时隐藏全部条带**（`__setWinState` 同步 `body.is-maximized`，CSS 隐藏）。
3. 保留：dblclick 最大化、Web 模式按钮隐藏、其余逻辑不变。

### 12.3 验证路径

1. 开发壳：栏空白区**拖动**（含最大化态拖顶栏 → 还原+拖动）、**双击最大化/还原**、**四边四角 8px 缩放**（最小 1024×600；最大化时禁用）、三按钮、✕→托盘→恢复/退出、DSH 切换、无 cmd 框；
2. Web 模式：直连 127.0.0.1:5000 正常、按钮隐藏、无报错；
3. tests/desktop 45 passed → .004 构建复验。
