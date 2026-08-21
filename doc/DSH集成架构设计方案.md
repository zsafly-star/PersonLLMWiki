# PersonLLMWiki × DeepSeek Harness 集成架构设计方案

> 版本：v0.5（2026-08-21）｜ 状态：已实现 v0.1~v0.3，v0.4 修复待实施 ｜ 日期：2026-08-20
> 关联文档：《多智能体PRD.md》《多智能体技术方案.md》《PersonLLMWiki设计规范.md》《分发部署方案.md》《ZSSNote_MCP_设计方案.md》《DSH集成-变更实施说明.md》
> 本文是「知识库产品 × 智能体执行引擎」整合讨论的收敛结论，若与前述文档冲突，以本文为准。

## 修订记录

| 版本 | 日期 | 内容 |
|---|---|---|
| v0.1 | 2026-08-20 | 三件套架构定稿（共享后端 / Plan B 桌面端 Tab 壳 / DSH 插件）；V1/V2/V3/V6 验证结论回写 |
| v0.2 | 2026-08-21 | 桌面壳由「Tab 壳」改为「Trae 式 Wiki/DSH 模式切换」（§4.1）；深链桥改为 headless 桥（§4.4）；实施指引见《DSH集成-变更实施说明.md》。代码现状：Trae 已按 v0.1 实现并提交（`2f47a30`~`1d53810`） |
| v0.3 | 2026-08-21 | ①PLW 侧边栏「知识组 / 效率组」分组（§4.5）；②企微待办 → 智能体自动执行场景纳入规划（§13）；③效率组形态定案：不拆应用、不做 DSH 插件，能力经 MCP 工具互通（D10/D11） |
| v0.4 | 2026-08-21 | **撤销 v0.3 侧边栏分组**（用户反馈菜单分组文字不符合预期 + 浏览器入口看不到 Wiki/DSH 开关）；改为**统一入口**：`/` → shell 壳页，浏览器与桌面端均显示顶栏开关；侧边栏恢复平铺（§4.5 重写，实施见《DSH集成-变更实施说明.md》§10） |
| v0.5 | 2026-08-21 | P3 共享中心**落地规格**：共享仓库目录结构 + agent.json manifest 定稿 + 安装动作映射 + 一期 UI 范围（§7.5）；P1 知识供给打通完成、DSH 生态实测结论（server-pdf/pdfs-mcp-server/dsh-office 不合格，自研直连） |

---

## 1. 背景与目标

### 1.1 原始愿景（设计之初）

- PersonLLMWiki 可部署在云端服务器，产出**公共知识库**（如物料信息），公司同事直接使用，无需各自重复生产；
- 个人实例可把自有知识库**共享到云端**供他人使用（已落地为 `INSTANCE_MODE=single/personal/public` + `COMMON_GIT_REPO` git 同步 + `submit_to_public` 提交审批机制）。

### 1.2 新认知（视频启示 + 现状分析）

- 除知识库外，**MCP 服务、Skills、智能体（agent）同样可以共享**——共享的是"定义层"而非"运行实例"；
- PersonLLMWiki 控制台正在自研的多智能体编排（`src/modules/tasks/`：orchestrator/router/state_store/security），本质上是在重复实现 DeepSeek Harness（DSH）已有的 goal / subagent / workflow / skills 能力；
- DSH 是独立的 Node 应用（npm 包 `@deepseek-ai/dsh`，当前 v0.1.0-rc.6），Web UI 运行在 3080 端口，具备 Web GUI、持久会话、headless CLI、MCP 客户端、插件系统。

### 1.3 最终目标

1. **停止重复造轮子**：搁置自研多智能体模块，执行/编排层交给 DSH；
2. **保留并强化知识层**：wiki 编译管道、混合检索、审批流、文章管理、MCP Server 全部保留；
3. **一体化分发**：以 PersonLLMWiki 为主体打包桌面端，DSH 作为可插拔的"智能体引擎"嵌入；
4. **开发者原生体验**：提供 DSH 插件，让 DSH 用户一键接入 PersonLLMWiki 知识库；
5. **共享闭环**：知识库 / MCP / Skills / 智能体定义均可共享（git 为主，注册中心为演进方向）。

---

## 2. 总体架构：三件套

```
┌────────────────────────────────────────────────────────────┐
│ ③ DSH 插件（开发者分发）                                      │
│  @company/dsh-personllmwiki                                 │
│  · MCP client 配置声明（连 ① 的 /mcp）                        │
│  · 知识库 SKILL（教 agent 先 search_kb 再回答）               │
│  · 可选：知识库检索面板（UI slot）                            │
└───────────────┬────────────────────────────────────────────┘
                │ MCP (JSON-RPC 2.0 over HTTP)
┌───────────────┴────────────────────────────────────────────┐
│ ① 共享后端（不变，云上 public 实例）                          │
│  PersonLLMWiki Flask                                       │
│  · wiki 编译/混合检索/审批流 · 文章图片 · SQLite              │
│  · MCP Server：28 个工具（search_kb / read_wiki_page /       │
│    write_note / compile_wiki / submit_to_public …）          │
│  · INSTANCE_MODE=public，同事/其他 AI 客户端经 /mcp 接入      │
└───────────────┬────────────────────────────────────────────┘
                │ MCP + iframe + headless CLI
┌───────────────┴────────────────────────────────────────────┐
│ ② 产品分发（Plan B 桌面端）                                  │
│  PersonLLMWiki 桌面 = 主体窗口（PyWebView）                  │
│  · Tab 壳：工作台/对话/知识库/文章/…/【智能体=DSH iframe】    │
│  · sidecar：dsh_bridge.py 管理 DSH 进程（发现/启停/版本门禁）  │
│  · 设置页：DSH 关联/重装/更新                                │
└─────────────────────────────────────────────────────────────┘
```

### 2.1 三条通信路径（互不混用）

| 路径 | 协议 | 方向 | 场景 | 归属 |
|---|---|---|---|---|
| 工具调用（主通道） | MCP / JSON-RPC 2.0 | DSH → PersonLLMWiki | agent 检索知识库、写文章、触发编译、提交共享 | ①②③ 共用 |
| UI 嵌入 | iframe + postMessage | PersonLLMWiki 窗口 ↔ DSH web | 桌面端「智能体」Tab | ② |
| 进程调用 | headless CLI | PersonLLMWiki → DSH | 控制台定时任务触发 `dsh --profile headless "job"` | ② |

> **关键认知**：PersonLLMWiki 不感知插件的存在——它只看到 MCP 调用。插件是 DSH 侧的接入封装（声明连接 + 教用法），不是通信通道本身。

---

## 3. 组件一：共享后端（现状盘点 + 最小改动）

### 3.1 已有设施（全部保留，无需重写）

| 设施 | 位置 | 状态 |
|---|---|---|
| MCP Server 28 工具（Tier1 只读 7 / Tier2 检索 1 / Tier3 写入 7 / Office 9 / Todo 1 / Workspace 3） | `src/modules/mcp/tools_registration.py` | ✅ 已注册，`/mcp` 对外暴露 |
| 混合检索（向量 0.7 + BM25 0.3，jieba 分词，内存常驻） | `src/modules/wiki/compiler/retrieval.py` | ✅ `hybrid_search()` |
| 对话页"先找本地知识库"（eager 预检索 + 循环中按需） | `src/common/agent.py:185` | ✅ 同一 `search_kb` handler |
| 公共库 git 同步 / 提交审批 | `src/common/sync_service.py` + `INSTANCE_MODE` + `MCP_SUBMITTER_TOKEN` | ✅ 已存在 |
| 内置 MCP 服务统一管理（service.json 自包含发现） | `src/common/builtin_mcp_manager.py` | ✅ 已存在 |

### 3.2 最小改动清单

| 改动 | 说明 | 优先级 |
|---|---|---|
| `search_kb` 可选频控 | 云上 public 实例防 Embedding 配额滥用（本地可不做） | P2 |
| MCP Server 鉴权文档化 | 明确 `MCP_ADMIN_TOKEN` / `MCP_SUBMITTER_TOKEN` 的对接方式（DSH 客户端、同事 AI 客户端） | P1 |
| 公共实例部署文档 | 复用《分发部署方案》思路，补充 Linux 部署 + 常驻进程（systemd） | P1 |

---

## 4. 组件二：Plan B 桌面端

### 4.1 桌面壳（模式切换：仿 Trae Work/Code）

- `desktop.pyw` 加载本地 shell 页（`templates/shell.html`），**顶栏仅一条 ~36px 模式条**：左侧品牌 + `[Wiki | DSH]` 分段开关（仿 Trae 顶部 Work/Code 全模式切换），右侧 DSH 连接状态点（绿=在线 / 灰=未装）；
- 下方**单个 iframe 占满剩余 100%×100%**：Wiki 模式 → `http://127.0.0.1:{flask_port}`；DSH 模式 → `http://127.0.0.1:3080`；
- **懒加载 + 双 iframe 常驻**：首次切到 DSH 才加载 3080，之后 CSS `display` 切换 → 切换无刷新、两边状态（会话/页面）均保留；快捷键 Ctrl+Shift+M 或 Alt+1/2 切换；模式记忆写入 `desktop_prefs.json`，重启回到上次模式；
- 优雅降级：DSH 未装/版本过低 → DSH 侧显示「未安装/未启用」占位 + 引导去设置页，开关禁用该侧；
- **已验证**（2026-08-20）：DSH web 响应头无 `X-Frame-Options`、无 CSP `frame-ancestors`，可嵌入 iframe；PersonLLMWiki 已启用 flask-cors，跨源 API 无碍；
- 端口固定：Flask 由 `find_free_port` 改为固定/可配（iframe 需要确定性 URL），写入 `instance/desktop_prefs.json`。

> 本方案取代早期"Tab 壳"构想：单 iframe 全屏显示使两应用各自获得完整视口、保留原生风格，壳 chrome 最小化；PersonLLMWiki 侧边栏不再需要"智能体"入口。

### 4.2 sidecar 进程管理：`common/dsh_bridge.py`（唯一 DSH 交互入口）

```
发现   → DSH_URL（默认 :3080）health check
       → 已在跑（用户自启）→ 直接复用
       → 未在跑 → 按 DSH_CMD（PATH/配置）拉起
版本门禁 → dsh --version ≥ 最低版本才启用 DSH 模式
headless → 控制台定时任务调用封装（CLI 语法变化收敛在此文件）
```

- 铁律：**只管理进程，不碰 DSH 文件**；`$DSH_HOME` 与 `~/.personllmwiki` 数据永不相交；
- 优雅降级：DSH 缺失/版本过低 → 桌面壳 DSH 模式显示「未安装/未启用」占位 + 引导去设置页，其余功能照常。

### 4.3 设置页「DeepSeek Harness」区块（独立于「系统更新」）

| 动作 | 流程 | 说明 |
|---|---|---|
| 关联已有 DSH | 浏览选择 `dsh.cmd`/安装目录 → `dsh --version` 探测 → 3080 健康检查 → 写入配置 | 不触碰已有 `$DSH_HOME`，只记 `DSH_CMD` / `DSH_URL` |
| 重新安装 | 下载 dsh 运行时包（zip）→ 解压 → 自动关联 → 首次启动初始化 web profile | 同事无 Node 也可用（捆绑便携 Node） |
| 更新检查 | 已装版本 vs 远程最新 → 一键更新 → 换 `app\`、留 `home\` → 重启 | 会话不丢（sessions 与 profiles 分离） |

安装位置建议（无需管理员权限、按用户隔离、升级=换 app）：

```
%LOCALAPPDATA%\DeepSeekHarness\
├── app\            ← DSH 安装本体：便携 Node + @deepseek-ai/dsh（替换=升级）
├── home\           ← DSH_HOME（profiles/ sessions/ storages/，升级永不动）
└── version.txt
```

更新源（并存，可配）：**公司镜像 zip**（同事，内网快、可离线，沿用 `bin-resources-*.zip` 分发习惯）+ **npm registry**（开发者，检查 `@deepseek-ai/dsh` latest 版本号）。

> 注意：`profiles/web` 的整套依赖位于 `$DSH_HOME` 内（非安装目录），更新后需做一次 profile 同步（`dsh plugin` 或重初始化）；`sessions/` 与 `profiles/` 分离，重初始化不丢会话。

### 4.4 界面编排原则（B 档：原样嵌入 + 入口缝合）

- **不重新设计 DSH 页面**（npm 包、构建产物、独立升级，fork 成本不可接受）；
- 分工：PersonLLMWiki 导航负责「应用级切换」，DSH 内部导航负责「会话级操作」；
- **headless 桥**（已验证 V1：DSH web 不支持 URL 深链）：知识库概念卡「用智能体深入分析」→ 经 `dsh_bridge` 调 `dsh --profile headless "分析概念 X"`，结果展示在 PersonLLMWiki 侧（如控制台运行记录 / 详情弹层）；需要继续人工交互时再切到 DSH 模式续聊。相比深链跳转，headless 桥更确定、可记录、可审计；
- 壳层统一：shell 加统一顶栏（品牌 + 全局搜索），iframe 顶部对齐，不碰 DSH 内部样式。

### 4.5 入口统一与侧边栏形态（v0.4 定案）

**演进记录**：v0.3 曾定案「侧边栏知识组/效率组分组」并实现（`826cbd2`），但用户反馈：①菜单栏出现分组文字不符合预期；②「品牌 + Wiki|DSH 开关」在浏览器入口看不到（根因：开关只存在于桌面壳 `/shell`）。→ **v0.4 撤销分组，改为统一入口**（实施见《DSH集成-变更实施说明.md》§10）。

**v0.4 决策**：

1. **统一入口**：`/` 重定向到 shell 壳页（`agent.shell`）——**桌面端与浏览器访问同一入口**，都先看到 36px 顶栏「品牌 + Wiki|DSH 开关 + 状态点」；SPA 工作台迁移到 `/home`，shell 的 wiki iframe 指向 `/home`（防 iframe 嵌套）。
2. **侧边栏平铺**：不设分组标题；恢复 v0.2 平铺结构（工作台 / 对话 / 文章 / 待办 / Wiki / 图片 / 控制台 / 笔记 / 设置）；移除「任务(`/tasks`)」（搁置，路由保留）与「DSH 模式(`/agent`)」（顶栏开关已取代，路由保留）。
3. **效率组形态不变**：todo/automation 仍留在 PLW（不拆独立应用、不做 DSH 插件），与 DSH 互通靠 MCP 工具（`create_todo` 已暴露；automation 需要时加提交工具）。
4. 企微待办自动执行场景（§13）是"效率功能"的职责延伸：todo=任务队列、automation=调度器、DSH=headless 执行器。

---

## 5. 组件三：DSH 插件（开发者分发）

### 5.1 定位与形态

- npm 包 `@company/dsh-personllmwiki`（cordis 插件，`package.json` 声明 `dsh.client.inject` 扩展 Web UI slot）；
- 安装：`dsh plugin --profile web add @company/dsh-personllmwiki`；
- **L1 能力插件**（推荐范围），内容三件：
  1. **MCP 连接声明**：`{name: personllmwiki, url: http://127.0.0.1:5000/mcp, token: <MCP_ADMIN_TOKEN>}`（等价现有 `mcp_servers.json` 结构，见 `resource/instance/mcp_servers.json`）；
  2. **知识库 SKILL**：仿 `seed/skills/bom-picking/SKILL.md` 格式（frontmatter `name/description` + 正文），教 agent「回答前先调 `personllmwiki__search_kb`，必要时 `personllmwiki__read_wiki_page` 读全文」；
  3. **可选 UI slot**：只读"知识库快速检索"面板（调 search_kb 展示结果）。

### 5.2 为什么插件 ≠ 通信通道

- 插件只做"告诉 DSH 去哪连 + 教它怎么用"；数据流通全靠 MCP 标准协议（JSON-RPC 2.0）；
- PersonLLMWiki 侧**零代码改动**，`search_kb` 等 28 个工具原样暴露；
- 插件本身就是可共享物（见 §7），随 npm 私服 / git 分发。

### 5.3 与组件二的关系

- 桌面端（②）与插件（③）**互不冲突、可叠加**：② 服务非技术同事与产品品牌；③ 服务开发者在 DSH 里的原生体验；
- 共享后端（①）是两者共用的底座。

---

## 6. 知识供给机制（DSH 如何访问 wiki）

### 6.1 现状：对话页的"先找本地知识库"

- eager：`agent.py:185` 循环前 `bus.call_tool('search_kb', {'keyword': user_query})` 预检索注入；
- lazy：system prompt 引导 agent 循环中自行调用 `search_kb` / `websearch__web_search`；
- `search_kb` handler：`hybrid_search`（向量 0.7 + BM25 0.3）→ 返回 `slug/title/snippet/score/source`，personal 模式带公共库关键词兜底。

### 6.2 DSH 接入三层次

| 层次 | 做法 | 工作量 | 说明 |
|---|---|---|---|
| **L1（推荐）** | DSH MCP 客户端配置指向 `/mcp` | 配置级 | agent 会话内自动出现 `personllmwiki__search_kb` 等工具，行为与对话页 lazy 一致 |
| **L2（可选）** | DSH profile 提示词 / SKILL 引导「必先检索」 | 配置级 | 复刻对话页 eager 语义 |
| **L3（暂缓）** | PersonLLMWiki 侧加 `search_kb_full` 组合工具（检索+全文一次返回） | 小开发 | 实测 agent 检索质量不足再考虑 |

### 6.3 闭环（DSH 不只是消费者，还是生产者）

```
DSH agent 提问 → search_kb 检索 → read_wiki_page 读全文 → 回答
                                          ↓ 产出沉淀
              write_note / save_text_file → 知识库
              compile_wiki → 待审批 → approve_candidate
              submit_to_public → 共享公共库
```

全部由现有 MCP 工具拼成，无需新代码。

### 6.4 注意点

- Embedding 配额：每次 `search_kb` 消耗 PersonLLMWiki 侧配置的 Embedding API（public 实例需频控）；
- 检索依赖 Flask 进程常驻（索引内存化）：桌面端常驻满足，云上 public 实例常驻满足；
- 安全：`search_kb`/`read_wiki_page` 只读；`approve_candidate` 已注明「LLM 不应自动批量审批」，DSH 侧 prompt 同样约束。

---

## 7. 共享中心（知识 / MCP / Skills / 智能体）

### 7.1 共享对象分层

| 层 | 内容 | 能否共享 |
|---|---|---|
| 定义层 | 提示词、Skills、Workflow 脚本、场景/流程定义、MCP 工具包装、agent.json、脱敏配置 | ✅ 共享的就是这个 |
| 运行时层 | 正在跑的 goal、子代理、DSH profile/会话状态 | ❌ 单用户、会话态 |
| 数据层 | 聊天记录、个人知识库、API key、SAP token | ❌ 永不外传 |

> 结论：共享的是"文件/配置"，不是"运行实例"——这决定了所有机制都基于文件流转。

### 7.2 四种机制（从轻到重）

| 机制 | 做法 | 优点 | 缺点 | 阶段 |
|---|---|---|---|---|
| ① git 文件库 | 共享仓库 `shared/skills|workflows|agents/`，复用 `COMMON_GIT_REPO` 同步管道 | 零新基建、版本化 | 无发现能力 | **一期** |
| ② wiki 目录 | 每个共享 agent 写成带安装说明 frontmatter 的文章，走编译管道 | 复用检索+审批流+溯源 | 非机器可安装格式 | 一期 |
| ③ 一键安装市场 | 控制台「共享中心」tab：浏览 → 安装 → 复制/导入 | 低门槛，同事可用 | 需写轻量市场 UI | 二期 |
| ④ MCP 化 | agent 包装为 `service.json`（embedded/subprocess）发布，别人"连接"即用 | 零安装、跨客户端 | 只适合工具型/服务型 | 高级形态 |

### 7.3 统一 Manifest：agent.json（①③④ 的地基）

仿照 service.json 的"自包含文件夹 + 清单"模式：

```json
{
  "name": "annual-report",
  "version": "1.2.0",
  "type": "workflow | skill | scenario | goal-template",
  "requires_mcp": ["pdf-mcp", "sap"],
  "requires_llm": "claude",
  "requires_dsh": ">=0.1.0",
  "install": "copy-to | import | mcp-connect",
  "author": "zhang.san"
}
```

### 7.4 安全边界

- 共享仓库永不放：`.env`、API key、`mcp_servers.json` 认证段、个人数据（发布前密钥扫描，可挂 wiki 审批流）；
- 信任分级：公司公共实例官方库 > 同事发布 > 外部来源，安装时标注来源等级；
- 安装动作 = 执行代码，需用户确认（对齐 PRD 威胁模型）。

### 7.5 落地规格：共享仓库结构、manifest 定稿与安装映射（v0.5）

**共享仓库目录结构**（`COMMON_GIT_REPO` 同步，personal 模式）：

```
shared/
├── skills/            # SKILL.md 技能（目录包：SKILL.md + scripts/）
│   └── bom-picking/
├── workflows/         # DSH workflow 脚本（JS + meta）
├── agents/            # agent 定义（goal 模板/场景定义，含 agent.json）
│   └── annual-report/
├── mcp/               # MCP 服务定义（service.json，凭证留空）
│   └── websearch/
├── INDEX.md           # 索引（供共享中心浏览；wiki 编译入口候选）
└── README.md
```

**agent.json manifest（定稿，升级 §7.3 初版）**：

```json
{
  "name": "annual-report",
  "version": "1.2.0",
  "type": "skill | workflow | agent | goal-template | mcp-server",
  "description": "一句话说明（共享中心列表显示）",
  "requires_dsh": ">=0.1.0",
  "requires_mcp": ["pdf", "personllmwiki"],
  "install": {
    "kind": "copy-to | mcp-connect | import",
    "target": "skills/ | workflows/ | agents/ | mcp/"
  },
  "author": "zhang.san",
  "sources": ["wiki 概念 slug 或文档链接"]
}
```

- type 明确**五类**；install 由字符串升级为**对象（kind + target）**，机器可执行；
- 凭证类字段一律禁止（P0）。

**安装动作映射（共享中心「安装」→ 具体动作）**：

| install.kind | target | 动作 |
|---|---|---|
| copy-to | skills/ | 复制到 DSH skills（`$DSH_HOME/skills/`）或 PLW skills（`~/.personllmwiki/skills/`） |
| copy-to | workflows/ | 复制到 DSH workflow 目录 |
| copy-to | agents/ | 复制到 DSH agents 目录（goal 模板供实例化） |
| mcp-connect | mcp/ | 读 service.json → 生成 DSH `cordis.patch.yml` 条目（或 PLW builtin 注册） |
| import | — | 导入为 PLW 场景/任务定义（预留） |

**一期范围（UI 骨架）**：
- 侧边栏新增「共享中心」菜单 → 独立页面：**浏览**（读共享仓库 INDEX.md + 目录清单）→ **详情**（manifest 渲染：版本/依赖/来源等级）→ **安装**（按映射执行，用户确认）；
- 同步复用 `INSTANCE_MODE=personal` + `COMMON_GIT_REPO`（git 管道已有，共享中心只是 UI 化）；
- 发布（git 提交）与审批流（wiki 候选机制）留二期/三期。

---

## 8. 控制台改造

| 部分 | 决策 |
|---|---|
| 自研多智能体 `src/modules/tasks/` | **搁置**（不删代码，转需求文档；编排能力由 DSH goal/workflow/subagent 承接） |
| 定时自动化（APScheduler） | **保留薄壳**：表结构与运行记录不变；执行改为经 `dsh_bridge` 调 `dsh --profile headless "prompt"`（内部 react loop 作兜底）。**已验证 V2：dsh-schedule 是会话内提醒（无 cron 表达式、冷会话不执行），不能承担无人值守定时，薄壳结论不变** |
| MCP / Skills 管理界面 | **保留**（服务端工具注册、客户端总线、内置服务管理是 PersonLLMWiki 自身的职责） |
| 智能体场景定义 | 简化：场景/节点定义保留为"业务层"（审批流、业务语义），执行引擎不重复实现 |

---

## 9. 待验证项清单（Phase 0）

| # | 验证项 | 结论（2026-08-20 实测/源码查证） | 影响 |
|---|---|---|---|
| V1 | DSH 深链支持 | ✅ **已验证：不支持**。SPA 无 URL 路由（bundle 仅含 React 事件名）；`dsh web` 无 resume 参数；`dsh-session:<base64url>` 是模型侧跨会话快照引用（明确"No live link"），非 UI 导航 | §4.4 深链桥改为 **headless 桥**（见 4.4 修订） |
| V2 | dsh-schedule | ✅ **已验证：会话内提醒，非 cron**。`schedule_create/list/delete`；固定间隔 ≥5 分钟、**无日历/cron 表达式**；**冷会话不执行**（resume 后补发 overdue）；需显式装载插件 | §8 定时任务**保留 APScheduler 薄壳**；dsh-schedule 仅作未来会话内提醒补充 |
| V3 | iframe 能力 | 🔶 **部分验证**：DSH 上传走标准拖拽/文件输入（AttachmentRail/DropOverlay），WebView2 内预期可用；会话导出下载行为需 P2 实机测试 | 下载若异常 → 「在浏览器打开」兜底 |
| V4 | 插件 API 稳定性 | ⬜ 待验证：`dsh.client.inject` / UI slot 接口在 rc 阶段变化率 | 决定组件三投入 |
| V5 | 插件分发渠道 | ✅ 已解决：Nexus（hosted 托管插件包 + proxy 代理 npmjs），git 分发作回退 | 插件走 Nexus npm，`dsh plugin add` 接入 |
| V6 | 桌面打包体积 | 🔶 已量化：便携 Node ~50-80MB + dsh node_modules ~246MB + profile 依赖；可选裁剪 web profile | 决定是否捆绑、裁剪 |

---

## 10. 里程碑划分

| 阶段 | 内容 | 验收标准 |
|---|---|---|
| **P0 验证**（~1 周） | V1~V6 全部验证并记录结论 | 每项有结论，设计文档据实修订 |
| **P1 知识供给打通**（~1 周） | 本机配置 DSH MCP client 连 `127.0.0.1:5000/mcp`；验证 search_kb 在 DSH 会话可用 | DSH 会话内能检索并回答知识库问题 |
| **P2 桌面端 Plan B**（~2 周） | 模式切换壳（Wiki\|DSH 顶栏开关 + 单 iframe 全屏）+ dsh_bridge + 设置页 DSH 管理（关联/重装/更新）+ 侧边栏分组（§4.5） | 桌面端一个窗口内完成知识库+智能体（全模式切换），DSH 缺失时优雅降级 |
| **P3 共享 + 插件**（~2 周） | 共享中心一期（git + wiki 目录 + agent.json）+ DSH 插件 L1 | 同事可发布/安装共享 agent；`dsh plugin add` 一条命令接入知识库 |
| **P4 企微待办自动化**（~2 周） | 企微会话存档 MCP 服务 + todo 队列扩展 + 轮询领取 + DSH headless 执行（§13） | 每天自动拉取企微待办入库；待办被智能体自动认领执行并回写状态 |

> 实现快照（2026-08-20）：P2 的「关联已有 DSH / 启动 / 停止 / 更新检查」已落地；「重新安装（下载运行时）」「一键更新（换 app 留 home）」以及「token 替换文档化」仍归入后续里程碑（当前为文本引导降级，不影响优雅降级验收）。

---

## 11. 风险与依赖

| 风险 | 等级 | 缓解 |
|---|---|---|
| DSH 为 0.1.0-rc.6，插件 API / CLI 语法可能变化 | 中 | 所有 DSH 交互收敛于 `dsh_bridge.py`；版本门禁 + 降级提示 |
| DSH 单用户、无账号体系，无法做公司共享入口 | 高 | 共享的永远是"物"（知识/MCP/Skills/定义文件），运行实例不共享 |
| 双运行时（Python + Node）、双 LLM 配置 | 低 | 各自独立，互不干扰；桌面端统一入口 |
| iframe 兼容性（未来 DSH 可能加 CSP/X-Frame-Options） | 中 | shell 检测加载失败 → 「在浏览器打开」兜底 |
| Embedding/LLM 配额（public 实例被频繁调用） | 中 | search_kb 频控；compile_wiki 走审批 |
| 便携 Node + dsh 依赖体积 | 低 | 可选捆绑；裁剪 web profile 依赖 |

---

## 12. 决策清单（已拍板，2026-08-20）

| # | 决策点 | 选项 | 结论 |
|---|---|---|---|
| D1 | DSH server 命名（工具前缀） | `personllmwiki` / `zssnote` / 其他 | **`personllmwiki`**：品牌正式定为 PersonLLMWiki，同步改 mcp.json / service.json / 工具前缀；`zssnote` 视存量用户决定是否留别名 |
| D2 | P1 验证环境 | 本机 `127.0.0.1` / 云上 public 实例 | **本机先行**：带 token 场景一起测，通过后上云复测频控 / Embedding 配额 / git 同步 |
| D3 | 共享仓库位置 | 公司 git（复用 COMMON_GIT_REPO）/ 公共实例目录 | **git**（复用 COMMON_GIT_REPO） |
| D4 | 共享中心一期范围 | 仅 ①+② / 含 ③ 市场 UI | **①+②**（市场 UI 二期） |
| D5 | DSH 更新源 | 公司镜像 zip / npm registry / 并存 | **并存**：Nexus 管 npm 包（proxy npmjs + hosted 插件），公司镜像管运行时 zip |
| D6 | 便携 Node 捆绑 | 捆绑（同事可用）/ 不捆绑（仅开发者） | **捆绑作为可选兜底**：无 Node 同事走重新安装；开发者走「关联已有 DSH」 |
| D7 | 界面统一强度 | B 档（原样嵌入+缝合）/ C 档（功能重组） | **B 档** |
| D8 | 插件 UI slot | 做只读检索面板 / 纯 agent 会话内调用 | **先纯会话，面板二期** |
| D9 | DSH 最低版本门禁 | `>=0.1.0-rc.6` / 不设门禁只提示 | **软门禁 `>=0.1.0-rc.6`**：降级提示 + 可强制继续；版本号收敛到 dsh_bridge.py 单点维护 |
| D10 | 效率组形态 | 独立应用 / DSH 插件 / **PLW 侧边栏分组** | **侧边栏分组**（§4.5）：不拆应用、不做插件；能力经 MCP 工具互通（todo 已暴露 `create_todo`） |
| D11 | 企微待办自动化 | 纳入规划（§13） | **纳入 P4**：前提=企微会话存档可开通；执行分级（默认只读自动，写操作白名单/确认） |

---

## 13. 场景：企业微信待办 → 智能体自动执行（P4）

### 13.1 场景描述

每天定时从企业微信聊天记录拉取待办 → 写入 PLW todo（任务队列）→ 智能体轮询监控，发现符合自身能力的待办自动认领执行 → 结果回写。

### 13.2 链路（职责归属：PLW 采集/排队/调度，DSH 执行）

```
企业微信（会话内容存档 API）
  ↓ ① automation 定时任务（每天，APScheduler）
  ↓    拉取消息 → 解密 → LLM 提取待办
  ↓ ② 批量写入 PLW todo（create_todo + 来源标注）
todo 表 = 任务队列（SQLite）
  ↓ ③ automation 轮询任务（每 N 分钟）
  ↓    扫描 pending → 能力匹配 → 原子领取（claimed_by）
  ↓ ④ dsh_bridge.run_headless("执行任务 X")
DSH agent 执行（经 MCP 调 search_kb / write_note / SAP…）
  ↓ ⑤ 结果回写 todo（完成/失败）+ 知识库沉淀
```

### 13.3 组件清单

| 组件 | 类型 | 说明 |
|---|---|---|
| 企微会话存档 MCP 服务 | **新增**（service.json subprocess，仿 pdf-mcp/websearch 自包含模式） | 拉取+解密+消息解析；本身可共享（呼应共享中心） |
| 提取待办 automation 任务 | 复用现有 | prompt 描述提取规则；工具范围=企微服务 + `create_todo` |
| todo 表扩展 | **新增**字段 | `source`（来源标注）、`status` 扩展（pending/claimed/running/done/failed）、`claimed_by`、`claimed_at`、`task_ref`（关联执行记录） |
| 轮询+能力匹配任务 | 复用 automation | 新增"每 N 分钟"interval（现有配置放宽到分钟级） |
| 原子领取 | **新增** | `UPDATE ... WHERE status='pending'` 防并发抢单；执行幂等 |
| 执行状态记录 | **轻量复活** tasks 模块 `state_store` | 只取 L4 状态表（任务执行进度/结果/失败重试点），**不搬 orchestrator/router** |
| headless 执行 | 已实现 | `dsh_bridge.run_headless` + 回退 react loop |

### 13.4 关键约束

1. **企微会话存档有开通门槛**：需企业管理员开通 + 合规审批 + 可信 IP + RSA 密钥（企微官方解密 SDK）；聊天记录拉取受《个人信息保护法》约束。拿不到存档 API 时，退化为应用消息回调/群机器人（范围窄）；
2. **"实时"= 分钟级**：存档 API 是拉取模式，轮询 1~5 分钟是实际可达值；
3. **headless 无会话连续性**：多步任务依赖 §13.3 的执行状态表承载上下文与断点；
4. **自动执行分级**：默认只放行只读/低风险（检索、整理、生成草稿）；写操作（write_note、SAP）进白名单或执行前推送确认（对齐 PRD 威胁模型）。

### 13.5 验收标准（P4）

- 每天定时从企微拉取消息并提取待办入库（来源标注 `wecom`）；
- 待办被轮询任务认领（原子、无重复领取），匹配规则/LLM 描述可配置；
- DSH headless 执行成功/失败后，todo 状态与执行记录正确回写；
- 写操作默认不自动执行（白名单/确认）。
