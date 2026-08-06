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
- 不做自定义标题栏（用系统默认标题栏）。
