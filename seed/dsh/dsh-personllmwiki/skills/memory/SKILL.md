---
name: personllmwiki-memory
description: Use to recall and persist cross-session memories (user preferences / facts / decisions) via PersonLLMWiki memory tools. Recall with personllmwiki__search_memory at conversation start; persist with personllmwiki__remember when a durable preference/fact/decision emerges, and consolidate missed ones at session end.
---

# PersonLLMWiki 记忆（记忆轨）

## 何时使用

- **开场召回**：会话开始，先调 `personllmwiki__search_memory` 召回与当前话题相关的历史偏好/事实/决策。涉及「用户习惯 / 上次怎么定的 / 之前聊过什么」时务必查，不要凭猜。
- **过程中内联记**：用户表达出可跨会话复用的偏好/事实/决策时，当场 `personllmwiki__remember`。
- **收尾复盘**：会话接近结束（用户告别 / 话题收束 / 你判断本会话将结束），回顾本次对话，把遗漏的、成型的偏好/事实/决策逐条补 `personllmwiki__remember`。

## 记忆分类（kind）

| kind | 含义 | 示例 |
|---|---|---|
| `preference` | 用户偏好/习惯/工作方式 | "用户习惯先看 TODO 再写代码" |
| `fact` | 客观事实 | "物料 10041601 已停产" |
| `decision` | 拍板/决策 | "文档库收敛为 4 目录 10 篇 + 数字前缀" |
| `other` | 其他备注 | 临时但值得留的 |

## 何时记（正例）

- 用户明说"我习惯… / 我喜欢… / 以后… / 记住这个 / 下次也这样"
- 明确拍板："就用 X / 决定 Y / 定了 Z / 从今往后…"
- 跨会话有用的客观事实（不是一次性问答）

## 何时不记（反例）

- 一次性问答、闲聊、临时情绪、用户随口一提但未确认的
- 与已有记忆重复（先 `search_memory` 查重）

## 铁律

- **一条只记一个点**，正文一句话说清；不要把整段对话粘进去。
- **记之前先查重**：`search_memory` 确认没有近似条目再 `remember`。
- `decision` 尽量带决策依据（basis）和来源。
- `forget_memory` **不得**自动调用（撤回是用户的权力）。
- `search_memory` 只读，安全；`remember` 是写入，**宁缺毋滥**，不确定就不记。
