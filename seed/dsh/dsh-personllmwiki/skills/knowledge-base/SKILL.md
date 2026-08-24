---
name: personllmwiki-knowledge-base
description: Use when answering questions that may involve the PersonLLMWiki knowledge base. Always search the wiki first via personllmwiki__search_kb before answering.
---

# PersonLLMWiki 知识库检索

## 何时使用

当用户的问题可能涉及公司知识库、物料信息、Wiki 概念、内部文档时，先用本技能检索知识库，再作答。

## 工作流程

1. **先检索**：调用 `personllmwiki__search_kb`，传入用户问题的关键词。
   - 返回 `slug / title / snippet / score / source`。
2. **必要时读全文**：若检索到的 snippet 不足以回答问题，调用 `personllmwiki__read_wiki_page` 读取对应页面全文。
3. **再回答**：基于检索结果回答；若知识库无相关内容，明确告知并正常回答。

## 铁律

- 回答知识库相关问题时，**必须先检索，不要凭空猜测**。
- 只读工具（`search_kb` / `read_wiki_page`）安全；写入 / 审批工具需谨慎。
- `personllmwiki__approve_candidate` 不得被自动批量调用。
- 检索依赖 PersonLLMWiki 进程常驻（`http://127.0.0.1:5000/mcp`），连接失败时向用户说明。
