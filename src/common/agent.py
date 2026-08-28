"""AI Agent 对话中枢（Phase 5）。

Tool-calling agent loop：
1. LLM 收到用户消息 + 工具列表
2. LLM 决定是否调用工具
3. 如果调用工具：执行工具 → 把结果喂回 LLM → 回到第 2 步
4. 如果不调用工具：返回最终回复

最大循环次数限制：30（防止无限循环）
"""

import os
import time

from common.mcp_client import get_bus
from common.agent_core import run_agent_loop, extract_tool_result_text


MAX_TOOL_ROUNDS = 30

AGENT_SYSTEM_PROMPT = """你是一个智能知识助手，专注于知识问答与检索。你可以通过调用工具来帮助用户：

## 思考展示规则（重要）
在每次调用工具之前，先用一句简短的口语化中文说明你在做什么、为什么这么做。像自言自语一样自然。不要用列表、不要用 markdown 格式，就是一句自然的句子。将这句思考文字作为普通文本输出，然后再调用工具。

示例：
- "我先搜一下知识库，看有没有记录过相关经验的"
- "知识库里的信息有点旧了，我再读一下相关笔记补充细节"

你可以通过调用工具来帮助用户：
- 搜索知识库（search_kb）
- 读取笔记和 Wiki 页面
- 以及其他知识问答类工具

请根据用户需求智能选择工具。如果不需要工具，直接回答。
工具调用结果中的 isError=true 表示工具执行出错，请告知用户并尝试其他方法。

## 定位与边界（重要）
你专注于知识问答、检索与信息整理。当用户的需求属于复杂的多步自动化编排、Office 文档（Word/Excel/PPT）生成或编辑、或需要调用大量专业工具完成的工作流时，请礼貌地建议用户切换到「智能体（DSH）」模式来处理。

## 文件路径规则
- 用户上传的文件在 `{upload_dir}` 目录下
- 需读取用户上传的文件时，使用完整路径 `{upload_dir}/文件名`"""

EXPERT_SYSTEM_PROMPT = """你是一个资深的领域专家顾问。你需要提供深入、专业、全面的分析。

## 思考展示规则（重要）
在每次调用工具之前，先用一句简短的口语化中文说明你在做什么、为什么这么做。像自言自语一样自然。不要用列表、不要用 markdown 格式，就是一句自然的句子。将这句思考文字作为普通文本输出，然后再调用工具。

示例：
- "我先搜一下知识库，看有没有记录过类似的分析经验"
- "知识库里的信息比较久远了，我再读一下相关笔记补充更多细节"

回答要求：
- 展示你的完整推理过程（thinking），让用户理解你的分析思路
- 从多个角度分析问题，列出优缺点、风险和机会
- 引用相关知识库内容或数据支撑你的论点
- 如果信息不足，明确指出需要补充什么信息
- 给出结构化的结论和可操作的建议

## 文件路径规则
- 用户上传的文件在 `{upload_dir}` 目录下
- 需读取用户上传的文件时，使用完整路径 `{upload_dir}/文件名`

## 定位与边界（重要）
你专注于知识问答、检索与深度分析。当用户的需求属于复杂的多步自动化编排、Office 文档（Word/Excel/PPT）生成或编辑、或需要调用大量专业工具完成的工作流时，请礼貌地建议用户切换到「智能体（DSH）」模式来处理。

## 预搜索上下文
系统已自动为你搜索了知识库，结果已在上下文中提供。请优先参考这些信息进行回答。
如需更深入的信息，你可以自行调用 search_kb 进行补充搜索。

## 可用工具
- 搜索知识库（search_kb）
- 读取笔记和 Wiki 页面
- 以及其他知识问答类工具

工具调用结果中的 isError=true 表示工具执行出错，请告知用户并尝试其他方法。"""


def _get_mermaid_prompt():
    """注入精简版 Mermaid 图表规范（详细规则见 seed/skills/mermaid/SKILL.md）。"""
    return """

## Mermaid 图表规范（仅在需要绘制图表时遵守）

1. 所有含特殊字符(空格/()/&/引号/中文括号/+)的标签文本必须用双引号包裹，节点ID用简单英文
2. 箭头标签必须用 `|"标签"|` 语法，严禁 `-- "标签" -->` 或 `-. "标签" .->`
3. **跨 subgraph 连线必须全部放在所有 `end` 之后，subgraph 内部只能有本组成员连线**
4. 禁止 `&` 多源合并（S1 & S2 --> M），拆成独立边
5. 生成后逐条自检：标签引号？|xxx|语法？跨组连线位置？&合并？发现任一问题自动修正后重新输出

"""


def _get_local_tools_for_llm():
    """构建仅本地工具的 LLM function-calling 格式列表。

    仅暴露 PersonLLMWiki 自身注册的本地 MCP 工具，不再合并远程/外部 MCP 工具
    （外部 MCP 能力统一由 DSH 承接）。
    """
    from modules.mcp.registry import list_tools
    tools = []
    for tool in list_tools():
        tools.append({
            'type': 'function',
            'function': {
                'name': tool.name,
                'description': tool.description,
                'parameters': tool.input_schema or {'type': 'object', 'properties': {}},
            },
        })
    return tools


def agent_chat(messages, use_tools=True, mode='quick', progress_callback=None):
    """Agent 模式对话（非流式）。

    Args:
        messages: 对话历史 [{role, content}]
        use_tools: 是否启用工具
        mode: 'quick'（快速模式，简洁直接）或 'expert'（专家模式，深入分析）
        progress_callback: 可选，工具调用进度回调 fn(event_type, data)

    Returns:
        {
            'response': str,        # 最终回复文本
            'tool_calls': list,     # 工具调用记录 [{name, arguments, result, round}]
            'rounds': int,          # 总共几轮工具调用
        }
    """
    # 获取工具列表（仅本地工具，外部 MCP 能力统一由 DSH 承接）
    tools = None
    if use_tools:
        tools = _get_local_tools_for_llm()

    # 构建 system prompt（注入 Skills 列表 + 上传路径）
    full_messages = list(messages)
    has_system = any(m.get('role') == 'system' for m in full_messages)
    system_prompt = None
    if not has_system:
        system_prompt = EXPERT_SYSTEM_PROMPT if mode == 'expert' else AGENT_SYSTEM_PROMPT
        # 注入上传目录路径（基于配置的附件路径）
        from config import Config
        upload_dir = os.path.join(Config.ATTACHMENT_PATH, 'chat_uploads')
        system_prompt = system_prompt.replace('{upload_dir}', upload_dir)
        # 注入可用技能列表
        try:
            from common.skill_loader import get_skills_prompt, match_skill
            skills_prompt = get_skills_prompt()
            if skills_prompt:
                system_prompt += skills_prompt
        except Exception:
            pass
        # 注入 Mermaid 图表规范（从 skill 文件加载，始终生效）
        system_prompt += _get_mermaid_prompt()

    # ── 记忆召回：对话开场自动注入（快速/专家模式都注入，记忆块在 Wiki 块之前）──
    if use_tools:
        user_query = ''
        for m in reversed(messages):
            if m.get('role') == 'user':
                user_query = m.get('content', '')
                break
        if user_query:
            try:
                from modules.memory.injector import inject_memory_context
                mem_text = inject_memory_context(user_query, top_k=3)
                if mem_text:
                    full_messages.append({'role': 'system', 'content': mem_text})
            except Exception:
                pass

    # ── 专家模式强制流程：先查知识库 → 注入上下文 ──
    if mode == 'expert' and use_tools and progress_callback:
        # 提取用户最新问题
        user_query = ''
        for m in reversed(messages):
            if m.get('role') == 'user':
                user_query = m.get('content', '')
                break
        if user_query:
            bus = get_bus()
            context_parts = []

            # 第1步：自动搜索知识库
            progress_callback('tool_start', {
                'name': 'search_kb',
                'arguments': {'keyword': user_query[:200],
                              'delivery': 'layered', 'budget_tokens': 1500},
                'round': 0,
            })
            kb_text = ''
            try:
                kb_result = bus.call_tool('search_kb', {'keyword': user_query[:200],
                                                        'delivery': 'layered', 'budget_tokens': 1500})
                kb_text = extract_tool_result_text(kb_result)
            except Exception as e:
                kb_text = f'知识库搜索失败: {e}'
            progress_callback('tool_result', {
                'name': 'search_kb', 'result': kb_text[:300],
                'success': True, 'round': 0,
            })
            context_parts.append('【知识库搜索结果】\n' + kb_text)

            # 第2步：整理思路（展示性阶段）
            progress_callback('custom_stage_start', {'stage_name': '整理思路'})
            time.sleep(0.3)
            progress_callback('custom_stage_end', {'stage_name': '整理思路'})

            # 注入预搜索结果到上下文
            full_messages.append({
                'role': 'system',
                'content': '以下是针对用户问题的知识库搜索结果，请综合这些信息来回答：\n\n'
                           + '\n\n'.join(context_parts),
            })

    # ── 复用公共 react loop ──
    return run_agent_loop(
        full_messages,
        system_prompt=system_prompt,
        tools=tools,
        max_rounds=MAX_TOOL_ROUNDS,
        progress_callback=progress_callback,
    )
