# PersonLLMWiki × DeepSeek Harness 架构边界与升级指南

> 版本：v1.0（2026-08-21）｜ 本文是 **doc/ 的入口总览**：先读本文理解系统构成与边界，再按需查阅细节文档（见 §4 文档导航）。

---

## 1. 系统总览

本系统由**两个独立应用**组成，通过标准协议协作：

```
┌──────────────────────────────────────────────────────────┐
│ DeepSeek Harness（DSH）—— 执行编排层（Node 应用）           │
│  agent 会话 · goal/workflow/subagent · skills · 记忆       │
│  MCP 客户端（mcp__personllmwiki__* / mcp__pdf__* / ...）   │
└───────────────┬──────────────────────────────────────────┘
                │ MCP（JSON-RPC 2.0）/ headless CLI / iframe
┌───────────────┴──────────────────────────────────────────┐
│ PersonLLMWiki（PLW）—— 知识底座 + 能力网关（Flask 应用）     │
│  wiki 编译/检索/审批 · 文章图片 · 定时任务 · MCP Server 28 工具│
└──────────────────────────────────────────────────────────┘
```

- **PLW 管"内容与公司能力"**：知识生产、编译、检索、审批、SAP、定时调度；
- **DSH 管"干活"**：目标执行、多步编排、技能、记忆——通过 MCP 消费 PLW 的能力。

---

## 2. PLW 与 DSH 边界（五维）

| 维度 | PLW | DSH | 边界规则 |
|---|---|---|---|
| **职责** | 知识生产/供给/管理 + 公司特有工具 + 调度 | 执行/编排（goal/workflow/subagent/skills） | 知识供给 vs 执行消费 |
| **数据** | `~/.personllmwiki`（文章/wiki/图片/SQLite） | `$DSH_HOME`（sessions/profiles/credentials） | **永不相交**，各自备份升级 |
| **能力** | 公司特有：知识、SAP、审批流、todo、workspace | 通用：office、pdf、web 搜索（生态/直连） | 公司特有走 PLW 网关，通用归 DSH 侧 |
| **交互** | 被 MCP 调用 + 发起 headless | MCP 客户端 + headless CLI + iframe（模式切换壳） | 三条通道各司其职 |
| **配置** | 设置页（LLM/Embedding/资源/DSH 关联） | 自己的 profile/插件管理（`$DSH_HOME/profiles/*`） | 各管各的，互不写入 |

**三条交互通道**：

| 通道 | 协议 | 方向 | 场景 |
|---|---|---|---|
| 工具调用（主） | MCP JSON-RPC 2.0 | DSH → PLW `/mcp` | agent 检索知识库、写文章、调 SAP/Office |
| 进程调用 | headless CLI | PLW → DSH | 定时任务触发 `dsh --profile headless` |
| UI 嵌入 | iframe + postMessage | PLW 窗口 ↔ DSH web | 桌面端「Wiki \| DSH」模式切换壳 |

---

## 3. 升级指南

> 核心原则：**两个系统独立升级，互不耦合**——兼容性靠 MCP 标准协议保证，不靠版本绑定。

### 3.1 PLW 升级

| 方式 | 适用 | 步骤 |
|---|---|---|
| 安装包升级 | 非技术用户 | 下载新安装包（GitLab Release / releases 分支）→ 覆盖 `app\`，**保留 `resource\`** |
| 自更新 | 开发者 | `self_update.py`（git pull + pip install），或 `.\dev.ps1 restart` |

- **数据保护**：`~/.personllmwiki/` 与 `resource/` 升级时**永不覆盖**；
- PLW 升级不影响 DSH（两边数据目录独立）。

### 3.2 DSH 升级

| 路径 | 适用 | 步骤 |
|---|---|---|
| **npm 路径**（增量更新，主） | 有网络 | 设置页「检查更新」→「一键更新」→ 便携 node 自动 `npm install @deepseek-ai/dsh@latest` + **profile 同步** → 重启 DSH |
| **zip 路径**（首次安装/重装/离线） | 无网络/全新安装 | 设置页「重新安装」→ 下载运行时包（GitLab Release 资产 / Nexus raw）→ SHA256 校验 → 替换 `app\` 保留 `home\` → 重启 |

- **升级包自动制作**：npm 路径无需制作（官方直拉）；zip 路径由 `packaging/build_dsh_runtime.py` + CI 定时自动构建（检测到 npm 新版即发布），**无需人工盯**；
- **升级后必须重启 DSH**，新配置（MCP 客户端、技能）才生效；
- **版本门禁**：`dsh_bridge.py` 软门禁 `>=0.1.0-rc.6`，过低时降级提示；
- **回滚**：zip 路径重装旧版本 / npm 指定版本 `npm install @deepseek-ai/dsh@<旧版>`。

### 3.3 升级顺序与兼容性

- **任意顺序均可**：PLW 升级不影响 DSH，反之亦然；
- DSH 为 **rc 快速迭代**：插件 API / CLI 语法可能变化 → 所有 DSH 交互收敛于 `dsh_bridge.py`（PLW 侧唯一入口），变化集中一处处理；
- MCP 工具面（`mcp__personllmwiki__*`）由 PLW 侧 28 工具注册表决定，DSH 升级不改变它们。

### 3.4 DSH 升级后的验证清单

1. 设置页 DSH 状态卡显示新版本、`DSH 在线`；
2. 新会话里 `mcp__personllmwiki__search_kb` 等工具可用；
3. 知识库 SKILL（`knowledge-base`）在技能目录可见；
4. 桌面端「DSH 模式」切换正常。

---

## 4. doc/ 文档导航

| 文档 | 定位 | 说明 |
|---|---|---|
| **本文** | 入口总览 | 边界 + 升级 + 导航 |
| DSH集成架构设计方案.md | 架构细节（v0.4） | 三件套、知识供给、共享中心、里程碑、决策清单 |
| DSH集成-变更实施说明.md | 实施流水账 | §10.x 变更逐项 + 完成状态速览 + 裁剪计划（§10.9） |
| PersonLLMWiki设计规范.md | PLW 设计索引 | 各模块设计文档入口（原 DESIGN.md，已按品牌重命名） |
| 分发部署方案.md | PLW 打包分发 | Embedded Python / 安装包 / 升级.bat |
| 开发者打包发布指南.md | 发布流程 | 打包、Release、GitLab 发布 |
| 用户使用指南.md | 用户手册 | 桌面端 / Web 使用说明 |
| ZSSNote_MCP_设计方案.md | MCP 深度设计 | 28 工具、双角色、内置服务（品牌名已标注更新） |
| 对话页/工作台/阶段组件 等 | 子模块设计 | 按 PersonLLMWiki设计规范.md 索引查阅 |
| archive/（新增） | 归档区 | 已搁置/已完成的文档移入，git 历史保留 |

---

## 5. 常见问题

1. **DSH 和 PLW 谁的版本新？** 无关——独立升级；DSH 看 npm latest，PLW 看 VERSION。
2. **升级 DSH 会丢我的对话吗？** 不会——会话在 `$DSH_HOME/sessions`，升级只动 `app\`（zip 路径）或包（npm 路径），`home\` 保留。
3. **为什么 SAP 只能在 PLW 里调？** 公司数据走 PLW 网关（默认禁止、白名单授权），不进第三方插件。
4. **office/pdf 用谁的？** 通用能力归 DSH 侧：office 用 OfficeCLI 官方 SKILL/MCP，PDF 用 `@modelcontextprotocol/server-pdf`（或自研直连）；PLW 侧保留为"能力供给兼容层"（见变更说明 §10.9 裁剪计划）。
