# LLMWikiPersonalNote

**AI-Powered Personal Knowledge Management System**

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-2.0%2B-black?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

基于 Flask 的全栈个人知识管理系统。将散落的笔记、文章、图片统一管理，通过 LLM 自动编译为互链 Wiki 知识库，支持 MCP 协议接入外部工具和 AI 助手。

---

## 目录结构

| 路径 | 说明 |
|------|------|
| `/demo` | 参考例程，只读 |
| `/instance` | SQLite 数据库 |
| `/resource` | 项目资源路径（文章、Wiki、图片） |
| `/src` | 项目源码 |

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
- **新建对话模式**：首次进入显示欢迎页 + 输入框，直接输入消息即可自动创建会话发送，无需手动点"新建对话"

### 知识库
Swiss-Style Minimalism 卡片网格布局，概念按 kind 分组展示。点击卡片右侧滑入详情抽屉，含摘要、正文、来源溯源 `^[文件]`、相关概念卡片。标签页：
- **概念** — 已编译的概念卡片，点击查看详情
- **源文件** — Markdown 源文件列表，标注编译状态（已编译 / 待编译），点击「增量/全量编译」触发 LLM 编译管道
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
双角色 MCP 协议（v2.0，24 工具）：
- **服务端**：`POST /mcp` (JSON-RPC 2.0)，4 Tier 工具：
  - Tier 1 只读 (7)：list_folders, read_note, list_wiki_pages, read_wiki_page, get_graph 等
  - Tier 2 检索 (1)：search_kb（向量+BM25 混合）
  - Tier 3 写入 (7)：write_note, compile_wiki, create_todo 等
  - Tier 4 OfficeCLI (9)：read_document, create_document, write_cells 等
- **客户端**：MCPClientBus 总线，连接外部 MCP 服务器（如 SAP），`server__tool` 路由

### 文章 / 图片
Markdown 文件管理、文件夹目录树、Fluent Emoji 图标、附件上传、图片网格/列表视图。

### 设置
LLM 配置、Embedding 配置、主题切换、资源路径。

---

## 技术亮点

- **MCP 双角色** — 既是 MCP Server 供外部 AI 使用，也是 MCP Client 调用外部工具
- **LLM 知识编译** — 两阶段管道（概念提取 → 页面生成），增量编译（SHA-256 哈希检测）
- **向量语义检索** — Embedding API + BM25 混合查询，精准命中知识库内容
- **知识星链** — D3.js 力导向图，节点大小反映关联数量
- **审批流** — 编译产出先进入待审批状态，逐个审核后才正式入库
- **来源溯源** — 每段内容标注 `^[来源文件]`，可追溯 LLM 生成内容的依据
- **定时自动化** — APScheduler + LLM Agent 循环，定时按提示词调用 MCP 工具执行任务
- **Markdown 原生** — 文章以 `.md` 文件存储，零锁定，随时可迁移

---

## 技术架构

```
src/
├── app.py                              # Flask 应用入口 + SQLite 自动迁移
├── config.py                           # 配置管理
├── extensions.py                       # 共享扩展（SQLAlchemy db）
├── common/
│   ├── llm.py                          # LLM 适配器（OpenAI/Claude/Gemini/Ollama）
│   ├── llm_config.py                   # LLM 配置 CRUD（数据库持久化）
│   ├── agent.py                        # Agent 循环：LLM + MCP tool-calling（≤10 轮）
│   ├── mcp_client.py                   # MCP 客户端总线（本地工具 + 远程 MCP 服务器）
│   ├── scheduler.py                    # APScheduler，DB 动态加载自动化任务
│   ├── automation_runner.py            # 自动化任务执行引擎
│   ├── embedding_config.py             # Embedding API 配置
│   └── response.py                     # 统一 JSON 响应格式
├── modules/
│   ├── home/                           # 工作台仪表盘
│   ├── chat/                           # AI 对话（统一 Agent 模式，流式输出）
│   ├── wiki/                           # 知识库
│   │   ├── compiler/
│   │   │   ├── pipeline.py             # 编译 + 查询编排
│   │   │   ├── extractor.py            # 概念提取（单篇/批量）
│   │   │   ├── generator.py            # 页面生成 + 候选页面
│   │   │   ├── retrieval.py            # 向量检索 + BM25 混合搜索
│   │   │   ├── prompts.py              # Prompt 模板
│   │   │   ├── hasher.py               # SHA-256 变更检测
│   │   │   └── status.py               # 编译状态管理（线程安全）
│   │   ├── wiki_service.py             # 文件系统操作
│   │   ├── models.py                   # WikiPage 模型（含溯源、审批字段）
│   │   ├── routes.py                   # API 路由 + 审批接口
│   │   └── templates/
│   │       ├── wiki.html               # Swiss-Style 卡片网格 + 抽屉详情
│   │       └── graph.html              # 知识星链图谱
│   ├── automation/                     # 控制台（定时 AI Agent 任务）
│   │   ├── models.py                   # AutomationTask + TaskRun 模型
│   │   ├── routes.py                   # CRUD API + 运行记录
│   │   └── templates/
│   │       └── automation.html          # 任务列表 + 新建弹窗 + 运行记录
│   ├── todo/                           # 五泳道看板任务管理
│   ├── mcp/                            # MCP 服务端 + 客户端
│   │   ├── routes.py                   # /mcp 端点 + 会话管理 + 客户端连接
│   │   ├── registry.py                 # 工具注册表
│   │   ├── errors.py                   # JSON-RPC 错误码
│   │   ├── security.py                 # 路径越界检测 + 扩展名白名单
│   │   ├── tools_read.py               # Tier 1 只读工具（7 个）
│   │   ├── tools_search.py             # Tier 2 检索工具（1 个）
│   │   ├── tools_write.py              # Tier 3 写入工具（5 个）
│   │   ├── image_extractor.py          # 内联图片提取（base64 → 文件）
│   │   └── tools_registration.py       # 工具注册入口
│   ├── article/                        # 文章模块（Markdown 渲染、文件夹管理、附件）
│   ├── picture/                        # 图片管理
│   ├── note/                           # 快速笔记
│   ├── settings/                       # 系统设置
│   └── weather/                        # 天气模块
├── static/
│   ├── css/                            # 组件化 CSS 模块
│   ├── emoji/                          # Fluent Emoji 3D 图标（200+）
│   └── lib/                            # 本地第三方库（Chart.js）
└── templates/                          # Jinja2 模板（SPA 式单页架构）
    └── base.html                       # 基础布局（侧边栏 + 主视图）
```

---

## 快速开始

### 环境要求

| 依赖 | 版本 |
|------|------|
| Python | >= 3.8 |
| pip | latest |

### 1. 克隆项目

```bash
git clone https://github.com/zsafly-star/LLMWikiPersonalNote.git
cd LLMWikiPersonalNote/src
```

### 2. 安装依赖

```bash
# 推荐：使用 conda
conda create -n flask python=3.10
conda activate flask
pip install -r requirements.txt

# 或使用 venv
python -m venv venv
source venv/bin/activate  # Linux/macOS
.\venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

### 3. 启动

```bash
python app.py
```

访问 **http://localhost:5000** 即可使用。

Windows 用户可使用开发脚本：

```powershell
.\dev.ps1 start     # 启动
.\dev.ps1 stop      # 停止
.\dev.ps1 restart   # 重启
.\dev.ps1 status    # 查看状态
```

---

## API 概览

### MCP 协议（JSON-RPC 2.0）

通过 `/mcp` 端点提供 MCP 协议接口。

| 接口 | 方法 | 说明 |
|------|------|------|
| `/mcp` | POST | JSON-RPC 2.0 请求（initialize / tools/list / tools/call 等） |
| `/mcp` | DELETE | 终止 MCP 会话 |
| `/api/mcp/servers` | GET/POST/DELETE | MCP 客户端服务器管理 |

**服务端工具列表**：

| 工具 | 层级 | 说明 |
|------|------|------|
| `list_folders` | Tier 1 | 列出知识库目录结构 |
| `read_note` | Tier 1 | 读取文章内容 |
| `list_wiki_pages` | Tier 1 | 列出 Wiki 概念页面 |
| `read_wiki_page` | Tier 1 | 读取 Wiki 页面详情 |
| `get_compile_status` | Tier 1 | 查询编译进度 |
| `list_candidates` | Tier 1 | 列出待审批页面 |
| `get_graph` | Tier 1 | 获取知识图谱数据（最多 80 节点） |
| `search_kb` | Tier 2 | 向量+BM25 混合语义检索 |
| `write_note` | Tier 3 | 创建/覆盖文章（支持内联图片） |
| `compile_wiki` | Tier 3 | 触发知识库编译 |
| `approve_candidate` | Tier 3 | 通过待审批页面 |
| `reject_candidate` | Tier 3 | 拒绝待审批页面 |
| `create_folder` | Tier 3 | 创建文件夹 |

### Wiki 知识库

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/wiki/compile` | POST | 启动编译（增量/全量） |
| `/api/wiki/status` | GET | 实时编译进度 |
| `/api/wiki/pages` | GET | 概念页面列表（已审批） |
| `/api/wiki/pages/<slug>` | GET/DELETE | 页面详情 / 删除 |
| `/api/wiki/sources` | GET | 源文章列表（含编译状态） |
| `/api/wiki/graph` | GET | 知识图谱数据（节点+边） |
| `/api/wiki/candidates` | GET | 待审批页面列表 |
| `/api/wiki/candidates/<id>/approve` | POST | 通过审批 |
| `/api/wiki/candidates/<id>/reject` | DELETE | 拒绝并删除 |
| `/api/wiki/embeddings/status` | GET | 向量索引状态 |
| `/api/wiki/embeddings/build` | POST | 手动构建向量索引 |

### 自动化任务

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/automation/tasks` | GET | 任务列表 |
| `/api/automation/tasks` | POST | 创建任务 |
| `/api/automation/tasks/<id>` | PUT/DELETE | 更新 / 删除 |
| `/api/automation/tasks/<id>/trigger` | POST | 手动触发执行 |
| `/api/automation/tasks/<id>/runs` | GET | 运行记录列表 |
| `/api/automation/tasks/runs/<id>` | GET | 运行记录详情 |
| `/api/automation/tasks/runs` | DELETE | 清空运行记录 |

### 对话

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/chat/sessions` | GET/POST | 会话列表 / 创建 |
| `/api/chat/sessions/<id>/messages` | GET | 消息历史 |
| `/api/chat/sessions/<id>/stream_message` | POST | 流式对话（统一 Agent 模式） |
| `/api/chat/sessions/<id>` | DELETE | 删除会话 |

### 调度器

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/scheduler/status` | GET | 调度器运行状态 + 任务列表 |
| `/api/scheduler/trigger/<job_id>` | POST | 手动触发定时任务 |

---

## 数据存储

所有用户数据以文件系统为主，SQLite 为辅，**零云依赖**：

| 数据 | 存储方式 | 位置 |
|------|----------|------|
| 知识库文章 | Markdown 文件 | `resource/article/` |
| Wiki 概念页面 | Markdown + JSON Frontmatter | `resource/wiki/concepts/` |
| 向量索引 | JSON | `resource/wiki/embeddings.json` |
| MCP 内联图片 | 文件系统（按文章名分目录） | `resource/img/<文章名>/` |
| 图片 / 附件 | 文件系统 | `resource/img/` / `resource/attachments/` |
| 聊天记录 / Wiki 元数据 / 自动化任务 | SQLite | `instance/sseditor.db` |

---

## 技术栈

| 类别 | 技术 |
|------|------|
| **后端** | Flask, SQLAlchemy, APScheduler, SQLite |
| **前端** | 原生 JavaScript, Jinja2 模板 |
| **AI** | OpenAI API, Anthropic API, Gemini API, Ollama |
| **向量检索** | Embedding API（可配置） + BM25（jieba 分词） |
| **MCP** | JSON-RPC 2.0 over HTTP（服务端）+ SSE/Streamable-HTTP（客户端） |
| **可视化** | D3.js v7（力导向图）, Chart.js |
| **Markdown** | Python-Markdown |
| **图标** | Fluent Emoji 3D（200+）, Lucide SVG Icons |
| **样式** | CSS 自定义属性，BEM 式命名，组件化 CSS |

---

## 感谢

- [Flask](https://github.com/pallets/flask)
- [Blossom](https://github.com/blossom-editor/blossom)
- [llm-wiki-compiler](https://github.com/atomicstrata/llm-wiki-compiler)
- [Fluent Emoji](https://github.com/microsoft/fluentui-emoji)

---

## 许可证

本项目基于 [MIT License](LICENSE) 开源。

---

<div align="center">

**如果这个项目对你有帮助，请给个 Star！**

</div>
