# zssnote 设计规范

> 总设计索引。修改任何子系统前先查本文，按链接找到对应设计文档阅读。

---

## 架构总览

ZSSNote = Flask Blueprint 模块化 × 14 功能模块，围绕四条核心线：

```
Flask App (app.py) ─ 注册 14 Blueprint + CORS + SQLite 自动迁移
│
├─ common/                    共享层
│  ├─ agent.py                Agent 循环 (LLM+MCP, ≤30轮) + 专家模式强制流程 + Skills 注入
│  ├─ mcp_client.py           MCPClientBus (外部 MCP 连接 + persist 参数)
│  ├─ builtin_mcp_manager.py  内置服务统一管理器 (bin/mcp/*/service.json 自包含发现)
│  ├─ skill_loader.py         Skills 加载器 (扫描 bin/skills/*/SKILL.md)
│  ├─ llm.py / llm_config.py  LLM 适配器 (OpenAI/Claude/Gemini/Ollama)
│  ├─ scheduler.py            APScheduler 定时调度
│  ├─ automation_runner.py    自动化 Agent 执行引擎
│  ├─ sync_service.py         公共库 git 同步 + 向量索引
│  ├─ embedding_config.py     Embedding 配置
│  ├─ self_update.py          自更新 (git pull + pip)
│  └─ response.py             统一 JSON 响应
│
├─ modules/                   功能模块
│  ├─ mcp/          MCP 双角色 (Server+Client) · 25 工具 + 内置服务管理（含 save_text_file 覆盖/追加）
│  ├─ chat/         对话页 · SSE 流式 · Agent 自动 · 阶段节点式思考过程 · 附件分流读取 · 模型切换
│  ├─ wiki/         知识编译管道 · 混合检索 · 图谱
│  ├─ article/      Markdown 文章 · 图片 · 附件
│  ├─ automation/   控制台 · 定时任务 · MCP/Skills 管理
│  ├─ todo/         五泳道待办看板
│  ├─ home/         仪表盘 · 收藏 · 实时搜索
│  └─ [note|folder|picture|plan|settings|weather]
│
├─ static/                    CSS (令牌体系) / JS / SVG 图标
│  ├─ css/components/
│  │  ├─ markdown.css         共享 Markdown 样式（chat/ article/ wiki/ drawer）
│  │  └─ ...
│  └─ js/
│     ├─ utils/md.js           共享 Markdown 渲染模块（LRU 缓存 + 后端渲染）
├─ bin/                       内置服务与技能（统一管理）
│  ├─ mcp/                    内置 MCP 服务（每个文件夹自包含 service.json）
│  │  ├─ officecli/           binary 类型：.NET 内嵌二进制 (6 平台)
│  │  ├─ pdf-mcp/             subprocess 类型：PDF MCP 运行时 (自包含源码 + models/ + cache/)
│  │  ├─ websearch/           subprocess 类型：联网搜索 MCP (DuckDuckGo Lite, 自包含源码)
│  │  └─ zssnote/             embedded 类型：ZSSNote 自身对外 MCP Server
│  └─ skills/                 Skills（Markdown 工作流）
│     └─ bom-picking/         BOM 检查技能 (SKILL.md + scripts/)
└─ doc/                       设计文档
   ├─ DESIGN.md                  ★ 本文件
   ├─ ZSSNote_MCP_设计方案.md    MCP 完整设计
   └─ assets/                    架构图 (SVG)
```

### 四条核心设计线

| 线 | 核心 | 要点 |
|----|------|------|
| **LLM 知识编译** | `wiki/compiler/` | 文章 → 提取(LLM) → 合并 → 生成 → 审批 → 向量索引；SHA-256 增量 |
| **MCP 双角色** | `modules/mcp/` + `common/mcp_client.py` | Server 26 工具 + Client 总线 + 内置服务管理器 |
| **Agent 无处不在** | `common/agent.py` | 对话页始终 Agent (≤30轮)，定时任务也走 Agent，专家模式强制知识库+联网搜索，Skills 注入提示词 |
| **Skills 工作流编排** | `common/skill_loader.py` + `bin/skills/` | SKILL.md 声明式技能，Agent 自动匹配加载，编排 MCP 工具 |

---

## 子系统

### MCP 系统

**[→ 完整设计文档](ZSSNote_MCP_%E8%AE%BE%E8%AE%A1%E6%96%B9%E6%A1%88.md)**
**[→ 通用文本写入工具设计](MCP_%E9%80%9A%E7%94%A8%E6%96%87%E6%9C%AC%E5%86%99%E5%85%A5%E5%B7%A5%E5%85%B7%E8%AE%BE%E8%AE%A1%E6%96%B9%E6%A1%88.md)**

ZSSNote 的 MCP 系统兼具 **Server** 和 **Client** 双角色：

| 角色 | 模块 | 说明 |
|------|------|------|
| **Server** | `modules/mcp/routes.py` + `registry.py` | 对外暴露 26 个工具（JSON-RPC 2.0 over `/mcp`），供外部 AI 客户端调用 |
| **Client** | `common/mcp_client.py` | `MCPClientBus` 总线，连接远程 MCP 服务器（`server__tool` 命名空间路由） |
| **内置服务** | `common/builtin_mcp_manager.py` | 管理本地内置 MCP 服务（子进程拉起、健康检查、注册到总线） |
| **统一 API** | `modules/mcp/client_routes.py` | 前端 MCP 管理页面的 REST API，合并内置 + 自定义服务 |

**工具路由**：`MCPClientBus.call_tool(name)` — `name` 含 `__` → 远程路由；否则 → 本地 registry handler。

**安全**：路径越界检测、`.md` 白名单、LLM 不可自审批、不提供 `delete_note`。

---

### 内置服务统一管理（bin/mcp/）

每个服务**自包含**在自己的文件夹下，由 `service.json` 声明。`common/builtin_mcp_manager.py` 扫描 `bin/mcp/*/service.json` 自动发现并管理所有内置 MCP 服务。与 Skills 的 `SKILL.md` 自描述模式一致：删除文件夹 = 移除服务，加文件夹 = 新增服务，零配置零代码。

#### 目录结构

```
bin/mcp/
├── officecli/                 ← binary 类型：预编译二进制（进 Git）
│   ├── service.json           ← 自包含声明（进 Git）
│   ├── officecli-*.exe        ← 各平台二进制
│   └── ...                    
├── pdf-mcp/                   ← subprocess 类型：pip 依赖 + 运行时数据
│   ├── service.json           ← 自包含声明（进 Git）
│   ├── pdf_mcp/               ← pdf-mcp 自包含源码（进 Git，替代 pip install）
│   ├── launcher.py            ← HTTP 启动脚本（streamable-http, 进 Git）
│   ├── models/                ← 嵌入模型 (~67MB, HF 镜像下载, 不进 Git)
│   └── cache/                 ← SQLite 缓存 (不进 Git)
├── websearch/                 ← subprocess 类型：联网搜索 MCP（自包含源码）
│   ├── service.json           ← 自包含声明（进 Git）
│   ├── launcher.py            ← HTTP 启动脚本（端口 17655, 进 Git）
│   └── websearch_mcp/         ← 自包含源码（DuckDuckGo Lite, 进 Git）
│       ├── __init__.py
│       └── server.py          ← FastMCP 服务器 + web_search 工具
└── zssnote/                   ← embedded 类型：应用自身 MCP Server
    └── service.json           ← 自包含声明（进 Git）
```

#### 三种服务类型

| 类型 | 说明 | 启动方式 | 可重连 | 示例 |
|------|------|----------|--------|------|
| `binary` | 预编译二进制，由本地 handler 直接调用 | 仅做目录/文件存在性检查 | 否 | officecli |
| `subprocess` | Pip 包 MCP 服务器，子进程拉起 HTTP 端点 | 子进程启动 → TCP 健康检查 → 注册到 MCPClientBus | 是 | pdf-mcp |
| `embedded` | 嵌入在当前进程内，始终可用 | 无需启动，直接返回可用 | 否 | zssnote |

#### service.json 完整字段

| 字段 | 必填 | 说明 | 示例 |
|------|------|------|------|
| `name` | 是 | 服务名（应与文件夹名一致） | `"pdf-mcp"` |
| `source` | 是 | 来源：`builtin` / `custom` | `"builtin"` |
| `location` | 是 | 位置：`local` / `remote` | `"local"` |
| `type` | 是 | 启动方式：`subprocess` / `binary` / `embedded` | `"subprocess"` |
| `description` | 推荐 | 服务描述 | `"PDF 文档读取..."` |
| `command` | subprocess | 启动命令 | `"python"` |
| `args` | subprocess | 命令参数（支持 `{bin_dir}` 模板） | `["{bin_dir}/launcher.py"]` |
| `host` | subprocess | 监听地址 | `"127.0.0.1"` |
| `port` | subprocess | 监听端口 | `17654` |
| `path` | subprocess | MCP 端点路径 | `"/mcp"` |
| `health_path` | subprocess | 健康检查路径 | `"/health"` |
| `auth_token_env` | subprocess | Token 环境变量名 | `"PDF_MCP_AUTH_TOKEN"` |
| `startup_timeout` | subprocess | 启动超时秒数 | `30` |
| `env` | subprocess | 环境变量（支持 `{bin_dir}` 模板） | `{"FASTEMBED_CACHE_PATH": "..."}` |
| `ensure_dirs` | subprocess | 启动前确保存在的子目录 | `["models", "cache"]` |
| `tool_count` | binary | 工具数量（文档用） | `9` |

**模板变量**：`{bin_dir}` → `bin/mcp/<name>/` 绝对路径，`{name}` → 服务名。

#### 管理器生命周期

```
app.py 启动
  → init_all_async() 守护线程
    → _discover_services() 扫描 bin/mcp/*/service.json
    → 逐个 start_service()
      ├─ binary   → _check_binary_service()  文件存在性检查
      ├─ subprocess → _start_subprocess_service()
      │               ├─ 子进程拉起 (Popen)
      │               ├─ 健康检查 (HTTP 200 → TCP 端口回退)
      │               └─ bus.add_server(name, url, token, persist=False)
      └─ embedded → _check_embedded_service() 直接返回可用
```

**关键设计**：
- `persist=False`：内置服务 token 每次随机生成，不写入 `mcp_servers.json`
- 后台守护线程：不阻塞 Flask 启动，服务逐个异步就绪
- 异常保护：`_worker` 循环内 try/except，单个服务失败不影响其他
- `stderr.log`：subprocess 的 stderr 重定向到 `bin/mcp/<name>/stderr.log` 辅助诊断

#### 统一 API

`GET /api/mcp/services` — 合并三个数据源为一个列表：

| 数据源 | source | location |
|--------|--------|----------|
| `builtin_mcp_manager._statuses`（bin/mcp/*/service.json） | builtin | 从 service.json 读取 |
| `MCPClientBus._remote_clients`（mcp_servers.json） | custom | remote |
| zssnote 保底（若后台线程未及注册） | builtin | local |

每个服务返回字段：`name`, `description`, `source`, `location`, `type`, `connected`, `tool_count`, `url`, `error`, `can_delete`, `can_reconnect`。

**错误消除**：subprocess 启动竞态可能导致 MCPClientBus 残留旧错误，统一 API 在 `connected=true 且 tool_count>0` 时自动清除 `error` 字段。

#### 工具查询 API

| 端点 | 说明 |
|------|------|
| `GET /api/mcp/servers/<name>/tools` | 查询指定服务的工具列表 |
| subprocess/remote | 从 MCPClientBus 获取 |
| binary (officecli) | 从本地 registry 匹配 `_BUILTIN_GROUPS` |
| embedded (zssnote) | 返回全部本地 registry 工具 |

#### 重连 API

`POST /api/mcp/servers/<name>/reconnect`：

| 类型 | 行为 |
|------|------|
| subprocess | `_stop_service()` → `sleep(1)` → `start_service()` 重新拉起子进程并注册 |
| custom/remote | `bus.reconnect()` 重做 MCP 握手 |
| embedded | 400：无需重连 |
| binary | 400：无需重连 |

前端重连按钮点击后状态序列：**重连中...** (黄色) → **已断开** (灰色, 0.6s) → **已连接** (绿色)。

---

### Skills 系统（bin/skills/）

Skill = Markdown 工作流指令 + 可选脚本。LLM 读取 SKILL.md 后按指令编排 MCP 工具完成跨系统任务。

```
bin/skills/
└── bom-picking/               ← 每个 skill 一个文件夹
    ├── SKILL.md               ← YAML front matter (name+description) + 工作流指令
    └── scripts/
        └── check_bom.py       ← 配套脚本（可选）
```

**SKILL.md 格式**

```yaml
---
name: bom-picking
description: Use when checking or validating PCB BOM Excel files ...
---
# 工作流标题
<Markdown 格式的详细工作流指令>
```

**添加自定义 Skill（零代码零配置）**

1. 在 `bin/skills/` 下新建文件夹（名称即 skill 标识）
2. 创建 `SKILL.md`，填写 YAML front matter（`name` 必填，`description` 必填——Agent 据此匹配用户意图）
3. 编写 Markdown 工作流指令（分步骤、交互规则、常见问题等）
4. 可选：在 `scripts/` 子目录放置辅助脚本
5. 重启服务即可生效，前端 Skill 标签页自动显示

删除也一样：删文件夹 = 移除 Skill，无需改代码。

**加载与执行流程**

```
Agent 启动
  → skill_loader.list_skills()     扫描 bin/skills/*/SKILL.md
  → get_skills_prompt()            生成技能摘要 → 注入系统提示词
  → match_skill(user_message)      关键词匹配用户意图
  → 命中 → load_skill(name)        读取完整 SKILL.md
  → SKILL.md 内容注入对话          LLM 按工作流编排 MCP 工具
```

**API**：`GET /api/skills`（列表）· `GET /api/skills/<name>`（详情）

**前端展示**：Skill 标签页采用与 MCP 服务相同的卡片模式（`.am-mcp-card` + 展开箭头 + `[内置]` `[本地]` 标签），点击卡片展开 SKILL.md 完整内容（Markdown 渲染为 HTML），支持 280ms 动画过渡、按压反馈、`prefers-reduced-motion` 无障碍。

**与 MCP 的关系**：MCP 工具是原子操作接口，Skills 是编排多个 MCP 工具完成业务流程的指令书

---

### Wiki 知识编译

将 Markdown 文章自动编译为结构化 Wiki。

```
文章 .md  ──→ extractor ──→ merger ──→ generator ──→ candidate ──→ approve ──→ index
              (LLM 提取)    (概念合并)   (页面生成)     (待审批)      (人工审批)    (向量+BM25)
```

| 模块 | 职责 |
|------|------|
| `extractor.py` | LLM 提取概念（单篇/批量） |
| `merger.py` | 去重合并相同概念 |
| `generator.py` | 生成 Wiki 页面 + 候选页 |
| `pipeline.py` | 编排全量/增量编译 |
| `hasher.py` | SHA-256 变更检测，增量编译 |
| `retrieval.py` | 向量(OpenAI Embedding) + BM25(jieba) 混合检索，LRU 缓存 |
| `status.py` | 线程安全编译进度（`get_compile_status` 轮询替代 SSE） |

**数据模型**：`WikiPage` — slug / title / body / refs（来源溯源）/ status（approved/pending/rejected）/ author

**审批流**：编译产出进入 pending → `approve_candidate` / `reject_candidate`。LLM 不可自审批。

---

### Agent 与对话

Agent 循环 (`common/agent.py`) 是 MCP 工具调用的统一入口，对话页 (`modules/chat/`) 始终走 Agent。

**[→ 阶段节点式思考过程组件规格](阶段节点式思考过程组件%20开发规格说明.md)**
**[→ 对话页设计方案](对话页设计方案.md)**

```
用户消息 + Wiki 上下文 ──→ Agent ≤30 轮 ──→ SSE 流式返回
      + Skills 摘要            │
                              │
                      MCPClientBus.call_tool()
                      本地 25 + 远程 N + 内置 MCP 统一调度
```

**关键决策**：
- 始终启用，无手动开关
- Wiki 上下文 `---` 分隔符注入
- **Skills 注入**：`get_skills_prompt()` 在系统提示词追加可用技能列表，`match_skill()` 匹配用户意图后自动加载完整 SKILL.md
- **附件分流读取**：对话页上传附件按格式分流 — Office 文件 → OfficeCLI / PDF → pdf-mcp / 文本 → UTF-8 / 其他 → 标注二进制
- `get_tools_for_llm()` 合并本地+远程+内置 → OpenAI function calling 格式
- 远程工具命名规则 `server__tool_name`（双下划线，`call_tool` 据此路由到对应 MCPRemoteClient）
- 工具 `isError: true` 不中断循环，LLM 可自行修正
- 多模型支持：OpenAI / Claude / Gemini / Ollama（`common/llm.py` 适配器）
- 会话持久化：`ChatSession` + `ChatMessage` ORM 模型，含 `thinking_json` 思考过程持久化
- **Runtime 依赖**：`requirements.txt` 声明 pymupdf / fastembed / fastmcp（为 pdf-mcp 自包含运行所需，无需 `pip install pdf-mcp`）

#### 专家模式强制流程

专家模式不再依赖 LLM 自主决定是否搜索，而是**系统强制执行**两路搜索后注入上下文：

```
用户提问
  ├─ 1. 自动调用 search_kb(keyword=用户问题) → 推送「搜索知识库」阶段
  ├─ 2. 自动调用 websearch__web_search(query=用户问题) → 推送「联网搜索」阶段
  ├─ 3. 推送「整理思路」展示性阶段
  ├─ 4. 将两路搜索结果注入 full_messages 作为 system 消息
  └─ 5. 进入正常 agent_chat 循环（LLM 可继续调用工具或直接回答）
```

快速模式不走强制流程，由 LLM 自主决定是否调用工具。

#### 阶段节点式思考过程

SSE 流式推送思考阶段，前端以横向节点进度条渲染：

| 模式 | 阶段链 |
|------|--------|
| 专家模式（强制） | 分析问题 → 搜索知识库 → 联网搜索 → 整理思路 → [LLM工具调用...] → 生成回答 |
| 快速模式 | 分析问题 → [LLM工具调用...] → 生成回答 |

SSE 事件类型：`stage_start` / `stage_end` / `custom_stage_start` / `custom_stage_end` / `heartbeat` / `thinking_done` / `chunk` / `done`。历史消息加载时通过 `thinking_json` 恢复可折叠的思考过程面板。

#### 模型切换

对话页支持运行时切换 LLM 模型：`GET /api/chat/model-configs` 返回可用模型列表 + 当前活跃模型，`POST /api/chat/model-configs/switch` 切换活跃模型。前端下拉菜单乐观更新 UI。

---

### 文章系统

文件系统 Markdown 管理：`resource/article/` 目录树即知识库结构。

- CRUD REST API (`/api/article/`) + Markdown → HTML 渲染
- MCP `write_note` 内联 base64 图片自动提取（`image_extractor.py` → `resource/img/`）
- 附件上传，代码高亮

---

### 自动化系统

定时 Agent 任务：APScheduler 触发 → Agent 执行 → 写结果。

- `common/scheduler.py`：BackgroundScheduler，加载 `automation_task` 表
- `common/automation_runner.py`：按服务器名过滤工具，Agent 循环执行
- `modules/automation/`：三标签页控制台（自动化任务 / MCP 服务 / Skill 技能）
- 数据模型：`AutomationTask` (cron/描述/服务器) + `TaskRun` (状态/输出/耗时)

**Skill 标签页**：展示 `bin/skills/` 下所有 Skill，采用与 MCP 服务相同的卡片模式（展开箭头 + 标签 + Markdown 渲染），点击展开查看完整 SKILL.md 内容。

---

### 前端 UI

CSS 令牌 → 共享 `mcp.css` → 覆盖 `automation.css`。

```
static/css/
├─ base.css         全局令牌 (--font-sans, --color-primary...)
├─ themes.css       主题切换
├─ layout.css       布局
├─ index.css        入口 @import 链
└─ components/
   ├─ mcp.css       ★ 共享词汇表 (内置+自定义统一)
   ├─ automation.css 仅放覆盖，不重复定义 mcp.css
   ├─ chat.css / wiki.css / sidebar.css / card.css / modal.css / graph.css
```

**核心规则**：改 MCP 样式 → 只改 `mcp.css`，两侧同步生效。Skills 标签页同样复用 `mcp.css` 的卡片模式（`.am-mcp-card`、`.am-mcp-chevron`、`.am-mcp-expanded`）。

**类叠加模式**：`am-mcp-*` (共享) + `am-srv-*` (MCP 服务) + `am-skill-*` (Skill 展开面板)。

**来源/位置标签** (`.am-tag`)：内置蓝 `am-tag-builtin`、自定义紫 `am-tag-custom`、本地绿 `am-tag-local`、远程橙 `am-tag-remote`。

**加载顺序**：`base → themes → layout → mcp → automation → ...`

#### 设计令牌

| 令牌 | 值 |
|------|----|
| `--font-sans` | Inter |
| `--font-mono` | JetBrains Mono |
| `--color-primary / --color-primary-50` | 主色 / 浅底 |
| `--color-surface / --color-surface-alt` | 卡片表面 / 交替 |
| `--color-foreground / --color-muted` | 前景 / 弱化 |
| `--color-border / --color-border-light` | 边框 / 浅边框 |
| `--color-background` | 页面背景 |

#### MCP 共享组件类 (mcp.css)

| 类 | 用途 |
|----|------|
| `.am-mcp-card` / `-head` / `-chevron` | 卡片 / 头部 / 展开箭头 |
| `.am-mcp-name-row` / `-name` / `-sub` | 名称行 / 标题 / 描述 |
| `.am-mcp-badge` / `-hint` | 工具数 / 版本胶囊 |
| `.am-mcp-status` + `-on`/`-off`/`-warn`/`-dot` | 状态指示 |
| `.am-mcp-tool-name` / `-desc` / `-cost` | 工具名 / 描述 / 成本 |
| `.am-mcp-tools-list` | 工具列表容器 |
| `.am-tag` + `-builtin`/`-custom`/`-local`/`-remote` | 来源/位置标签 |

---

### 其他模块

| 模块 | 说明 |
|------|------|
| todo | 五泳道看板（收集箱→待办→进行中→已完成→已取消） |
| home | 仪表盘：收藏夹 + 天气 + 实时搜索（输关键字自动进 Chat Agent 模式） |
| note | 快速笔记 |
| folder | 文件夹管理 |
| picture | 图片管理（`resource/img/`） |
| plan | 计划管理 |
| settings | LLM/Embedding 配置、主题、资源路径 |
| weather | 天气配置 |

---

## 编码约定

### Python

- **MCP 工具名**：snake_case（`read_document`）
- **Handler 命名**：`handle_{tool_name}`
- **Blueprint**：`{module}_bp`，`__init__.py` 导出，`app.py` 统一注册
- **ORM 模型**：单数 CamelCase（`WikiPage`, `TodoItem`, `AutomationTask`）
- **DB Session**：handler 内 commit/rollback，Flask teardown 自动 remove
- **线程安全**：`MCPClientBus` 用 `RLock`，网络 I/O 在锁外

### CSS

- **前缀**：`am-`（automation）
- **状态灯**：共享 `am-mcp-status-on/off/warn`

---

## 基础设施

| 项 | 说明 |
|----|------|
| 数据库 | SQLite `resource/instance/sseditor.db`，启动时自动迁移 (PRAGMA) |
| 存储 | `resource/article/*.md` + `resource/img/` + `resource/instance/` |
| 端口 | 默认 `5000`，绑定 `0.0.0.0` |
| LLM | OpenAI / Claude / Gemini / Ollama，`LLMConfig` 数据库持久化 |
| Embedding | OpenAI Embedding，`EmbeddingConfig` 管理 |
| 自更新 | 启动时 `git pull` + `requirements.txt` 检测 + `pip install` |

### 启动

```
cd src
$env:FLASK_APP='app'
python -m flask run --host=0.0.0.0 --port=5000 --no-reload
```

---

## OfficeCLI

内嵌 .NET 二进制（`src/bin/mcp/officecli/`，6 平台，v1.0.143），在 `bin/mcp/officecli/service.json` 中以 `binary` 类型声明。由 `modules/mcp/tools_office.py` 通过 `subprocess.run()` 直接调用，超时 120s。前端通过 `GET /api/mcp/servers/officecli/tools` 从本地 registry 获取 9 个工具列表。

平台映射：`_get_platform_id()` → darwin→mac, windows→win, x86_64→x64, arm64→arm64。

## pdf-mcp

PDF 文档读取/搜索/大纲/分页服务（13 个 MCP 工具），引擎为 PyMuPDF (fitz)。源码自包含在 `bin/mcp/pdf-mcp/pdf_mcp/` 下（不依赖 `pip install pdf-mcp`），通过 `launcher.py` 以 streamable-http 模式在端口 17654 启动。嵌入模型下载到 `bin/mcp/pdf-mcp/models/`（通过 HF 镜像），SQLite 缓存在 `bin/mcp/pdf-mcp/cache/`。

Runtime 依赖（在 `requirements.txt` 中声明）：pymupdf、fastembed、fastmcp。

## websearch

联网搜索 MCP 服务（1 个工具 `web_search`），使用 DuckDuckGo Lite 免费搜索（无需 API Key）。源码自包含在 `bin/mcp/websearch/websearch_mcp/` 下，通过 `launcher.py` 以 streamable-http 模式在端口 17655 启动。专家模式强制流程自动调用此服务进行联网搜索。

目录结构：
```
bin/mcp/websearch/
├── service.json           ← subprocess 类型声明（端口 17655）
├── launcher.py            ← sys.path 自包含启动入口
└── websearch_mcp/
    ├── __init__.py        ← 版本号
    └── server.py          ← FastMCP 服务器 + DuckDuckGo 搜索实现
```

---

## 测试体系

后端单元测试基于 pytest，位于 `tests/` 目录。

```
Tests/
├── conftest.py            ← pytest fixture（Flask app context、DB 隔离）
├── mcp/                   ← MCP 工具单元测试
│   └── test_tools_search.py
├── chat/                  ← 对话与思考过程测试
│   ├── test_agent_expert.py    ← 专家模式强制流程（5 个测试）
│   ├── test_thinking_stages.py ← 思考阶段构建逻辑（8 个测试）
│   ├── test_tool_map.py        ← TOOL_CN_MAP 映射完整性（5 个测试）
│   └── test_mermaid_img.py     ← Mermaid 代理端点（10 个测试）
└── common/                ← 共享层测试
    └── test_seed_sync.py       ← 种子智能同步（12 个测试）
```

**运行测试**：

```bash
cd src
python -m pytest tests/ -v          # 全部
python -m pytest tests/chat/ -v     # 仅对话相关
python -m pytest tests/common/ -v   # 仅共享层
```

**测试策略**：
- Mock LLM adapter + MCP bus，不依赖外部服务
- 覆盖专家模式强制流程（自动搜索、结果注入、回调顺序、失败容错）
- 覆盖思考阶段构建（阶段链顺序、轮次标注、completed 状态、JSON 序列化）
- 回归保护：TOOL_CN_MAP 核心工具映射不遗漏
- Mermaid 代理端点：base64url 编码、多图型代理、中文标签、错误处理
- 种子同步：新增文件、更新文件、用户文件保留、子目录递归、源不存在容错

---

## 变更记录

### 2026-08-12

**对话页多项优化**（[chat.js](../static/js/modules/chat.js) / [chat.css](../static/css/components/chat.css)）

- 源码面板白色蒙层修复：`.mermaid-source pre` 全部属性加 `!important`，容器固定深色背景 `#1e293b`，彻底覆写全局 markdown 样式
- Mermaid 渲染语法纠正：前端弯引号→直引号自动替换、classDiagram 中文类名引号包裹、mindmap `(text)`→`["text"]` 转义
- 连续流思考速度优化：打字机 50ms→10ms/字符，折叠后不再清除 DOM 重建
- 对话模式默认为专家：`_chatMode = 'expert'`
- SVG 常量模块级统一：6 个共享 SVG + `_escHtml()` 死代码移除
- CSS 优化：合并重复 `@media` 查询，移除 ~100 行 v3 遗留 CSS

**种子智能同步**（[app.py](../src/app.py)）

- `_seed_smart_sync()` 替代 `_seed_user_dir()`：逐文件内容对比（`filecmp.cmp(shallow=False)`），seed 新增→追加、变更→覆盖、用户独有→保留
- MCP 服务配置（`seed/mcp/*.service.json`）和 Skills 技能（`seed/skills/*/SKILL.md`）同步到运行时目录
- 每次启动执行，不再限于首次；无变更时打印"已是最新"日志

**Mermaid 图表技能**（[SKILL.md](../seed/skills/mermaid/SKILL.md) / [agent.py](../common/agent.py)）

- 新建 `seed/skills/mermaid/SKILL.md`：8 条规范 + 审查清单，涵盖 flowchart/classDiagram/mindmap/subgraph/时序图
- `_get_mermaid_prompt()` 从 skill 文件注入系统提示词（精简版 ~400 字符），不再在 system prompt 硬编码
- 后端 Mermaid 代理：`GET /api/chat/mermaid-img?code=<base64url>` 解决浏览器 ORB 跨域

**新增测试用例**

- `tests/chat/test_mermaid_img.py`：10 个用例，覆盖 base64url 编码、4 种图型代理、空码/错误处理
- `tests/common/test_seed_sync.py`：12 个用例，覆盖新增/更新/保留/递归/容错全场景

---

## 变更记录

### 2026-08-07

**路径设置改为用户自定义**（[启动.bat](../packaging/scripts/启动.bat) / [routes.py](../modules/settings/routes.py) / [settings.html](../modules/settings/templates/settings.html) / [config.py](../config.py)）

路径设置页从"只读展示"改为"用户可编辑"：
- `启动.bat` 去掉自动创建数据目录的步骤（不再在启动时建 `resource/`）
- 路径设置页输入框变为可编辑，用户可输入自定义资源路径
- 点击"保存"时后端写入 `.env` 文件（`RESOURCE_BASE_PATH=用户输入的路径`），并创建所需子目录
- 首次使用流程：启动 → 打开浏览器 → 设置页填写路径 → 保存 → 开始使用

新增 API：
- `GET /api/settings/path` — 返回当前资源路径
- `POST /api/settings/path` — 保存路径到 .env 并创建目录

**启动即安装 — 合并首次安装与启动**

合并 `首次安装.bat` 和 `启动.bat` 为单一入口，用户只需双击"启动.bat"：
- `启动.bat` 启动前自动执行环境自检（runtime → 依赖 → .env → 桌面快捷方式）
- 自检全通过则直接启动 Flask；有问题则自动修复后继续
- 删除独立的 `首次安装.bat`

**关于页签增加环境检查信息**

`GET /api/settings/version` 返回完整环境诊断：
- runtime 路径、依赖完整性（逐个检测 flask/openai/pymupdf/fastembed）
- 数据目录可写性、磁盘剩余空间
- bin/ MCP 服务清单

关于页面新增"环境诊断"区块，展示检测结果，方便用户和开发者排查问题。

新增 API：
- `GET /api/settings/version` — 返回当前版本、Python 版本、运行模式
- `POST /api/settings/upgrade/check` — 检查远程是否有新版本
- `POST /api/settings/upgrade/apply` — 下载并应用增量更新

### 2026-08-11

**SSE 流式响应修复**（[routes.py](../modules/chat/routes.py) / [chat.js](../static/js/modules/chat.js)）

- 修复对话页 SSE 流式响应"网络错误"：服务端发送两个 `done` 事件导致客户端过早停止读取流、`reader.cancel()` 触发浏览器断连
- 服务端第二个 `done` 改为 `session_name` 事件，客户端收到 `done` 后不取消 reader，让流自然结束
- 修复 `Md.renderSync().then(...)` 错误：`renderSync` 是同步函数，改为直接赋值
- 新增 `_doneProcessed` 守卫防重复处理

**静态文件浏览器缓存**（[app.py](../src/app.py)）

- `SEND_FILE_MAX_AGE_DEFAULT = 0` + `after_request` 添加 `Cache-Control: no-store`
- 解决修改 JS/CSS 后浏览器使用缓存旧文件的问题

**设置页路径保存修复**（[routes.py](../modules/settings/routes.py)）

- 路径保存改为临时文件 + `os.replace` 原子替换，避免 PermissionError

**fastmcp 版本冲突**（requirements.txt）

- `fastmcp 3.4.7` 移除 `FastMCP` 类导致 pdf-mcp/websearch 不可用，回退到 `fastmcp==2.14.7`

**文章删除确认重构**（[article.js](../static/js/modules/article.js) / [article.css](../static/css/components/article.css)）

- 删除按钮行内 `onclick` 改为 `data-action` + `#tree-list` 事件委托
- 原生 `confirm()` 改为自定义模态框（居中弹窗 + 取消/确认删除按钮 + 遮罩关闭）

**剪贴板写入兜底**（[chat.js](../static/js/modules/chat.js)）

- `navigator.clipboard.writeText()` 权限不足时回退到 `document.execCommand('copy')`（隐藏 textarea + 选中 + 复制）

**save_text_file MCP 工具**（[tools_write.py](../modules/mcp/tools_write.py) / [tools_registration.py](../modules/mcp/tools_registration.py) / [security.py](../modules/mcp/security.py)）

- 新增通用文本写入工具：支持覆盖/追加双模式，可选 `article`（默认，与 write_note 同根）/ `resource` 根目录
- 覆盖模式使用临时文件 + `os.replace` 原子替换；追加模式直接 `open(path, 'a')`
- 测试：22 个测试用例，覆盖覆盖/追加/路径越界/root 参数等场景

**Wiki 编译状态移至源文件工具栏**（[wiki.html](../modules/wiki/templates/wiki.html)）

- 编译状态指示从全局 header 移至 sources 标签页工具栏，仅编译相关页签显示

**Wiki 字体大小优化**（[wiki.html](../modules/wiki/templates/wiki.html)）

- 遵循 UX 排版规范：正文 ≥16px、标签 ≥12px、按钮 14px、卡片标题 15px

### 2026-08-06（续）

**对话页新建对话模式**（[chat.html](../modules/chat/templates/chat.html) / [chat.js](../static/js/modules/chat.js)）

移除欢迎页 6 个快捷操作按钮（总结文章/解释概念等），改为新建对话页面模式：
- 欢迎页仅保留问候语 + 输入框，首次输入消息自动创建会话并发送
- `initChat()` 无历史会话时显式 `hideChat()`（显示欢迎页 + 输入框），不再依赖 HTML 默认值
- `sendMsg()` 无 `sid` 时自动调用 `createNewSession()` 再发送
- `hideChat()` 不再隐藏输入框，确保欢迎态和对话态输入框均可用
- 删除不再使用的 `startWith()` 函数
- 5 处 `alert()` 统一替换为 `showToast()`
- 修复 `renderHistory()` 空状态占位 SVG 自闭合 bug

**头像 SVG 全局同步**（[base.html](../templates/base.html) / [settings.html](../modules/settings/templates/settings.html) / [avatar.js](../static/js/modules/avatar.js)）

头像系统从 FontAwesome 图标统一为内联 SVG 路径，设置页与侧边栏全局同步：
- `window.AVATAR_SVGS`（base.html）定义 16 个头像 SVG 路径，`loadAvatar()` 读取此对象
- 设置页 `_settingsAvatarSVGs` 同步定义，选择头像后即时更新侧边栏
- 修复 `TypeError: Cannot read properties of undefined (reading 'moon')`：`onPageReady()` 调用移到脚本末尾，确保 `var _settingsAvatarSVGs` 先赋值再执行

**设置页头像弹窗修复**（[settings.html](../modules/settings/templates/settings.html)）

去掉行内 `onclick`，改用 `addEventListener` 绑定头像点击事件；SVG 加 `pointer-events: none` 防止内部元素拦截点击。

**SPA 脚本加载顺序修复**（[base.html](../templates/base.html)）

重构 SPA 导航脚本注入逻辑：先 `Promise.all()` 加载所有外部 `[src]` 脚本，完成后再执行内联脚本，解决对话页 `initChat` 未定义导致历史对话为空的问题。

**MCP 状态显示修复**

后端 `mcp_client.py` 的 `status()` 返回 `connected`（布尔值），前端 JS 按字符串 `'connected'` 匹配导致显示 0/3。修正为直接按布尔值过滤。

### 2026-08-05

**共享 Markdown 渲染模块**（[md.js](../static/js/utils/md.js) / [markdown_service.py](../modules/article/markdown_service.py)）

抽取项目级 Markdown 渲染为共享模块：
- 前端 `Md` 模块（`static/js/utils/md.js`）：`Md.render()` / `Md.renderInto()` / `Md.renderSync()`，LRU 缓存 80 条
- 后端 `markdown_service.py` 新增：任务列表 `- [ ]`、Wiki 链接 `[[title]]`、来源标注 `^[source]` 渲染
- 对话页、文章页、Wiki 页面、预览面板统一使用 `Md` 模块，消除 3 处手写 JS 渲染器

**文章页 Wiki 侧滑抽屉**

文章页中 `[[Wiki概念]]` 链接不再跳转导航，改为侧滑抽屉展示 Wiki 页面内容（[article.html](../modules/article/templates/article.html) / [article.js](../static/js/modules/article.js)）

**SVG 图标替换**

全部页面图标从 emoji 替换为 SVG（[article.html](../modules/article/templates/article.html) / [chat.html](../modules/chat/templates/chat.html) 等）

**SPA 路由修复**

对话页 SPA 导航时通过 inline script 调用 `initChat()`，解决点击对话菜单后"暂无历史对话"问题（[chat.html](../modules/chat/templates/chat.html) / [index.js](../static/js/index.js)）

**文档创建系统提示词**

Agent 系统提示词（[agent.py](../common/agent.py)）新增"文档创建规则"：LLM 严禁主动创建文档，仅当用户明确说"保存为文档"、"导出为 Word"时才调用文档工具

**右侧预览面板**

- 默认宽度 360px → 440px（[chat.css](../static/css/components/chat.css)）
- 修复 `preview_doc()` API 缺少 `type: 'markdown'` 导致渲染失败（[routes.py](../modules/chat/routes.py#L728)）

### 早期变更
