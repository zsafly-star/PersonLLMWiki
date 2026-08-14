# Bug 修复记录

> 目的：记录所有已修复的 bug，防止同类问题重复出现。
> 最后更新：2026-08-12

---

## 一、根因模式总结

几乎所有前端 bug 都可以归入以下几种根因模式：

| 模式 | 出现次数 | 典型症状 |
|------|---------|---------|
| **SPA 导航下变量/脚本初始化时序** | 10+ | 函数未定义、变量 undefined、事件不生效 |
| **行内 onclick 在 SPA 模式失效** | 4 | 点击无反应、跳过确认弹窗 |
| **行间事件绑定未用 _bindOnce 防重复** | 2 | 重复触发、累计副作用 |
| **客户端/服务端类型不匹配** | 2 | 数据显示错误 |
| **脚本异步加载顺序** | 1 | SPA 导航后功能模块未初始化 |
| **原生 confirm/alert 不可靠** | 1 | 弹窗不出现或被跳过 |
| **API 兼容性缺陷** | 1 | 浏览器 API 权限不足 |
| **UI 状态放置不当** | 1 | 全局状态指示在不相关页面显示 |
| **CSS 继承穿透** | 1 | 全局样式覆盖组件内元素，需 `!important` 锁定 |
| **LLM prompt 过长** | 1 | 大段规则挤占 LLM 对核心指令的注意力 |

---

## 二、已修复 Bug 清单

### #1 MCP 连接数显示 0/3

- **日期**：2026-08-06
- **文件**：`mcp_client.py`、前端 JS
- **根因**：`mcp_client.py` 返回 `connected` 为布尔值，前端按字符串 `'connected'` 匹配
- **修复**：改为直接使用 `s.connected`（布尔判断）
- **模式**：类型不匹配

### #2 Wiki 页面首次点击一直"加载中"

- **日期**：2026-08-06
- **文件**：`base.html`（SPA 导航逻辑）
- **根因**：`body > script` 选择器过严 + `loadingTimer` 逻辑错误 + 缺 HTTP 错误检查
- **修复**：放宽选择器、修复定时器、添加错误检查。改为乐观加载（>300ms 才显示加载态）
- **模式**：SPA 加载逻辑

### #3 Wiki 页面 DOMParser 导致永久加载中

- **日期**：2026-08-06
- **文件**：`base.html`
- **根因**：`DOMParser` 解析完整 HTML 文档行为不稳定
- **修复**：改用真实 DOM 元素（临时 div + innerHTML）解析
- **模式**：SPA 加载逻辑

### #4 Wiki 编译按钮可重复点击

- **日期**：2026-08-06
- **文件**：`wiki.html`
- **根因**：缺少并发保护，快速多次点击触发多次编译
- **修复**：新增 `_compiling` 全局锁，编译完成前阻止新请求
- **模式**：并发控制缺失

### #5 Wiki `_graphState.simulation` 未定义

- **日期**：2026-08-06
- **文件**：`wiki.html`
- **根因**：`_graphState` 定义在 `onPageReady(...)` 调用之后，回调同步执行时变量未声明
- **修复**：将 `_graphState` 定义提前到 `onPageReady` 之前
- **模式**：SPA 导航下变量声明顺序

### #6 设置页头像点击偶发不弹窗

- **日期**：2026-08-06
- **文件**：`settings.html`、`settings.css`
- **根因**：(a) 行内 `onclick` 在 SPA 模式不生效 (b) SVG 元素拦截点击
- **修复**：(a) 改为 `addEventListener` 绑定 (b) `.avatar-preview svg { pointer-events: none }` (c) 加 try/catch
- **模式**：行内 onclick + 事件冒泡

### #7 设置页所有行内事件批量失效风险

- **日期**：2026-08-06
- **文件**：`settings.html`
- **根因**：多个元素使用了行内 `onclick`/`onfocus`/`onchange`，SPA 模式下不可靠
- **修复**：全部改为 `addEventListener`，新增 `_bindOnce` 辅助函数防止重复绑定
- **模式**：行内事件
- **规则**：[project_memory] 设置页所有行内事件需改为 JS 事件绑定

### #8 `TypeError: Cannot set properties of null` + Avatar not ready

- **日期**：2026-08-06
- **文件**：`settings.html`、`home.html`
- **根因**：(a) `loadProfileSettings()` 定义在 `_settingsAvatarSVGs` 之前 (b) `updateTimeAndGreeting` 中 `getElementById` 无 null 检查
- **修复**：(a) 调整函数定义顺序 (b) 所有 `getElementById` 加 null 检查 (c) SPA 切换清理定时器
- **模式**：SPA 导航下变量声明顺序 + null 检查

### #9 头像选择后刷新变回默认值

- **日期**：2026-08-06
- **文件**：`avatar.js`、`settings.html`
- **根因**：`loadAvatar()` 硬编码重置为默认 user SVG，忽略 localStorage
- **修复**：(a) `loadAvatar()` 从 `window.AVATAR_SVGS` 读取 (b) `_normalizeAvatarKey()` 兼容旧格式
- **模式**：硬编码默认值

### #10 基本信息页头像与侧边栏不一致

- **日期**：2026-08-06
- **文件**：`settings.html`
- **根因**：修改头像后侧边栏未同步更新
- **修复**：`loadProfileSettings()` 中主动调用 `updateSidebarAvatar()`
- **模式**：状态同步缺陷

### #11 非对话页面刷新后，历史对话列表为空

- **日期**：2026-08-06
- **文件**：`base.html`
- **根因**：SPA 导航时外部脚本异步加载，内联 `initChat()` 同步执行时函数未定义
- **修复**：修改脚本注入逻辑，`Promise.all` 等待外部脚本加载完成后再执行内联脚本
- **模式**：脚本异步加载顺序
- **规则**：[project_memory] SPA 导航时外部脚本需全部加载完成后再执行内联初始化脚本

### #12 `TypeError: Cannot read properties of undefined (reading 'moon')`

- **日期**：2026-08-06
- **文件**：`settings.html`
- **根因**：`onPageReady(...)` 放在脚本顶部，回调同步执行时 `_settingsAvatarSVGs` 未赋值
- **修复**：将 `onPageReady(...)` 移至文件末尾
- **模式**：SPA 导航下变量声明顺序
- **规则**：[project_memory] 设置页初始化脚本 `onPageReady(...)` 需放在所有函数和变量声明之后

### #13 SSE 流式响应报"网络错误"

- **日期**：2026-08-11
- **文件**：`chat.js`、`routes.py`（chat 模块）
- **根因**：(a) 服务端在 SSE 流中发送了**两个** `done` 事件，客户端在收到第一个 `done` 后停止读取流 (b) 客户端在 `processChunk` 中 `reader.cancel()` 导致浏览器报告连接中断 (c) 客户端将同步函数 `Md.renderSync()` 当成异步调用（`.then()`）
- **修复**：(a) 服务端第二个 `done` 改为 `session_name` 事件 (b) 客户端收到 `done` 后不取消 reader，让流自然结束 (c) `_doneProcessed` 守卫防重复处理 (d) `Md.renderSync(...).then(...)` → 直接赋值
- **模式**：SSE 协议错误 + 异步/同步混淆

### #14 静态文件浏览器缓存导致修改不生效

- **日期**：2026-08-11
- **文件**：`app.py`
- **根因**：Flask 默认对静态文件设置了较长的缓存时间，浏览器不重新请求
- **修复**：`SEND_FILE_MAX_AGE_DEFAULT = 0` + `after_request` 添加 `Cache-Control: no-store`
- **模式**：HTTP 缓存

### #15 设置页"用户内容存储路径"保存失败（PermissionError）

- **日期**：2026-08-11
- **文件**：`.env`、`routes.py`（settings 模块）
- **根因**：(a) TraeCode 沙箱以 `trae-sandbox` 用户运行，无权写入 `C:\Users\zhusa\.personllmwiki\` (b) 首次写 `.env` 时锁文件问题
- **修复**：(a) 改用 `dev.ps1` 在本地终端运行 (b) 保存路径改为临时文件 + `os.replace` 原子替换
- **模式**：权限问题

### #16 fastmcp 版本冲突导致 MCP 服务不可用

- **日期**：2026-08-11
- **文件**：`flask` conda 环境
- **根因**：(a) `fastmcp 2.x` → `3.4.7` 升级导致 `FastMCP` 类被移除，`pdf-mcp`/`websearch` 导入失败 (b) `sap-mcp` 要求 `<3`
- **修复**：`pip install fastmcp==2.14.7` 回退到兼容版本
- **模式**：依赖版本冲突

### #17 文章目录树三点按钮删除不弹确认框

- **日期**：2026-08-11
- **文件**：`article.js`、`article.css`
- **根因**：(a) 删除按钮使用行内 `onclick="deleteDocument(...)"` 在 SPA 模式不可靠 — 点击"删除"时事件冒泡到父级 `<span onclick="toggleTreeItemMenu(this)">`，触发菜单 toggle 干扰了 `confirm()` (b) 原生 `confirm()` 在部分浏览器/SPA 环境中不可靠
- **修复**：(a) 移除所有行内 `onclick`，改为 `data-action` + `#tree-list` 事件委托 (b) 彻底移除原生 `confirm()`，改为自定义模态框（居中弹窗 + "取消"/"确认删除"按钮 + 点击遮罩关闭）
- **模式**：行内 onclick

### #18 save_text_file 写入路径与 write_note 不一致

- **日期**：2026-08-11
- **文件**：`tools_write.py`、`tools_registration.py`、`security.py`
- **根因**：`save_text_file` 锚定 `RESOURCE_BASE_PATH`，`write_note` 锚定 `ARTICLE_PATH`（= `RESOURCE_BASE_PATH/article/`），同一相对路径 `OpenHarmony/xxx.md` 解析到不同物理文件
- **修复**：新增 `root` 参数，默认 `"article"`（与 write_note 同根），可选 `"resource"`
- **模式**：路径根目录不一致

---

## 三、防重复规则（写入 project_memory.md）

以下规则已沉淀到 [project_memory.md](../project_memory.md)，修改相关代码时务必遵守：

1. **CSS 修改**：优先改 `mcp.css`，`automation.css` 只放覆盖
2. **MCP 工具名**：用 snake_case
3. **设置页所有行内事件**（onclick/onfocus/onchange）：改为 `addEventListener` + `_bindOnce`
4. **函数定义顺序**：确保依赖变量已声明
5. **首页 `updateTimeAndGreeting`**：所有 `getElementById` 加 null 检查
6. **SPA 切换**：清理首页定时器
7. **头像加载**：从 `window.AVATAR_SVGS` 读取，兼容旧数据格式
8. **设置页初始化**：`onPageReady(...)` 放脚本最后
9. **SPA 导航脚本加载**：外部脚本全部就绪后再执行内联脚本
10. **删除操作**：使用自定义模态框，不依赖原生 `confirm()`
