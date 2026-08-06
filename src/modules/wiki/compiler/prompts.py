EXTRACT_PROMPT = """你是一个知识提取专家。请从以下内容中提取核心概念。

对于每个概念，返回一个 JSON 数组，每个元素包含：
- "name": 概念名称
- "summary": 一句话概述（50字以内）
- "key_points": 关键要点列表（3-5个）
- "confidence": 置信度 0-1
- "tags": 分类标签列表（2-4个）

请只返回 JSON 数组，不要其他内容。

源文件: {title}

{content}"""

BATCH_EXTRACT_PROMPT = """你是一个知识提取专家。请从以下多篇文章中提取核心概念。

每篇文章用 ====文件名==== 分隔。

对于每个概念，返回一个 JSON 数组，每个元素包含：
- "name": 概念名称
- "summary": 一句话概述（50字以内）
- "key_points": 关键要点列表（3-5个）
- "confidence": 置信度 0-1
- "tags": 分类标签列表（2-4个）
- "_source_title": 来源文章名称

请只返回 JSON 数组，不要其他内容。

{content}"""

GENERATE_PROMPT = """你是一个知识 Wiki 编写专家。请根据以下信息生成一个 Wiki 页面。

概念名称: {concept_name}
已知概念列表: {known_concepts}
相关信息:
{context}

要求:
1. 用 Markdown 格式
2. 使用 [[概念名]] 语法链接到相关概念，只能链接"已知概念列表"中存在的概念名，必须使用列表中的原始名称，不要修改或缩写
3. 内容结构清晰，包含概述、详细说明、相关概念
4. 语言简洁准确
5. 在末尾列出相关概念链接
6. 在段落后使用 ^[来源文件名] 标注来源，如有多来源用 ^[文件a, 文件b]
7. 如果某句话可精确到源文件的行范围，使用 ^[文件名:起始行-结束行] 格式

请直接输出 Markdown 内容，不要包含标题的 # 行。"""

QUERY_SELECT_PROMPT = """你是一个知识库助手。给定以下 Wiki 索引和用户问题，请选择最相关的概念页面。

Wiki 索引:
{index}

问题: {question}

请返回一个 JSON 数组，包含最相关的页面 slug（最多 {limit} 个）和选择理由：
{{"pages": ["slug1", "slug2"], "reasoning": "选择理由"}}

只返回 JSON，不要其他内容。"""

QUERY_ANSWER_PROMPT = """你是一个知识助手。请根据以下 Wiki 内容回答问题。

Wiki 内容:
{context}

问题: {question}

请用中文回答。如果 Wiki 中没有相关信息，请说明。回答时可以引用相关概念。在回答末尾列出引用的概念名称。"""
