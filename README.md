# PersonLLMWiki

**AI-Powered Personal Knowledge Management System**

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-2.0%2B-black?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

基于 Flask 的全栈个人知识管理系统，**深度继承 DeepSeek Harness（DSH）作为内置 AI 执行引擎**——桌面端单栏顶栏一键切换「Wiki | DSH」双模式，DSH agent 经 MCP 直接检索知识库、读写文章、触发编译。将散落的笔记、文章、图片统一管理，通过 **LLM 自动编译为互链 Wiki 知识库**；规划中的**记忆模块**（1.2）将补齐会话记忆自动提取与开场召回注入，形成**知识 + 记忆双轨上下文底座**（详见[设计方案](doc/记忆与上下文交付设计方案.md)）；支持 **MCP 双角色**（对外 19 个工具的 Server，接入外部服务的 Client）。支持 **Web 浏览器** 与 **桌面应用**（PyWebView 无边框单栏）两种形态。

---

## 🏗️ 架构

![PersonLLMWiki × DeepSeek Harness 架构图](doc/architecture.svg)

- **DSH（DeepSeek Harness）** — AI 执行引擎，作为 **MCP Client** 经协议调用 PLW 能力（检索知识库 / 读写文章 / 触发编译 / 记忆读写），桌面端以 iframe 嵌入（DSH 模式）；**亦可直接配置使用外部 MCP Server / Skill（主通道）**
- **PLW（PersonLLMWiki）** — Flask 知识管理系统：知识库核心（文章 → Wiki 编译 → 混合检索）+ **记忆模块**（会话记忆自动提取 / 开场召回注入，知识·记忆双轨制）+ **MCP Server**（`/mcp`，19 个工具）+ **Bridge** 桥接层
- **MCP** — 统一协议层（JSON-RPC 2.0 / streamable-HTTP）。**架构方向（三层）**：外部 MCP / Skill 统一由 DSH 消费；DSH ↔ PLW 走 `/mcp`（知识检索 / 记忆读写 / 编译触发）；PLW ↔ 外部 MCP Server（SAP 等）为**过渡态**（MCP Client 总线，规划收敛，见待办）
- **Bridge（dsh_bridge）** — 桌面端管理 DSH 生命周期（启动 / 状态 / 版本门禁）、headless 调用、静默拉起与单栏模式切换
- **桌面壳（PyWebView）** — 无边框单栏自绘标题栏（logo + Wiki|DSH 开关 + 窗口按钮），拖动 / 双击最大化 / 边缘缩放 / 关闭到托盘，统一承载双模式

---

## ✨ 亮点

- **LLM 知识编译** — 文章 → LLM 概念提取 → 概念合并 → 页面生成 → 审批 → 向量索引，增量编译（SHA-256 哈希检测）
- **混合检索** — Embedding API + BM25（jieba）双路召回
- **知识 + 记忆双轨（1.2 规划）** — 会话记忆自动提取 / 开场召回注入，与人工审批知识隔离互不污染（详见[设计方案](doc/记忆与上下文交付设计方案.md)）
- **MCP 双角色** — 既是 MCP Server（对外暴露 19 个工具）供 AI 客户端调用，也是 MCP Client 连接外部服务
- **DSH 集成** — 桌面端顶栏「Wiki \| DSH」模式切换；DSH agent 可直接检索知识库、读写文章、触发编译
- **共享中心** — 技能 / 智能体 / MCP 服务的发布、浏览与一键安装（git 同步）*（1.0.1 暂隐藏，1.1 回归）*
- **知识星链** — D3.js 力导向图，节点大小反映关联数量
- **Markdown 原生** — 文章以 `.md` 文件存储，零锁定

---

## 📸 界面预览

| 工作台 | Wiki 知识库 |
|---|---|
| <img src="src/static/img/首页.png" width="400"> | <img src="src/static/img/Wiki.png" width="400"> |

| 对话（Agent + MCP 工具） | 文章管理 |
|---|---|
| <img src="src/static/img/AIChat.png" width="400"> | <img src="src/static/img/文章.png" width="400"> |

| 知识星链 | DSH 模式（内置 AI 执行引擎） |
|---|---|
| <img src="src/static/img/知识星链.png" width="400"> | <img src="src/static/img/DSH.png" width="400"> |

---

## 📦 功能模块

### 工作台

扁平分区仪表盘，展示收藏文章、天气、数据统计。顶部搜索框输入问题后自动跳转对话页，Agent 模式调用 MCP 工具查询。

### 对话

AI 对话页面，统一走 Agent 模式（LLM + MCP tool-calling）。支持：

- 多模型（OpenAI / Claude / Gemini / Ollama），流式输出
- Wiki 知识库上下文注入
- MCP 工具自动调用
- 对话转存为文章或 Wiki 页面

### 知识库

Swiss-Style Minimalism 卡片网格布局，概念按 kind 分组。标签页：

- **概念** — 已编译的概念卡片，点击查看详情（摘要、正文、来源溯源、相关概念）
- **源文件** — Markdown 源文件列表，标注编译状态，可触发增量/全量编译
- **待审批** — 编译产出的候选页面，逐条审核通过/拒绝

编译管道：`article/*.md → LLM 概念提取 → 概念合并 → 页面生成 → wiki/concepts/*.md → Embedding 向量索引`

### 共享中心（1.0.1 暂隐藏，1.1 回归）

技能（SKILL.md）/ 智能体定义 / MCP 服务定义的**发布、浏览与一键安装**：

- 发布：本地技能/智能体 → 校验（manifest）→ 写入共享仓库 → 更新索引 → git 提交
- 安装：`copy-to`（技能落位本地）/ `mcp-connect`（生成 MCP 客户端配置）
- 共享物标注来源等级：官方库 / 同事 / 外部

### 任务 / 自动化 / 文章 / 图片

- **任务**：五泳道看板（收集箱 / 待办 / 进行中 / 已完成 / 已取消）
- **自动化**：定时 AI Agent 任务（APScheduler），支持周期 / 间隔 / 单次，可经 headless 桥接外部执行引擎
- **文章 / 图片**：Markdown 文件管理、文件夹树、附件上传、图片网格视图

### 设置

LLM 配置、Embedding 配置、用户资料、资源路径、系统更新、外部执行引擎（DSH）关联与升级。

---

## 📌 路线图（待办）

### 架构收敛（1.1：外部 MCP 统一走 DSH 三层架构）

详见 [待办：架构收敛](doc/待办-架构收敛.md)（应用内待办同步记录）。

- [ ] **[高] MCP Client 总线**（`mcp_client.py` / `/api/mcp/servers`）标记 legacy，1.1 评估移除
- [ ] **[中] SAP 定时同步改走 DSH headless**（或直连 HTTP/DB），移除 PLW 主动调 SAP MCP 的依赖（与上一条一起评估）
- [ ] **[中] PLW 内置对话 agent 工具源限缩**到自身 19 个 MCP 工具，外部能力一律由 DSH 承接

### 模块完善（1.1：本次发布暂隐藏，完善后重新开放）

- [ ] **[中] 共享中心** — 发布 / 安装流程打磨后重新开放菜单
- [ ] **[中] 笔记** — 功能完善后重新开放菜单

### 体验迭代

**安装版体验**
- [x] **[高] 安装版全自动静默升级**（下载 → 自退出 → 静默安装 → 自动重启；其下载通道是「升级下载进度条」前置）
- [x] **[中] 升级下载进度条**（流式下载 + `/api/settings/upgrade/download-progress` 轮询 + 前端进度显示；依赖上一条的下载通道）
- [ ] **[中] Windows 代码签名**（消除 SmartScreen「未知发布者」提示）

**桌面壳体验**
- [x] **[中] 全屏保留桌面任务栏**：无边框桌面壳（PyWebView）全屏后流出桌面任务栏的位置，不遮挡任务栏（含最大化 / 退出全屏交互可用）
- [x] **[高] 修复标题栏拖动回归**：自绘标题栏被移出窗口可视区后，窗口无法再通过顶栏拖动；需确保标题栏可拖拽区域对「拖动 / 最大化时拖顶栏还原」均生效（回归点：`desktop.pyw` 的 `start_drag`）
- [x] **[中] 拖到桌面最上方默认放大**：按住标题栏将窗口拖至屏幕顶部时默认放至最大（Aero Snap 顶边吸附语义），松手进入最大化；再次拖离顶部可还原
- [x] **[中] 记忆窗口位置与大小**：退出时保存窗口 bounds 与最大化状态，下次启动恢复上次位置/尺寸（含多显示器 DPI 缩放容错）

**DSH 交互收敛（建议与 1.1 架构收敛同批实施，避免两次改动 `dsh_bridge.py` / 设置页）**
- [ ] **[中] DSH 集成收敛**：`shared/routes.py` 的 `_append_cordis_patch` 与 DSH 实际 cordis 语法（数组 `insert:`）/数据目录（`~/.dsh`）不一致，统一重构为 `get_dsh_data_home()` + 标准 insert 语法（「检查更新 → 升级指引」前置）
- [ ] **[中] DSH 检查更新 → 升级指引（移除一键更新 / 重新安装）**：设置页移除「一键更新 / 重新安装」按钮；「检查更新」发现新版本时提示版本差异（当前 vs 最新）并给出升级操作指引——开发者：`cd <DSH 安装目录> && npm install @deepseek-ai/dsh@latest` 后重启 DSH；保持「关联已有 DSH」与 DSH 独立升级原则（PLW 不接管 DSH 安装文件，互不耦合）；同步修订 `doc/README-架构边界与升级指南.md` §3.2 表格

**决策记录（不占排期）**
- 📋 **[已评估，暂不立项] DSH vision × PLW 图片打通**：最小验证通过（`02_第2章_路由决策` 截图识别质量可接受，通道可用），无批量/无人值守看图需求，暂不立项；保留 L0（人工传图 + `write_note` 写回）。触发条件：知识库超预算大图（>1 MiB / 64 万像素）自动压缩后小字失真的批量场景 → 再启动 L1（MCP 新增 `list_images` / `read_image`）

### 记忆与上下文（OpenViking 替代，1.2 方向）

PLW 补全「会话记忆自动提取 + 分层上下文交付 + 技能沉淀」，单进程替代本机 OpenViking 的 Agent 上下文底座角色（详见 [记忆与上下文交付设计方案](doc/记忆与上下文交付设计方案.md)）：

- [ ] **[高] 记忆模块**：对话结束后台异步提取（用户偏好/事实/决策）→ `resource/memories/*.md` → embedding 索引 → 对话开场自动召回注入；新增 MCP 工具 `remember` / `search_memory` / `list_memories` / `forget_memory`
- [ ] **[中] 分层上下文交付**：`context_assembler` 按 token 预算分「摘要 → 命中片段 → 原文」三层组装检索结果，替代"整库 Top-K 全量注入"（依赖记忆模块）
- [ ] **[中] 技能沉淀**：会话中识别可复用流程 → 生成 SKILL.md 草案 → 复用候选审批流入库
- [ ] **[中] 记忆/知识双轨制**：自动记忆（低门槛入库 + 一键撤回 + 带来源对话）与人工审批知识（可信溯源）隔离，互不污染

---

## 🗓️ 版本计划

| 版本（主版本） | 主题 | 包含待办 | 状态 |
|---|---|---|---|
| **1.0.2** | 体验补丁 | 安装版全自动静默升级、升级下载进度条、全屏保留桌面任务栏、标题栏拖动回归修复、拖到顶部最大化、记忆窗口位置、Windows 代码签名（视证书就绪，代码签名延期） | 已完成 |
| **1.1** | 三层架构落地 + DSH 交互收敛 + 模块回归 | 架构收敛（MCP Client 总线 legacy / SAP 改 headless / 对话工具源限缩）、DSH 集成收敛、DSH 检查更新→升级指引、共享中心 / 笔记回归 | 未开始 |
| **1.2** | 记忆与上下文（OpenViking 替代） | 记忆模块、分层上下文交付、技能沉淀、记忆/知识双轨制 | 未开始 |
| — | 不排期 | 📋 DSH vision × PLW 图片打通（触发条件未达，已评估暂不立项） | 已评估 |

**版本号规则**：

- `VERSION` = 主版本（如 1.0.2），由版本计划确定；
- 构建号（`app_version.txt` / git tag `v<主版本>.<构建号>`）由打包流程按构建轮次生成（`packaging/build_counter.txt` 计数，当前=8），**不预先指定**——验证不过会继续打包、构建号继续递增；
- 发版以最终验证通过的构建产物为准，每轮验证走 [打包验证任务书](doc/打包验证任务书.md)；
- zip 增量通道（`packaging/versions.json`）随正式版更新 `latest` 与版本条目。

---

## 🏗️ 技术架构

```
src/
├── app.py                              # Flask 应用入口 + SQLite 自动迁移
├── config.py                           # 配置管理
├── desktop.pyw                         # 桌面应用入口（PyWebView）
├── common/                             # 共享层：LLM 适配、Agent 循环、MCP 总线、调度器
├── modules/
│   ├── home/                           # 工作台仪表盘
│   ├── chat/                           # AI 对话
│   ├── wiki/                           # 知识库 + 编译管道 + 混合检索
│   ├── shared/                         # 共享中心（发布/浏览/安装）
│   ├── automation/                     # 定时 AI Agent
│   ├── mcp/                            # MCP Server + Client 双角色
│   ├── todo/                           # 五泳道看板
│   ├── article/  picture/  note/       # 内容管理
│   └── settings/  weather/             # 设置与工具
├── static/                             # CSS / JS / 图标
└── templates/                          # SPA 基础布局
```

**与 DeepSeek Harness（DSH）的分工**：PLW 管「内容与公司能力」（知识编译/检索/审批/工具），DSH 管「执行编排」（goal/workflow/subagent/skills）。二者通过 MCP 标准协议协作，详见 [架构边界与升级指南](doc/README-架构边界与升级指南.md)。

---

## 🚀 快速开始

### 环境要求

| 依赖   | 版本   |
| ------ | ------ |
| Python | >= 3.8 |

### 1. 克隆项目

```bash
git clone https://github.com/zsafly-star/PersonLLMWiki.git
cd PersonLLMWiki
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 启动

**Web 模式**（浏览器访问 http://localhost:5000）：

```bash
cd src
python app.py
```

**桌面模式**（原生窗口，**无系统标题栏**——单栏自绘标题栏：左侧 logo +「Wiki | DSH」开关 + DSH 状态点，右侧最小化/最大化/关闭按钮；支持顶栏拖动、双击最大化、四边四角边缘缩放、关闭到系统托盘）：

```bash
cd src
python desktop.pyw
```

Windows 开发脚本：`.\dev.ps1 start | stop | restart`（`stop` 按命令行清理整套进程树：应用/MCP/DSH，避免端口残留；`stop -KeepDsh` 保留 DSH）

> 💡 集成 DeepSeek Harness（可选）：在设置页关联已安装的 DSH，即可在桌面端通过「Wiki | DSH」模式切换，让 DSH agent 直接使用知识库。

---

## 🔄 升级

- **安装版（推荐）**：设置页「版本与更新」→「检查更新」，自动查询 [GitHub Releases](https://github.com/zsafly-star/PersonLLMWiki/releases) 最新版本；发现新版本后点「下载并升级」，应用自动退出并启动新版安装向导（UAC 确认后覆盖安装；用户数据保留在 `~/.personllmwiki`，不受影响）。
- **源码 / zip 部署**：开发模式用 `git pull`（启动时自动检测 `requirements.txt` 变化并 `pip install`）；zip 部署用 `packaging/scripts/升级.bat`（versions.json 增量通道）。
- **发版约定**：GitHub tag 使用**完整构建号**（如 `v1.0.1.007`），Release 附件命名 `PersonLLMWiki-Setup-<版本>.exe`，否则安装版检测不到新版本。

---

## 📚 文档

- [架构边界与升级指南](doc/README-架构边界与升级指南.md) — 系统总览、PLW 与 DSH 分工、升级方法（**入口文档**）
- [PersonLLMWiki 设计规范](doc/PersonLLMWiki设计规范.md) — 各子系统设计索引
- [DSH 集成架构设计方案](doc/DSH集成架构设计方案.md) — 集成架构、知识供给、共享中心、里程碑
- [记忆与上下文交付设计方案](doc/记忆与上下文交付设计方案.md) — 会话记忆 / 分层交付 / 技能沉淀（OpenViking 替代，1.2）
- [打包验证任务书](doc/打包验证任务书.md) — 发版打包验证 SOP（可被任意 AI 工具执行）
- [安装版自动升级设计方案](doc/安装版自动升级设计方案.md) — 安装版 GitHub Releases 检测与升级
- [待办：架构收敛](doc/待办-架构收敛.md) — 外部 MCP 统一走 DSH 的三层架构收敛项（1.1）
- [分发部署方案](doc/分发部署方案.md) — 打包与分发
- [开发者打包发布指南](doc/开发者打包发布指南.md) — 发布流程

---

## 🔌 MCP API 概览

| 接口                      | 方法     | 说明                                                             |
| ------------------------- | -------- | ---------------------------------------------------------------- |
| `/mcp`                  | POST     | JSON-RPC 2.0（streamable-HTTP），`tools/list` / `tools/call` |
| `/api/wiki/compile`     | POST     | 触发知识编译（增量/全量）                                        |
| `/api/wiki/pages`       | GET      | 概念页面列表                                                     |
| `/api/wiki/candidates`  | GET      | 待审批页面                                                       |
| `/api/chat/sessions`    | GET/POST | 对话会话                                                         |
| `/api/automation/tasks` | GET/POST | 定时任务                                                         |
| `/api/shared/items`     | GET      | 共享中心条目                                                     |
| `/api/shared/publish`   | POST     | 发布共享物                                                       |

---

## 💾 数据存储

所有用户数据以文件系统为主，SQLite 为辅，**零云依赖**：

| 数据              | 存储方式                    | 位置                                           |
| ----------------- | --------------------------- | ---------------------------------------------- |
| 知识库文章        | Markdown 文件               | `{RESOURCE_BASE_PATH}/article/`              |
| Wiki 概念页面     | Markdown + JSON Frontmatter | `{RESOURCE_BASE_PATH}/wiki/concepts/`        |
| 向量索引          | JSON                        | `{RESOURCE_BASE_PATH}/wiki/embeddings.json`  |
| 图片 / 附件       | 文件系统                    | `{RESOURCE_BASE_PATH}/img/` `attachments/` |
| 聊天记录 / 元数据 | SQLite                      | `{RESOURCE_BASE_PATH}/instance/sseditor.db`  |

---

## 🧰 技术栈

| 类别             | 技术                                                                           |
| ---------------- | ------------------------------------------------------------------------------ |
| **后端**   | Flask, SQLAlchemy, APScheduler, SQLite                                         |
| **桌面**   | PyWebView (WebView2), pystray, PyInstaller, Inno Setup（无边框单栏自绘标题栏）  |
| **前端**   | 原生 JavaScript, Jinja2 模板, D3.js v7                                         |
| **AI**     | OpenAI API, Anthropic API, Gemini API, Ollama                                  |
| **检索**   | Embedding API + fastembed（本地 ONNX）+ BM25（jieba）                          |
| **文档解析** | PyMuPDF（PDF MCP）                                                             |
| **MCP**    | JSON-RPC 2.0 over HTTP（streamable-HTTP）                                      |
| **智能体** | [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)（**深度集成，内置 AI 执行引擎**） |

---

## 🙏 感谢

- [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)（深度集成，内置 AI 执行引擎）
- [Flask](https://github.com/pallets/flask)
- [PyWebView](https://pywebview.flowrl.com/)、[PyInstaller](https://pyinstaller.org/)、[Inno Setup](https://jrsoftware.org/isinfo.php)、[pystray](https://github.com/moses-palmer/pystray)（桌面壳与打包分发）
- [jieba](https://github.com/fxsjy/jieba)、[fastembed](https://github.com/qdrant/fastembed)（ONNX）、[PyMuPDF](https://pymupdf.readthedocs.io/)（中文分词检索、本地向量化、PDF 解析）
- [D3.js](https://d3js.org/)（知识星链可视化）
- llm-wiki-compiler（LLM Wiki 模式启发）
- [Trae](https://www.trae.ai/)（AI 编码助手，主要代码实现伙伴）

---

## 📄 许可证

[MIT License](LICENSE)
