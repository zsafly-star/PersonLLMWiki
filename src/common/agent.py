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

AGENT_SYSTEM_PROMPT = """你是一个智能知识助手。你可以通过调用工具来帮助用户：

## 思考展示规则（重要）
在每次调用工具之前，先用一句简短的口语化中文说明你在做什么、为什么这么做。像自言自语一样自然。不要用列表、不要用 markdown 格式，就是一句自然的句子。将这句思考文字作为普通文本输出，然后再调用工具。

示例：
- "我先搜一下知识库，看有没有记录过相关经验的"
- "知识库里的信息有点旧了，联网查查最新的资料"

你可以通过调用工具来帮助用户：
- 搜索知识库（search_kb）
- 读取笔记和 Wiki 页面
- 查询 SAP 物料信息（如果已连接 SAP MCP 服务器）
- 创建和编辑 Office 文档（Word/Excel/PPT）
- 以及其他可用工具

请根据用户需求智能选择工具。如果不需要工具，直接回答。
工具调用结果中的 isError=true 表示工具执行出错，请告知用户并尝试其他方法。

## 文件路径规则
- 用户上传的文件在 `{upload_dir}` 目录下
- 需读取用户上传的文件时，使用完整路径 `{upload_dir}/文件名`
- 导出/创建的文档保存到 `{export_dir}` 目录下

## 核心规则：文档创建
- **严禁主动创建文档**。除非用户明确要求"保存为文档"、"导出为 Word"、"生成文档"、"创建 docx"等，否则所有内容应直接在对话中展示，不要调用 create_document / add_element 等文档工具。
- 即使用户说"写一篇报告"、"整理一份文档"等，也应在对话中直接输出内容，不要创建文件。

## 文档导出规则（仅当用户明确要求导出/保存为文档时适用）
当用户明确说"保存为文档"、"导出为 Word/Word版/docx"、"生成文档"等：
1. 导出目录 `{export_dir}` 已自动创建，无需调用 create_folder
2. create_document 会自动覆盖同名文件，无需手动删除
3. 使用 create_document 创建 .docx 文件，路径为 `{export_dir}/文档标题.docx`
4. 使用 add_element 写入内容，优先用 type="paragraph" 分段写入，每个段落尽可能包含更多内容以减少调用次数
5. 导出完成后告知用户文件路径和下载方式"""

EXPERT_SYSTEM_PROMPT = """你是一个资深的领域专家顾问。你需要提供深入、专业、全面的分析。

## 思考展示规则（重要）
在每次调用工具之前，先用一句简短的口语化中文说明你在做什么、为什么这么做。像自言自语一样自然。不要用列表、不要用 markdown 格式，就是一句自然的句子。将这句思考文字作为普通文本输出，然后再调用工具。

示例：
- "我先搜一下知识库，看有没有记录过类似的分析经验"
- "知识库里的信息比较久远了，联网搜索一下最新的研究进展"

回答要求：
- 展示你的完整推理过程（thinking），让用户理解你的分析思路
- 从多个角度分析问题，列出优缺点、风险和机会
- 引用相关知识库内容或数据支撑你的论点
- 如果信息不足，明确指出需要补充什么信息
- 给出结构化的结论和可操作的建议

## 文件路径规则
- 用户上传的文件在 `{upload_dir}` 目录下
- 需读取用户上传的文件时，使用完整路径 `{upload_dir}/文件名`
- 导出/创建的文档保存到 `{export_dir}` 目录下

## 核心规则：文档创建
- **严禁主动创建文档**。除非用户明确要求"保存为文档"、"导出为 Word"、"生成文档"、"创建 docx"等，否则所有分析内容直接在对话中展示，不要调用 create_document / add_element 等文档工具。
- 即使用户说"写一份报告"、"整理一份文档"等，也应在对话中直接输出内容，不要创建文件。

## 预搜索上下文
系统已自动为你搜索了知识库和互联网，结果已在上下文中提供。请优先参考这些信息进行回答。
如需更深入的信息，你可以自行调用 search_kb 或 websearch__web_search 进行补充搜索。

## 可用工具
- 搜索知识库（search_kb）
- 联网搜索最新资料（websearch__web_search）
- 读取笔记和 Wiki 页面
- 查询 SAP 物料信息（如果已连接 SAP MCP 服务器）
- 创建和编辑 Office 文档（Word/Excel/PPT）
- 以及其他可用工具

工具调用结果中的 isError=true 表示工具执行出错，请告知用户并尝试其他方法。

## 文档导出规则（仅当用户明确要求导出/保存为文档时适用）
当用户明确说"保存为文档"、"导出为 Word/Word版/docx"、"生成文档"等：
1. 导出目录 `{export_dir}` 已自动创建，无需调用 create_folder
2. create_document 会自动覆盖同名文件，无需手动删除
3. 使用 create_document 创建 .docx 文件，路径为 `{export_dir}/文档标题.docx`
4. 使用 add_element 写入内容，优先用 type="paragraph" 分段写入，每个段落尽可能包含更多内容以减少调用次数
5. 导出完成后告知用户文件路径和下载方式"""


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
    # 获取工具列表
    tools = None
    if use_tools:
        bus = get_bus()
        tools = bus.get_tools_for_llm()

    # 构建 system prompt（注入 Skills 列表 + 导出路径）
    full_messages = list(messages)
    has_system = any(m.get('role') == 'system' for m in full_messages)
    system_prompt = None
    if not has_system:
        system_prompt = EXPERT_SYSTEM_PROMPT if mode == 'expert' else AGENT_SYSTEM_PROMPT
        # 注入导出目录路径和上传目录路径（基于配置的附件路径）
        from config import Config
        export_dir = os.path.join(Config.ATTACHMENT_PATH, 'file_exports')
        upload_dir = os.path.join(Config.ATTACHMENT_PATH, 'chat_uploads')
        system_prompt = system_prompt.replace('{export_dir}', export_dir)
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

    # ── 专家模式强制流程：先查知识库 → 再联网搜 → 注入上下文 ──
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
                'arguments': {'keyword': user_query[:200]},
                'round': 0,
            })
            kb_text = ''
            try:
                kb_result = bus.call_tool('search_kb', {'keyword': user_query[:200]})
                kb_text = extract_tool_result_text(kb_result)
            except Exception as e:
                kb_text = f'知识库搜索失败: {e}'
            progress_callback('tool_result', {
                'name': 'search_kb', 'result': kb_text[:300],
                'success': True, 'round': 0,
            })
            context_parts.append('【知识库搜索结果】\n' + kb_text)

            # 第2步：自动联网搜索
            progress_callback('tool_start', {
                'name': 'websearch__web_search',
                'arguments': {'query': user_query[:200]},
                'round': 1,
            })
            web_text = ''
            try:
                web_result = bus.call_tool('websearch__web_search', {'query': user_query[:200]})
                web_text = extract_tool_result_text(web_result)
            except Exception as e:
                web_text = f'联网搜索失败: {e}'
            progress_callback('tool_result', {
                'name': 'websearch__web_search', 'result': web_text[:300],
                'success': True, 'round': 1,
            })
            context_parts.append('【联网搜索结果】\n' + web_text)

            # 第3步：整理思路（展示性阶段）
            progress_callback('custom_stage_start', {'stage_name': '整理思路'})
            time.sleep(0.3)
            progress_callback('custom_stage_end', {'stage_name': '整理思路'})

            # 注入预搜索结果到上下文
            full_messages.append({
                'role': 'system',
                'content': '以下是针对用户问题的自动搜索结果，请综合这些信息来回答：\n\n'
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
