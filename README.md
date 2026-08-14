# PersonLLMWiki

**AI-Powered Personal Knowledge Management System**

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-2.0%2B-black?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

基于 Flask 的全栈个人知识管理系统。将散落的笔记、文章、图片统一管理，通过 LLM 自动编译为互链 Wiki 知识库，支持 MCP 协议接入外部工具和 AI 助手。支持 **Web 浏览器** 和 **桌面应用**（PyWebView 原生窗口）两种使用方式。

---

## 目录结构

```
PersonLLMWiki/
├── src/                    # 源码（Flask + 前端）
├── seed/                   # 播种数据（MCP + Skills 默认文件）
├── tests/                  # 测试
├── doc/                    # 文档
├── packaging/              # 打包脚本
│   ├── desktop.spec        #   PyInstaller 配置
│   ├── build_desktop.py    #   打包编排
│   ├── release.py          #   发布到 GitLab
│   └── installer.iss       #   Inno Setup 安装包
├── release/                # 打包产物（gitignored）
│   ├── dist/               #   绿色版 EXE
│   └── installer/          #   安装包 .exe
├── requirements.txt
└── VERSION
```

### 运行时数据目录

首次启动自动创建 `~/.personllmwiki/`（播种数据从安装目录 `seed/` 复制）：

```
~/.personllmwiki/           # 应用数据根（固定）
├── .env                    #   应用配置
├── instance/               #   数据库和配置（固定）
├── mcp/                    #   MCP 服务二进制（固定）
├── skills/                 #   技能定义文件（固定）
└── resource/               #   用户内容（可自定义）
    ├── article/
    ├── img/
    ├── attachments/
    └── wiki/
```

---

## 功能模块

### 工作台
扁平分区仪表盘，展示收藏文章、天气、数据统计。顶部搜索框输入问题后自动跳转对话页，Agent 模式调用 MCP 工具查询（如 SAP 库存）。

### 对话
AI 对话页面，统一走 Agent 模式（LLM + MCP tool-calling），无需手动切换。支持：
- 多模型（OpenAI / Claude / Gemini / Ollama），流式输出
- Wiki 知识库上下文注入（勾选开关）
- MCP 工具自动调用（SAP 物料查询、知识库检索等）
- 对话转存为文章或 Wiki 页面
- **新建对话模式**：首次进入显示欢迎页 + 输入框，直接输入消息即可自动创建会话发送

### 知识库
Swiss-Style Minimalism 卡片网格布局，概念按 kind 分组展示。点击卡片右侧滑入详情抽屉，含摘要、正文、来源溯源 `^[文件]`、相关概念卡片。标签页：
- **概念** — 已编译的概念卡片，点击查看详情
- **源文件** — Markdown 源文件列表，标注编译状态，点击「增量/全量编译」触发 LLM 编译管道
- **待审批** — 编译产出的候选页面，逐条审核通过/拒绝

编译管道：`article/*.md → LLM 概念提取 → 概念合并 → 页面生成 → wiki/concepts/*.md → Embedding 向量索引`

### 任务
五泳道看板：收集箱 / 待办 / 进行中 / 已完成 / 已取消。拖拽切换状态，支持子任务列表。

### 控制台（自动化）
定时 AI Agent 任务管理：
- **执行频率**：周期（每天/每周/双周/每月/每年 + 具体时间 + 可选星期）、按间隔（每 N 小时）、单次
- **任务配置**：名称、提示词、MCP 工具范围、生效日期区间
- **运行记录**：每次执行自动记录，展示执行状态、LLM 回复、工具调用明细
- 基于 APScheduler 动态加载，支持手动触发

### MCP
双角色 MCP 协议（v2.0，25 工具）：
- **服务端**：`POST /mcp` (JSON-RPC 2.0)，3 Tier 工具
- **客户端**：MCPClientBus 总线，连接外部 MCP 服务器（如 SAP）
- **write_note**：创建/覆盖 Markdown 文章，内嵌 base64 图片自动提取
- **save_text_file**：通用文本写入，支持覆盖/追加双模式，可选 article/resource 根目录

### 文章 / 图片
Markdown 文件管理、文件夹目录树、附件上传、图片网格/列表视图。

### 设置
LLM 配置、Embedding 配置、用户头像/昵称、资源路径、系统更新。

---

## 技术亮点

- **MCP 双角色** — 既是 MCP Server 供外部 AI 使用，也是 MCP Client 调用外部工具
- **LLM 知识编译** — 两阶段管道（概念提取 → 页面生成），增量编译（SHA-256 哈希检测）
- **向量语义检索** — Embedding API + BM25 混合查询
- **知识星链** — D3.js 力导向图，节点大小反映关联数量
- **审批流** — 编译产出先进入待审批状态，逐个审核后才正式入库
- **来源溯源** — 每段内容标注 `^[来源文件]`
- **定时自动化** — APScheduler + LLM Agent 循环
- **Markdown 原生** — 文章以 `.md` 文件存储，零锁定
- **桌面应用** — PyWebView 原生窗口，系统托盘，点 X 最小化

---

## 技术架构

```
src/
├── app.py                              # Flask 应用入口 + SQLite 自动迁移
├── config.py                           # 配置管理
├── desktop.pyw                         # 桌面应用入口（PyWebView）
├── extensions.py                       # 共享扩展（SQLAlchemy db）
├── common/
│   ├── llm.py                          # LLM 适配器
│   ├── llm_config.py                   # LLM 配置 CRUD
│   ├── agent.py                        # Agent 循环：LLM + MCP tool-calling
│   ├── mcp_client.py                   # MCP 客户端总线
│   ├── scheduler.py                    # APScheduler 定时任务
│   ├── automation_runner.py            # 自动化任务执行引擎
│   ├── embedding_config.py             # Embedding API 配置
│   ├── tray_manager.py                 # 系统托盘管理
│   ├── port_utils.py                   # 端口分配
│   ├── desktop_prefs.py                # 桌面偏好（首次启动标记）
│   ├── self_update.py                  # 自更新（git pull + 依赖检测）
│   └── response.py                     # 统一 JSON 响应格式
├── modules/
│   ├── home/                           # 工作台仪表盘
│   ├── chat/                           # AI 对话
│   ├── wiki/                           # 知识库 + 编译管道
│   ├── automation/                     # 控制台（定时 AI Agent）
│   ├── todo/                           # 五泳道看板
│   ├── mcp/                            # MCP 服务端 + 客户端
│   ├── article/                        # 文章管理
│   ├── picture/                        # 图片管理
│   ├── note/                           # 快速笔记
│   ├── settings/                       # 系统设置
│   └── weather/                        # 天气模块
├── static/
│   ├── css/                            # 组件化 CSS
│   ├── js/                             # 前端 JavaScript
│   ├── img/                            # 图标
│   └── lib/                            # 第三方库
└── templates/
    └── base.html                       # SPA 基础布局
```

---

## 快速开始

### 桌面版安装

1. 下载最新 [Release 分支](http://gitlab.xiangyuniot.com/AiTeam/personllmwiki/-/tree/releases) 中的 `PersonLLMWiki-Setup-*.exe` 安装包
2. 下载 `bin-resources-*.zip` 资源包
3. 安装完成后，将 `bin-resources-*.zip` 解压到资源路径（默认 `{安装目录}\resource\`），确保目录结构为：
   ```
   resource\bin\
   ├── mcp\
   │   ├── officecli\
   │   ├── pdf-mcp\
   │   ├── websearch\
   │   └── zssnote\
   └── skills\
   ```
4. 重启应用即可在控制台 → MCP 页面看到所有服务

### 环境要求

| 依赖 | 版本 |
|------|------|
| Python | >= 3.8 |

### 1. 克隆项目

```bash
git clone git@gitlab.xiangyuniot.com:AiTeam/personllmwiki.git
cd personllmwiki
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 启动

**Web 模式**（浏览器访问）：

```bash
cd src
python app.py
```

访问 **http://localhost:5000**。

Windows 开发脚本：

```powershell
.\dev.ps1 start     # 启动
.\dev.ps1 stop      # 停止
.\dev.ps1 restart   # 重启
```

**桌面模式**（原生窗口）：

```bash
cd src
python desktop.pyw
```

---

## 打包发布

### 打包

```bash
python packaging/build_desktop.py 1.0.0
```

产出：
- `release/dist/PersonLLMWiki/` — 绿色版
- `release/installer/PersonLLMWiki-Setup-1.0.0.exe` — 安装包

### 发布到 GitLab

安装包通过 `releases` 分支分发：

```bash
# 推送到 releases 分支
git checkout --orphan releases
git rm -rf .
cp release/installer/PersonLLMWiki-Setup-*.exe .
git add *.exe
git commit -m "release v1.0.0"
git push -u origin releases
git checkout main
```

用户下载地址：`http://gitlab.xiangyuniot.com/AiTeam/personllmwiki/-/tree/releases`

---

## API 概览

### MCP 协议（JSON-RPC 2.0）

| 接口 | 方法 | 说明 |
|------|------|------|
| `/mcp` | POST | JSON-RPC 2.0 请求 |
| `/mcp` | DELETE | 终止 MCP 会话 |
| `/api/mcp/servers` | GET/POST/DELETE | MCP 客户端服务器管理 |

### Wiki 知识库

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/wiki/compile` | POST | 启动编译（增量/全量） |
| `/api/wiki/status` | GET | 实时编译进度 |
| `/api/wiki/pages` | GET | 概念页面列表 |
| `/api/wiki/pages/<slug>` | GET/DELETE | 页面详情 / 删除 |
| `/api/wiki/sources` | GET | 源文章列表 |
| `/api/wiki/graph` | GET | 知识图谱数据 |
| `/api/wiki/candidates` | GET | 待审批页面 |
| `/api/wiki/candidates/<id>/approve` | POST | 通过审批 |
| `/api/wiki/candidates/<id>/reject` | DELETE | 拒绝 |
| `/api/wiki/embeddings/build` | POST | 构建向量索引 |

### 对话

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/chat/sessions` | GET/POST | 会话列表 / 创建 |
| `/api/chat/sessions/<id>/messages` | GET | 消息历史 |
| `/api/chat/sessions/<id>/stream_message` | POST | 流式对话 |
| `/api/chat/sessions/<id>` | DELETE | 删除会话 |

### 自动化任务

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/automation/tasks` | GET/POST | 任务列表 / 创建 |
| `/api/automation/tasks/<id>` | PUT/DELETE | 更新 / 删除 |
| `/api/automation/tasks/<id>/trigger` | POST | 手动触发 |
| `/api/automation/tasks/<id>/runs` | GET | 运行记录 |

---

## 数据存储

所有用户数据以文件系统为主，SQLite 为辅，**零云依赖**：

| 数据 | 存储方式 | 位置 |
|------|----------|------|
| 知识库文章 | Markdown 文件 | `{RESOURCE_BASE_PATH}/article/` |
| Wiki 概念页面 | Markdown + JSON Frontmatter | `{RESOURCE_BASE_PATH}/wiki/concepts/` |
| 向量索引 | JSON | `{RESOURCE_BASE_PATH}/wiki/embeddings.json` |
| 图片 / 附件 | 文件系统 | `{RESOURCE_BASE_PATH}/img/` / `{RESOURCE_BASE_PATH}/attachments/` |
| 聊天记录 / 元数据 | SQLite | `{RESOURCE_BASE_PATH}/instance/sseditor.db` |

`RESOURCE_BASE_PATH` 默认为项目外层 `resource/`，可在设置页自定义。

---

## 技术栈

| 类别 | 技术 |
|------|------|
| **后端** | Flask, SQLAlchemy, APScheduler, SQLite |
| **桌面** | PyWebView (WebView2), pystray, PyInstaller |
| **前端** | 原生 JavaScript, Jinja2 模板 |
| **AI** | OpenAI API, Anthropic API, Gemini API, Ollama |
| **向量检索** | Embedding API + BM25（jieba） |
| **MCP** | JSON-RPC 2.0 over HTTP + SSE/Streamable-HTTP |
| **可视化** | D3.js v7, Chart.js |
| **Markdown** | Python-Markdown |
| **图标** | Fluent Emoji 3D, Lucide SVG Icons |

---

## 感谢

- [Flask](https://github.com/pallets/flask)
- [PyWebView](https://pywebview.flowrl.com/)
- [Blossom](https://github.com/blossom-editor/blossom)
- [Fluent Emoji](https://github.com/microsoft/fluentui-emoji)

---

## 许可证

[MIT License](LICENSE)
