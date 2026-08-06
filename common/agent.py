"""AI Agent 对话中枢（Phase 5）。

Tool-calling agent loop：
1. LLM 收到用户消息 + 工具列表
2. LLM 决定是否调用工具
3. 如果调用工具：执行工具 → 把结果喂回 LLM → 回到第 2 步
4. 如果不调用工具：返回最终回复

最大循环次数限制：30（防止无限循环）
"""

import json
import os
import time

from common.llm_config import LLMConfigService
from common.mcp_client import get_bus


MAX_TOOL_ROUNDS = 30

AGENT_SYSTEM_PROMPT = """你是一个智能知识助手。你可以通过调用工具来帮助用户：
- 搜索知识库（search_kb）
- 读取笔记和 Wiki 页面
- 查询 SAP 物料信息（如果已连接 SAP MCP 服务器）
- 创建和编辑 Office 文档（Word/Excel/PPT）
- 以及其他可用工具

请根据用户需求智能选择工具。如果不需要工具，直接回答。
工具调用结果中的 isError=true 表示工具执行出错，请告知用户并尝试其他方法。

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

回答要求：
- 展示你的完整推理过程（thinking），让用户理解你的分析思路
- 从多个角度分析问题，列出优缺点、风险和机会
- 引用相关知识库内容或数据支撑你的论点
- 如果信息不足，明确指出需要补充什么信息
- 给出结构化的结论和可操作的建议

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


def _get_active_llm():
    """获取活跃 LLM 配置"""
    config = LLMConfigService.get_active()
    if config:
        provider = config.provider
        model = config.model or ''
        kwargs = {}
        if config.api_key:
            kwargs['api_key'] = config.api_key
        if config.base_url:
            kwargs['base_url'] = config.base_url
        return provider, model, kwargs
    return None, None, {}


def _extract_tool_result_text(result):
    """从工具返回的 MCP content 格式中提取纯文本"""
    if isinstance(result, str):
        return result

    if isinstance(result, dict):
        if result.get('isError'):
            texts = []
            for c in result.get('content', []):
                if isinstance(c, dict) and c.get('type') == 'text':
                    texts.append(c['text'])
            return '工具执行出错: ' + '\n'.join(texts)

        contents = result.get('content', [])
        texts = []
        for c in contents:
            if isinstance(c, dict) and c.get('type') == 'text':
                texts.append(c['text'])
        return '\n'.join(texts) if texts else json.dumps(result, ensure_ascii=False)

    return str(result)


def _message_to_dict(message):
    """把 OpenAI message 对象转为 dict（可序列化）"""
    if isinstance(message, str):
        return {'role': 'assistant', 'content': message}

    d = {'role': message.role}
    if message.content:
        d['content'] = message.content
    if hasattr(message, 'tool_calls') and message.tool_calls:
        d['tool_calls'] = []
        for tc in message.tool_calls:
            d['tool_calls'].append({
                'id': tc.id,
                'type': 'function',
                'function': {
                    'name': tc.function.name,
                    'arguments': tc.function.arguments,
                },
            })
    return d


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
    provider, model, kwargs = _get_active_llm()
    if not provider:
        return {'response': '未配置 LLM', 'tool_calls': [], 'rounds': 0}

    from common.llm import LLMService
    adapter = LLMService.get_adapter(provider, **kwargs)

    # 获取工具列表
    tools = None
    if use_tools:
        bus = get_bus()
        tools = bus.get_tools_for_llm()

    # 确保 system prompt 在最前面（注入 Skills 列表 + 导出路径）
    full_messages = list(messages)
    has_system = any(m.get('role') == 'system' for m in full_messages)
    if not has_system:
        system_prompt = EXPERT_SYSTEM_PROMPT if mode == 'expert' else AGENT_SYSTEM_PROMPT
        # 注入导出目录路径（基于配置的附件路径）
        from config import Config
        export_dir = os.path.join(Config.ATTACHMENT_PATH, 'file_exports')
        system_prompt = system_prompt.replace('{export_dir}', export_dir)
        # 注入可用技能列表
        try:
            from common.skill_loader import get_skills_prompt, match_skill
            skills_prompt = get_skills_prompt()
            if skills_prompt:
                system_prompt += skills_prompt
        except Exception:
            pass
        full_messages.insert(0, {'role': 'system', 'content': system_prompt})

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
                kb_text = _extract_tool_result_text(kb_result)
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
                web_text = _extract_tool_result_text(web_result)
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

    tool_call_log = []
    current_round = 0

    while current_round < MAX_TOOL_ROUNDS:
        current_round += 1

        # 调用 LLM
        if isinstance(adapter, type) :
            adapter_instance = adapter(**kwargs) if isinstance(adapter, type) else adapter
        else:
            adapter_instance = adapter

        message = adapter_instance.chat(full_messages, model=model, tools=tools)

        # 如果返回的是字符串（错误），直接返回
        if isinstance(message, str):
            return {'response': message, 'tool_calls': tool_call_log, 'rounds': current_round - 1}

        # 检查是否有 tool_calls
        has_tool_calls = hasattr(message, 'tool_calls') and message.tool_calls

        if not has_tool_calls:
            # LLM 没有调用工具，返回最终回复
            return {
                'response': message.content or '',
                'tool_calls': tool_call_log,
                'rounds': current_round - 1,
            }

        # 有 tool_calls：把 assistant 消息加入历史
        msg_dict = _message_to_dict(message)
        full_messages.append(msg_dict)

        # 执行每个工具调用
        bus = get_bus()
        for tc in message.tool_calls:
            tool_name = tc.function.name
            try:
                tool_args = json.loads(tc.function.arguments) if tc.function.arguments else {}
            except json.JSONDecodeError:
                tool_args = {}

            # 通知前端正在调用工具
            if progress_callback:
                try:
                    progress_callback('tool_start', {
                        'name': tool_name,
                        'arguments': tool_args,
                        'round': current_round,
                    })
                except Exception:
                    pass

            # 调用工具（异常保护：确保 tool_result 回调始终触发）
            result = None
            result_text = ''
            try:
                result = bus.call_tool(tool_name, tool_args)
                result_text = _extract_tool_result_text(result)
            except Exception as e:
                result_text = f'工具调用失败: {str(e)}'

            # 通知前端工具调用完成
            if progress_callback:
                try:
                    progress_callback('tool_result', {
                        'name': tool_name,
                        'result': result_text[:300],
                        'success': result is not None,
                        'error': result_text if result is None else None,
                        'round': current_round,
                    })
                except Exception:
                    pass

            tool_call_log.append({
                'round': current_round,
                'name': tool_name,
                'arguments': tool_args,
                'result': result_text[:500],
            })

            # 把工具结果加入消息历史
            full_messages.append({
                'role': 'tool',
                'tool_call_id': tc.id,
                'content': result_text,
            })

    # 超过最大轮次
    return {
        'response': '已达到最大工具调用次数限制，以下是最后一次工具调用的结果。请尝试简化您的请求。',
        'tool_calls': tool_call_log,
        'rounds': current_round,
    }
