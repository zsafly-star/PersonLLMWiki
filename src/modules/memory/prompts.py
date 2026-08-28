"""记忆提取 prompt 定义。"""

MEMORY_EXTRACT_PROMPT = """你是个人知识库的「记忆提取器」。输入是某次对话的原始 trace（用户消息 + 工具调用名/结果）：

{trace_text}

请从中提取用户【明确表述】的偏好、事实与决策。

输出要求：
- 只输出一个 JSON 数组，不要任何额外文字、解释或代码块标记。
- 每个元素形如：
{{"kind": "preference|fact|decision|other", "slug": "简短中文slug", "content": "正文", "summary": "一句话摘要"}}
- kind=decision 的元素额外带：
  {{"kind": "decision", "slug": "...", "content": "...", "summary": "...", "basis": "决策依据", "source_refs": ["来源列表"], "related_entities": ["关联实体列表"]}}

严格规则：
1. 只提取用户【明确表述】的偏好/事实/决策，禁止臆测、推断、编造。
2. 没有可提取内容时输出 []。
3. 输出必须是合法 JSON 数组。
"""
