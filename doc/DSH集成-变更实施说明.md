# DSH 集成 - 变更实施说明（v0.1 → v0.4）

> 用途：本文件是给 **Trae**（或其他编码 Agent）的增量实施指令，请先阅读《DSH集成架构设计方案.md》（v0.4）相关章节，再按本文件逐项实施。
> 基线：当前代码已由 Trae 按 v0.1 方案实现并提交（commit `2f47a30`~`1d53810`，工作树干净）。
> 原则：**只改变更涉及的部分，未变更功能一律不动**；每项变更附验收标准，实施完成后逐项自检。

## 完成状态速览（2026-08-21）

| 节 | 内容 | 状态 |
|---|---|---|
| §10.4 | shell 修复 + 菜单排序 | ✅ `e11ace4` |
| §10.5 | 无损瘦身 | ✅ `2c8cf52` |
| §10.6 | 控制台拆解 | ✅ `3626463` |
| §10.7 | 设置页 DSH 重装/更新 | ✅ `c46eceb` |
| §10.8 | dsh-runtime 构建脚本 | ✅ `8d3a3cb`（模式 A，GitLab 写路径恢复后跑全链路） |
| P1 | 知识供给打通 | ✅ 2026-08-21：MCP 客户端配置（`$DSH_HOME/profiles/web/cordis.patch.yml` 用 `insert:` 语法）+ 知识库 SKILL（`$DSH_HOME/skills/knowledge-base/SKILL.md`，watcher 实时生效） |
| §10.9 | 有损裁剪计划 | 📋 规划中（C1~C7 清单 + 触发条件，未执行）；2026-08-21 触发条件已核对：均未满足，暂缓 |

---

## 0. 变更背景（一句话）

v0.1 把 DSH 做成了 PersonLLMWiki SPA 里的一个页面（侧边栏「智能体」→ `/agent`，iframe 嵌 DSH web）。
v0.2 改为 **Trae 式全模式切换**：桌面窗口顶层加一条 ~36px 模式条，`[Wiki | DSH]` 分段开关，单 iframe 占满整个窗口，每次只显示一个全屏应用，各自保留原生风格。

```
┌────────────────────────────────────────────────┐
│ ⚡ PersonLLMWiki  │  Wiki │ DSH  │  ● DSH 在线   │ ← 36px 顶栏（新增 shell 唯一 chrome）
├────────────────────────────────────────────────┤
│                                                │
│   <iframe> 100%×100%                            │
│   Wiki 模式 → http://127.0.0.1:{port}/         │
│   DSH 模式  → http://127.0.0.1:{dsh_url}       │
│                                                │
└────────────────────────────────────────────────┘
```

---

## 1. 变更总览

| # | 文件 | 动作 | 摘要 |
|---|---|---|---|
| 1 | `src/desktop.pyw` | 改 | webview 加载 `/shell` 页面（替代直接加载 Flask 根 URL）；托盘菜单加「切换 Wiki/DSH」 |
| 2 | `src/modules/agent/routes.py` | 改（小） | 新增 `GET /shell` 路由渲染 shell 页（复用 agent 模块，避免新 Blueprint） |
| 3 | `src/modules/agent/templates/shell.html` | **新增** | 模式条 + 单 iframe 全屏切换页 |
| 4 | `src/modules/agent/templates/agent.html` | 改（文案） | 术语「智能体 Tab」→「DSH 模式」；页面保留（Web 浏览器模式仍作 DSH 入口） |
| 5 | `src/templates/base.html` | 改（小） | 侧边栏「智能体」菜单保留但文案改为「DSH 模式」；或保留原样（见 §3 决策） |
| 6 | `src/common/dsh_bridge.py` | 改（注释/文案） | 代码逻辑**不改**；docstring 中「智能体」Tab → 「DSH 模式」 |
| 7 | `tests/desktop/test_dsh_bridge.py` | 不动 | 桥接层逻辑未变 |
| 8 | `src/common/automation_runner.py` | **不动** | headless 优先 + react loop 回退已符合 v0.2（V2 已验证 dsh-schedule 不能替代 cron） |
| 9 | `src/templates/base.html` + `src/static/css/index.css` | 改 | 侧边栏「知识组 / 效率组」分组（§6） |

---

## 2. 变更 1：桌面壳（`src/desktop.pyw`）

**现状**：`webview.create_window(url=f"http://127.0.0.1:{port}")` 直接加载 Flask 根 URL；端口已固定 5000（`common.desktop_prefs.get_port/set_port`，被占用回退动态端口并持久化）。

**改为**：

1. 窗口 URL 改为 `f"http://127.0.0.1:{port}/shell"`（其余窗口/托盘/单实例/图标逻辑不动）。
2. 托盘菜单追加「切换 Wiki/DSH 模式」项（复用现有 `TrayManager` 回调机制；回调通过 `window.evaluate_js` 或新增 `js_api` 调用 shell 页的切换函数）。理由：iframe 聚焦时键盘事件不冒泡到父页面，**纯前端快捷键在 iframe 内无效**，托盘是可靠的兜底入口。
3. 保留：单实例、X 最小化、托盘启停、端口探测逻辑全部不动。

**验收**：
- [ ] 桌面端启动后窗口显示 shell 顶栏 + Wiki 模式全屏 PersonLLMWiki
- [ ] 托盘菜单「切换 Wiki/DSH」可来回切换，且与顶栏开关状态一致

---

## 3. 变更 2：shell 路由（`src/modules/agent/routes.py`）

**现状**：仅 `/agent`（render agent.html）、`/api/agent/status`、`/api/agent/start`。

**改为**：新增：

```python
@agent_bp.route('/shell')
def shell():
    """桌面壳：Wiki/DSH 模式切换页（v0.2）。"""
    return render_template('shell.html', active_view='shell')
```

**验收**：浏览器访问 `http://127.0.0.1:5000/shell` 返回 shell 页（非 404）。

---

## 4. 变更 3：新增 `src/modules/agent/templates/shell.html`

**实现规格**（独立于 PersonLLMWiki 现有样式体系，使用内联/独立 `<style>`，不依赖 base.css）：

1. **布局**：固定顶栏（高 36px，flex）+ 下方 iframe 填满剩余空间（`width:100%; height:calc(100vh - 36px); border:none`）。
2. **顶栏内容**（左→右）：
   - 品牌文本 `PersonLLMWiki`（小号、弱色）
   - 分段开关：`Wiki | DSH`（两个按钮，选中态高亮）
   - 右侧 DSH 状态点：绿=在线 / 灰=未装 / 黄=版本过低 / 红=未运行，标题悬浮提示状态文案
3. **iframe 行为**：
   - Wiki 模式 src = `{{ request.host_url }}`（Flask 根）；DSH 模式 src = 状态接口返回的 `url`（`/api/agent/status` 的 `url` 字段）。
   - **懒加载**：页面加载只挂 Wiki iframe；首次切到 DSH 才设置 DSH iframe 的 src；之后切换用 CSS `display` 显隐（两个 iframe 常驻，状态保留、无刷新闪烁）。
   - 两个 iframe 均设 `allow="clipboard-read; clipboard-write"`（对齐现有 agent.html 的 allow 配置）。
4. **状态与降级**：启动时轮询 `/api/agent/status`（2s 间隔，3 次后改为 10s）：
   - `running` → 开关 DSH 侧可用，状态点绿；
   - `not_running` → 开关可点（点击先调 `/api/agent/start`，失败再显示占位）或直接禁用并显示「去设置」，状态点红；
   - `not_installed` / `version_low` → 开关 DSH 侧禁用，状态点灰/黄，点击提示「请到 设置 → DeepSeek Harness 关联或安装」并给出跳转链接 `/settings`（复用 agent.html 的占位文案风格）。
5. **模式记忆**：localStorage 键 `dsh_shell_mode`（`wiki` / `dsh`），加载时恢复；shell 与 Flask 同源，localStorage 可用。
6. **键盘快捷键**：window 级 `keydown` 监听 `Ctrl+Shift+M` 切换（注意：iframe 聚焦时无效，属已知限制，托盘菜单为兜底）。
7. 禁止在 shell 中引入 `base.html` 继承（shell 是全屏壳，不与 SPA 布局混用）。

**验收**：
- [ ] 切到 DSH 模式全屏显示 DSH web（3080），切回 Wiki 再切回 DSH **不重新加载**（状态保留）
- [ ] DSH 未安装时开关禁用并引导去设置页
- [ ] 重启桌面端回到上次模式
- [ ] 顶栏高度 ≤ 40px，两模式均无滚动条/白边

---

## 5. 变更 4：文案术语统一

| 位置 | 现状 | 改为 |
|---|---|---|
| `agent.html` 占位/提示文案 | 「智能体 Tab 需要 DeepSeek Harness…」 | 「DSH 模式需要 DeepSeek Harness…」 |
| `dsh_bridge.py` docstring | 「智能体」Tab | DSH 模式 |
| `settings.html` 区块描述 | 「为「智能体」Tab 提供能力」 | 「为桌面端 DSH 模式提供能力」 |
| `base.html` 侧边栏 | 「智能体」菜单 | 保留菜单但文案改「DSH 模式」（桌面端下此菜单仍指向 /agent，Web 模式降级入口；**若你认为重复，可改为 `target="_blank"` 打开 /shell，二选一，默认保留原样仅改文案**） |

**验收**：全局无「智能体 Tab」残留文案（grep 校验）。

---

## 6. 明确不动（防止误改）

- `src/common/dsh_bridge.py` 全部逻辑（状态机/版本门禁/防 SSRF/启停/headless/check_update）
- `src/common/automation_runner.py`（headless 优先 + 回退已符合 v0.2）
- `src/bin/mcp/personllmwiki/service.json`（embedded MCP 服务注册）
- 设置页「DeepSeek Harness」区块的 API 与保存逻辑（`/api/settings/dsh*` 路由不动）
- `desktop.pyw` 的：单实例、托盘、X 最小化、端口探测、MCP launcher 子进程入口
- 所有 MCP 工具注册与 wiki 编译/检索代码

---

## 7. 实施顺序建议

1. `routes.py` 加 `/shell` 路由 → 2. 写 `shell.html`（可先在浏览器验证）→ 3. 改 `desktop.pyw`（窗口 URL + 托盘切换项）→ 4. 文案统一 → 5. 跑 `tests/desktop/test_dsh_bridge.py` 确认无回归 → 6. 手动验收（§2~§5 的验收清单）。

## 8. 关联文件（供参考）

- 设计文档：`doc/DSH集成架构设计方案.md`（§4.1 桌面壳模式切换、§4.2 dsh_bridge、§4.4 headless 桥、§4.5 侧边栏分组、§9 验证结论、§13 企微待办场景）
- 现有实现参考：`src/modules/agent/templates/agent.html`（状态检测/占位逻辑可复用）、`src/common/dsh_bridge.py`

---

## 9. 变更 6：PLW 侧边栏分组（知识组 / 效率组）

> ⚠️ **已撤销（2026-08-21）**：该分组已由 v0.3 提交 `826cbd2` 实现，但用户反馈菜单栏出现「知识组/效率组」文字不符合预期，**本变更整体回退**（见 §10 修复指令）。本节仅留档。
> 背景：v0.3 定案——效率组（todo/automation 等）**不拆独立应用、不做 DSH 插件**，仅做 PLW 侧边栏分组（设计文档 §4.5）。

**目标文件**：`src/templates/base.html`（侧边栏结构）、`src/static/css/index.css`（分组样式）。

**规格**：

1. 侧边栏按两组渲染（组标题 + 可折叠，默认知识组展开、效率组展开）：
   - **知识组**：知识库 / 文章 / 图片 / 对话
   - **效率组**：待办 / 自动化 / 笔记
   - 底部（不分组）：控制台(MCP/Skill) / 设置
2. 只调整导航层（HTML 结构 + CSS 分组标题/折叠箭头），**不改任何模块路由与页面代码**；
3. 折叠状态用 localStorage 持久化（键 `sidebar_group_*`）；
4. 保持现有「智能体/DSH 模式」菜单项原样（若 v0.2 决策为保留）——它不属于任何组，可放在底部区；
5. **隐藏「任务(/tasks)」菜单**：该模块（自研多智能体）v0.1 已搁置，编排由 DSH 承担；路由保留，仅移除侧边栏入口（若当前侧边栏已无此项则跳过）。

**验收**：
- [ ] 侧边栏显示「知识组 / 效率组」标题，可独立折叠，刷新后记住状态
- [ ] 所有模块入口位置正确、跳转无回归
- [ ] 模块页面代码零改动（git diff 仅 base.html / index.css）

---

## 10. 修复指令：统一入口 + 侧边栏清理（2026-08-21，替代 §9）

> **背景**：v0.3（`826cbd2`）实现后用户反馈：①「品牌 + Wiki|DSH 分段开关」根本看不到——根因是该开关只存在于桌面壳 `/shell`，浏览器访问 `/` 时进的是 SPA 本身；②侧边栏出现「知识组/效率组」分组文字，不符合预期。
> **目标**：无论桌面端还是浏览器，打开应用入口都先见「36px 顶栏（品牌 + Wiki|DSH 开关 + DSH 状态点）」；侧边栏恢复平铺、无分组文字。

### 10.1 实施步骤

1. **回退 v0.3 分组**：`git revert --no-commit 826cbd2`（恢复 `base.html` 至 v0.2 状态，删除 `src/static/css/components/sidebar.css` 及其引用）。**保留** v0.2 提交 `ce0a2c6` 的 shell 壳/托盘切换/desktop.pyw 改动。

2. **统一入口**（`src/modules/home/routes.py`）：
   - imports 增加 `redirect, url_for`；
   - `@home_bp.route('/')` 改为 `return redirect(url_for('agent.shell'))`（浏览器访问 `/` 也进 shell 壳）；
   - 原 `home()` 工作台逻辑迁移到新路由 `@home_bp.route('/home')`（仍 `render_template('home.html', active_view='home')`）。

3. **修正链接防 iframe 嵌套**：
   - `src/templates/base.html`：工作台 `href="/"` → `href="/home"`；
   - `src/modules/agent/templates/shell.html`：`iframe-wiki` 的 `src="{{ request.host_url }}"` → `src="{{ url_for('home.home') }}"`（避免 iframe 加载 `/` 再次进入 shell）。

4. **侧边栏清理**（`base.html`，回退后处理）：
   - 删除「任务(`/tasks`)」菜单项（路由保留）；
   - 删除「DSH 模式(`/agent`)」菜单项（顶栏开关已取代；`/agent` 路由与页面代码保留不删）；
   - 最终侧边栏平铺：工作台 / 对话 / 文章 / 待办 / Wiki / 图片 / 控制台 / 笔记 / 设置（按 v0.2 实际结构为准）。

### 10.2 禁止改动

`dsh_bridge.py`、`automation_runner.py`、`desktop.pyw` 的托盘/单实例/端口逻辑、shell.html 的 v0.2 样式与交互（36px 顶栏、分段开关、状态点、懒加载、localStorage 记忆、mask 降级）——**仅改 iframe src 一处**。

### 10.3 验证清单

- [ ] 浏览器打开 `http://127.0.0.1:5000/` → 地址栏跳转 `/shell`，看到顶栏「品牌 + Wiki|DSH 开关 + 状态点」，iframe 显示工作台
- [ ] 顶栏切 DSH → 全屏 DSH（未装则占位 + 去设置引导）
- [ ] SPA 内点「工作台」→ 停留 iframe 内（URL `/home`），不跳出 shell
- [ ] 侧边栏无「知识组/效率组」文字、无「任务」、无「DSH 模式」菜单项
- [ ] 桌面端托盘「切换 Wiki/DSH」仍可用
- [ ] `git diff` 仅涉及 `home/routes.py`、`base.html`、`shell.html`（一行）、删除 `sidebar.css`；`tests/desktop/test_dsh_bridge.py` 通过

---

## 10.4 补充修复：shell.html 已知问题 + 菜单排序（2026-08-21）

> 状态：§10 已由 Trae 实施并提交（`956530d`）。本节为后续新增：**shell.html 的 4 个 bug + Wiki 模式侧边栏菜单排序**。只动 `src/modules/agent/templates/shell.html` 与 `src/templates/base.html`（排序）；**禁止改动** `dsh_bridge.py`、`automation_runner.py`、`desktop.pyw`、`home/routes.py`。

### A. shell.html 修复（4 处）

1. **A1 启动遮罩闪烁**：新增 `var statusLoaded = false;`；`applyMode()` 遮罩显隐改为 `els.mask.classList.toggle('show', statusLoaded && dshOn && !canUseDsh());`；`refreshStatus()` 成功回调中、`applyMode()` 前设 `statusLoaded = true;`。效果：状态返回前不显示遮罩。
2. **A2 启动后自动切 DSH**：`startDsh()` 成功分支改为 `currentMode = 'dsh'; refreshStatus();`（内部 applyMode + 懒加载 iframe）；失败分支保持现状。
3. **A3 移除无效属性**：删除 `.shell-bar` 的 `-webkit-app-region: drag;` 及 `.shell-seg`、`.shell-status` 的 `-webkit-app-region: no-drag;`（PyWebView 不识别）。
4. **A4 无障碍**：`#seg-wiki`/`#seg-dsh` 补 `role="tab"` 与 `aria-selected`；`updateSeg()` 中同步 aria-selected。

### B. Wiki 模式侧边栏菜单排序（base.html）

- 当前：工作台 / 对话 / 文章 / 待办 / Wiki / 图片 / 控制台 / 笔记 / 设置
- 目标：工作台 / 对话 / **Wiki** / 文章 / 图片 / 待办 / 控制台 / 笔记 / 设置
- 只调整 `<a data-nav>` 节点顺序，不改路由/文案/样式。

### C. 验证清单

- [ ] 切 DSH 后刷新无"未检测到"遮罩闪烁（直接显示 DSH）
- [ ] DSH 未运行点开关 → 启动成功后自动切入 DSH
- [ ] 无 `-webkit-app-region` 残留
- [ ] 切换模式时 `aria-selected` 同步
- [ ] 侧边栏顺序：工作台 / 对话 / Wiki / 文章 / 图片 / 待办 / 控制台 / 笔记 / 设置
- [ ] `git diff` 仅 `shell.html` + `base.html`；`tests/desktop/test_dsh_bridge.py` 通过

---

## 10.5 无损瘦身（2026-08-21）

> 原则：只动入口/界面，**不动任何业务代码与路由逻辑**；每项都可随时回滚。目标文件：`src/modules/automation/templates/automation.html`、`src/modules/agent/routes.py`、`src/modules/agent/templates/agent.html`（删除）。

### 实施项

1. **控制台移除 Skill tab**（执行侧技能已由 DSH 接管）：
   - `automation.html` 删除 `data-tab="skill"` 的 tab 按钮及其 Tab Pane；
   - `common/skill_loader.py` 代码**保留不删**（未来共享中心可能复用）。
2. **控制台移除「agent」tab**（若其指向已搁置的 tasks/场景管理——先检查其 pane 内容，确认无实际功能再删；如有在用功能则保留并说明）。
3. **`/agent` 页面改为重定向**（统一入口后它已无侧边栏入口，仅作旧书签兼容）：
   - `agent/routes.py`：`/agent` 路由改为 `return redirect(url_for('agent.shell'))`；
   - 删除 `templates/agent.html`；
   - **必须保留**：`/api/agent/status`、`/api/agent/start`（shell.html 正在使用）、`/shell` 路由。
4. **tasks 残留确认**：`/tasks` 路由保留、侧边栏入口已删，确认无死链（grep `href="/tasks"` 应为空）。
5. **天气/计划/文件夹**：已确认不在侧边栏（现状如此），仅当仪表盘或其他页面存在入口时加 feature flag 默认隐藏（路由保留）；无入口则跳过。

### 禁止改动

`dsh_bridge.py`、`automation_runner.py`、`desktop.pyw`、`home/routes.py`、`shell.html`（§10.4 已修完）、MCP 工具注册、wiki 编译/检索代码。

### 验证清单

- [ ] 控制台仅剩「自动化 + MCP」两个 tab（+ 确认 agent tab 处置）
- [ ] 浏览器访问 `/agent` → 跳转到 `/shell`
- [ ] shell 页状态接口（`/api/agent/status`、`/api/agent/start`）正常
- [ ] 侧边栏/页面无 `/agent`、`/tasks` 死链
- [ ] `git diff` 仅涉及 automation.html、agent/routes.py、删除 agent.html；`tests/desktop/test_dsh_bridge.py` 通过

---

## 10.6 控制台拆解：自动化独立成页 + MCP 并入设置（2026-08-21，单独一轮）

> 背景：§10.5 移除 Skill/agent tab 后，「控制台」只剩「自动化 + MCP」两个 tab。本轮拆掉「控制台」页面本身：**自动化独立为侧边栏菜单页**；**MCP 作为配置并入设置页「能力供给」区块**。接口层（`/api/automation/*`、`/api/mcp/*`）全部不动，纯前端重组，可回滚。

### A. 自动化独立成页

- `automation.html`：去掉 tab 壳（`am-tabs`/`switchTab`），「自动化」tab pane 直接成为页面主体（任务列表 / 创建 / 运行记录 / 手动触发原样保留）；
- `base.html` 侧边栏：菜单项「控制台」→「自动化」（`href="/automation"` 不变）；
- 相关 JS 依赖 `switchTab` 的调用相应简化。

### B. MCP 并入设置页

- 将「MCP」tab pane 的 HTML 与对应 JS 迁移到 `settings.html`，新增「能力供给」区块（置于 LLM / Embedding 区块之后）；
- `settings/routes.py` 补充区块所需上下文（`skills_dir` 等字段已存在）；
- ⚠️ `src/modules/mcp/client_routes.py` 的 REST 接口（`/api/mcp/servers` 等）**不动**，仅迁移前端挂载点。

### C. Skills 处置（不建管理页）

- **运行**：chat agent 仍自动注入技能（`common/agent.py` `match_skill`），技能文件放 `~/.personllmwiki/skills/` 即生效，**不需要管理 UI**；
- **共享**：技能流转归共享中心（git 仓库 → 安装到本地 skills 目录），`common/skill_loader.py` 保留作为格式校验/复用件；
- **DSH 执行侧**：DSH profile 内技能由 DSH 自己管理。

### 禁止改动

`/api/automation/*`、`/api/mcp/*` 路由与 handler、`dsh_bridge.py`、`automation_runner.py`、`desktop.pyw`、`home/routes.py`、`shell.html`。

### 验证清单

- [ ] 侧边栏「自动化」直达任务管理页（无 tab 壳，任务 CRUD / 运行记录 / 手动触发正常）
- [ ] 设置页「能力供给」区块完整展示 MCP 服务与工具（增删改查正常）
- [ ] `/api/automation/*`、`/api/mcp/*` 无回归
- [ ] 全站无「控制台」残留死链（grep）
- [ ] `git diff` 涉及 `automation.html`、`settings.html`、`settings/routes.py`、`base.html`；`tests/desktop/test_dsh_bridge.py` 通过

---

## 10.7 设置页 DSH 区块补全：「重新安装」+「一键更新」（2026-08-21）

> 背景：设计文档 §10 实现快照标注的欠账——当前仅有「关联已有/启动/停止/检查更新」，「重新安装」「一键更新」为文本引导降级。
> **分发渠道决策（2026-08-21）**：dsh-runtime zip 走 **GitLab Release 资产**（与 PersonLLMWiki 安装包分发习惯一致）；文件体兜底 **Nexus raw `nexus_pub_hosted_repo`**（上传 204 / 匿名下载 200 已验证）。
> **GitLab 上传限制（诊断中）**：Release 资产上传受 `gitlab_rails['max_attachment_size']`（默认 10MB）+ `nginx['client_max_body_size']`（默认 250m）限制；改对这两项后 direct asset 可传；**未解前用外部链接资产（文件体放 Nexus raw）兜底**。我的环境（HTTP API 401 / HTTPS 不可达）无法进一步验证，需在内网确认 GitLab 版本与报错码（413→nginx / 422→max_attachment_size）。
> **网络前提（已确认）**：内网可访问外网 npmjs（实测成功但慢）→ 增量更新走 npm；首次/重装走 zip（内网快）。

### A. 一键更新（按场景选路径）

1. **zip 路径（首次/重装/离线，主）**：下载 `DSH_MIRROR_URL`（默认 GitLab Release 资产 URL 或 Nexus raw URL，二选一可配）→ 校验 SHA256 → 解压替换 `app\`、保留 `home\`；
2. **npm 路径（增量更新）**：用捆绑的便携 node 执行 `npm install @deepseek-ai/dsh@latest`（cwd = `%LOCALAPPDATA%\DeepSeekHarness\app\`，app 目录需含 `package.json` 声明 `@deepseek-ai/dsh` 依赖），registry 可配（默认 npmjs 直连；Nexus npm proxy 建好后可切）；完成后执行 **profile 同步**（`dsh plugin --profile web` 或重初始化）；
3. **下载源配置化**：`DSH_MIRROR_URL` 默认 `https://gitlab.xiangyuniot.com/AiTeam/personllmwiki/-/releases/download/` + 文件体 URL（direct 资产走 GitLab，link 资产走 Nexus raw）；**配置为空时降级为现有文本引导**；
4. **版本检查双源**：「检查更新」优先 npm latest（实时）；zip 场景查 GitLab Release API（列最新 tag 及其资产），Nexus 兜底场景读 `dsh-runtime-latest.json`。

### B. 重新安装

- 下载运行时 zip（同上源）→ 解压到 `%LOCALAPPDATA%\DeepSeekHarness\`（`app\` + `home\` 初建）→ 自动关联 → 首次启动初始化 web profile。

### 禁止改动

`dsh_bridge.py` 的状态机/版本门禁/健康检查逻辑（仅可新增下载/更新函数，不得改动现有 `get_status`/`start`/`stop`/`run_headless`/`check_update` 行为）、`automation_runner.py`、`desktop.pyw`、`shell.html`。

### 验证清单

- [ ] 「检查更新」在有网机器返回 npm latest（实时）；zip 场景返回 GitLab Release 最新 tag 资产（或 Nexus `dsh-runtime-latest.json` 兜底）
- [ ] 「一键更新」npm 路径：`app\` 内包版本提升、`home\` 会话保留、DSH 重启后可进
- [ ] zip 路径：SHA256 校验失败拒绝安装；`home\` 不被覆盖
- [ ] 下载源留空时回退文本引导，无报错
- [ ] `tests/desktop/test_dsh_bridge.py` 通过

---

## 10.8 DSH 运行时包自动重建与上传（2026-08-21）

> ✅ **已实现 2026-08-21**：`packaging/build_dsh_runtime.py`（模式 A 为主），dry-run 验证通过（npm latest=0.1.0-rc.7，GitLab 无 dsh-runtime Release → 待构建）。完整构建+上传需等 GitLab 写路径恢复（磁盘满阻塞中）。用法：`set GITLAB_TOKEN=xxx && python packaging/build_dsh_runtime.py [--dry-run] [--mode A|B] [--version X]`；凭证全走环境变量；模式 B（Nexus raw）扩展位已留。
> 背景：zip 快照无法"实时"，但**首次安装/离线**场景仍需它。本项把打包上传自动化：检测到 npm 新版本即自动构建 zip 并发布到 **GitLab Release**——准实时、零人工。

### 实施（`packaging/build_dsh_runtime.py` + GitLab CI）

1. 查 npm latest `@deepseek-ai/dsh` 版本 vs GitLab Release 最新 tag；无新版则退出；
2. 构建 `app\`（便携 node + `@deepseek-ai/dsh` + 依赖 + `package.json`）→ 打 zip → 生成 SHA256；
3. 发布到 GitLab Release（GitLab CI 内 `release-cli`，**首选 direct asset**）：
   - 模式 A（direct asset，需上传限制已解）：`release-cli create --tag-name vX --assets "path=./dsh-runtime-vX.zip"`；
   - 模式 B（外部链接，限制未解时兜底）：zip 先传 Nexus raw（`POST /service/rest/v1/components?repository=nexus_pub_hosted_repo`，凭证环境变量）→ `release-cli create --assets-links --url <Nexus URL> --name dsh-runtime-vX --link-type other`；
4. 触发：GitLab CI **schedule**（如每 6 小时）+ 手动触发。

### 验证

- Release 页可见资产（direct 或 link），下载 URL 可访问、SHA256 一致；
- 离线/首次安装机器用 zip 路径「重新安装/一键更新」可用。

### 备注

- **GitLab 上传限制修复**（用户侧）：`gitlab_rails['max_attachment_size']`（MB）+ `nginx['client_max_body_size']` → `gitlab-ctl reconfigure`；需管理员权限，报错码 413→nginx 层、422→应用层；
- Nexus npm proxy 降级为**可选**（内网可直连外网，仅加速）；`build_dsh_runtime.py` 构建时如需加速可临时指 registry 到 proxy。

### 阻塞记录：GitLab 写路径 500（运维处理中，2026-08-21）

> **症状**：GitLab Release 资产上传失败。实测（root 与 zhusa/非 admin Owner 两个 PAT 均复现）：读操作✅ / 文件上传（`/uploads`）✅ 201 / **任何 DB+git 写操作（建 issue、建 tag、建 Release、改 Release 资产）❌ 500**——实例级写路径故障。
> **根因**：疑似**磁盘满**（近一月上传多个 linux-arm BSP 大文件，运维已介入处理，待通知）。
> **已排除**：上传大小限制（attachment=10000 已生效）、HTTP Basic Auth（16.1.2-jh 禁用，与 500 无关）、root 账号（非 root Owner 同样 500）、维护模式（未开启）。
> **待复测（运维处理后）**：① 建 tag → ② 建 Release → ③ 加资产链接 → ④ 上传正式 dsh-runtime zip（direct 或外部链接）。
> **不阻塞**：Nexus raw 通道已验证（上传 204 / 匿名下载 200）；§10.8 按模式 B（文件体 Nexus raw + Release 挂链接）先行；GitLab 恢复后切模式 A（direct asset）零成本。
> **遗留**：项目 606 uploads 下有探测文件 `gl-upload-probe.txt`（30 字节，无删除 API，无害）。

---

## 10.9 有损裁剪计划（2026-08-21，规划中，非立即执行）

> 原则：**先隐藏后删除**；**替代者确认可用才动**；每项可回滚（git 历史保留）；开工前更新本节触发条件核对表。
> 背景：DSH 集成验证后，PLW 中与 DSH 能力重叠/低价值的模块进入裁剪通道。当前均**未执行**，仅规划。

### 裁剪项清单

| # | 项 | 现状 | 目标 | 触发条件 | 验证方式 | 优先级 |
|---|---|---|---|---|---|---|
| C1 | **officecli 退役**（28 工具中 9 个 Office 工具 → 19） | PLW vendored v1.0.143 + `tools_office.py` + `bin/mcp/officecli` | 从 /mcp 暴露面移除；PLW 降级薄壳 → 退役 | ①确认**无非 DSH 用户**在用 ②DSH 侧 OfficeCLI 官方 SKILL/MCP 实测通过 ③上游二进制先升 v1.0.144 过渡 | 同事入口无回归；DSH 独立完成文档读写（SKILL 方式） | P1 |
| C2 | **chat 收敛 RAG 问答** | 全量 agent（LLM+MCP 编排） | 知识问答优先（search_kb/websearch）；通用编排引导去 DSH 模式 | §10.7 一键更新/headless 桥稳定运行后 | 对话页知识问答正常；日常编排走 DSH | P1 |
| C3 | **automation 执行引擎剥离** | react loop 兜底保留 | 仅 headless 桥执行；内部 loop 删除 | headless 执行稳定 N 轮（无回退触发） | 定时任务全走 headless | P2 |
| C4 | **pdf-mcp / websearch 退役**（`bin/mcp/`） | builtin 拉起 | 移除（DSH 用**自研 pdf-mcp 直连 :17654** + 自带 websearch） | **自研 pdf-mcp 直连 DSH 实测通过**（2026-08-21 已接入配置，待重启验证）。⚠️ 生态替代实测不合格：`@modelcontextprotocol/server-pdf` 是 viewer 工具集（read_pdf_bytes，非文本提取）；`pdf-mcp-server` 依赖原生 canvas（node-gyp 编译失败） | DSH 独立处理 PDF/搜索 | P2 |
| C5 | **笔记页移除** | `/note` 页面 | 隐藏 → 删除 | 使用率观察期 1~2 月 | 无使用、无死链 | P3 |
| C6 | **文件夹**（仅此一项） | 已无侧边栏入口 | 路由删除（可选） | 观察期后确认无人用 | 无死链 | P3 |
| C7 | **tasks 模块清理** | 已搁置（路由保留） | 代码归档/删除 | 需求确认不再需要 | git 历史可回溯 | P4 |

### 执行节奏

- **第一批（P1）**：C1（officecli 退役）+ C2（chat 收敛）——触发条件核对后开工；
- **第二批（P2）**：C3（automation 剥离）+ C4（pdf/websearch 退役）；
- **第三批（P3）**：C5（笔记）+ C6（文件夹）；
- **归档（P4）**：C7（tasks）。

> ⚠️ **保留项**：**天气、计划为待开发项**（模块已建、功能待开发），**不纳入裁剪**，保留并继续按计划开发。C6 仅指**文件夹**模块。

### 执行规范

- 每批开工前：更新本节"触发条件核对表"（逐条打勾/不满足原因）；
- 每项完成：git commit + 验收清单打勾（对应 §10.5 的"先隐藏后删除"风格）；
- 涉及 MCP 暴露面变化的项（C1/C4）需同步更新：`tools_registration.py`、`bin/mcp/`、能力供给管理页（§10.6 迁入设置页的区块）；

### 触发条件核对表（2026-08-21）

> 核对结论：C1~C7 触发条件**均未全部满足**，维持「规划中、未执行」。仅 C6 的「已无侧边栏入口」一项已满足（入口已删，等待观察期）。

| # | 触发条件 | 核对结果 | 证据 / 说明 |
|---|---|---|---|
| C1 | ①无非 DSH 用户在用 | 🕐 待确认 | 无法从代码确认，需业务侧确认 |
| C1 | ②DSH 侧 OfficeCLI 官方 SKILL/MCP 实测通过 | ❌ 未通过 | 无实测证据 |
| C1 | ③上游二进制先升 v1.0.144 | ❌ 未满足 | 当前 vendored **v1.0.143**（`src/modules/mcp/client_routes.py`、`src/bin/mcp/officecli/service.json`） |
| C2 | §10.7 一键更新/headless 桥稳定运行后 | ❌ 未满足 | §10.7 刚提交（`c46eceb`），尚未观察稳定运行 |
| C3 | headless 执行稳定 N 轮（无回退触发） | ❌ 未满足 | 需运行观察；`automation_runner.py` 仍为 headless 优先 + react loop 回退 |
| C4 | 自研 pdf-mcp 直连 DSH 实测通过（:17654） | 🔶 待重启验证 | 2026-08-21 已接入 DSH 配置（`cordis.patch.yml` mcp-pdf → `http://127.0.0.1:17654/mcp`），dump-config 通过，待重启 DSH 后新会话实测。⚠️ 生态替代不合格：server-pdf 是 viewer（read_pdf_bytes）、pdf-mcp-server 依赖原生 canvas（node-gyp 编译失败） |
| C5 | 使用率观察期 1~2 月 | ❌ 未满足 | 观察期未到；`/note` 仍在侧边栏（`base.html`） |
| C6 | 观察期后确认无人用 | 🕐 部分满足 | 「已无侧边栏入口」✅（`base.html` 无 `/folder`）；「观察期确认无人用」未到 |
| C7 | 需求确认不再需要 | 🕐 待确认 | 需业务确认；`src/modules/tasks/` 仍在（路由保留，侧边栏入口已删） |

**代码现状快照（本次核对）**：

- 侧边栏菜单（`src/templates/base.html`）：工作台 / 对话 / Wiki / 文章 / 图片 / 待办 / 自动化 / 笔记 / 设置——**无 `/folder`、无 `/tasks`、无 `/agent`**；
- OfficeCLI：9 个工具仍在 `tools_registration.py` 注册，`_BUILTIN_GROUPS` 含 `officecli` 分组（`client_routes.py`）；
- `pdf-mcp` / `websearch`：均为 `builtin` + `subprocess`（`src/bin/mcp/*/service.json`），在 `app.py` 内置服务注册，仍被 chat/agent 引用；
- `automation_runner.py`：已 headless 优先 + react loop 回退（C3 剥离的前提代码形态已就位，仅差「稳定 N 轮」观察）。
