"""Agent 循环公共核心。

统一 react loop（chat / automation / tasks 三处共用），消除历史重复代码：
- chat 对话页（common/agent.py）
- 自动化定时任务（common/automation_runner.py）
- 任务流水线编排（modules/tasks/orchestrator.py）

核心函数 run_agent_loop 只负责"思考 → 调工具 → 产出"的循环，
system prompt 与工具范围由调用方传入。
"""

import json

from common.llm_config import LLMConfigService
from common.mcp_client import get_bus


def get_active_llm():
    """获取活跃 LLM 配置，返回 (provider, model, kwargs)。"""
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


def extract_tool_result_text(result):
    """从工具返回的 MCP content 格式中提取纯文本。"""
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


def message_to_dict(message):
    """把 OpenAI message 对象转为可序列化 dict。"""
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


def filter_tools_by_scope(allowed_tools):
    """按工具名白名单过滤工具列表。

    Args:
        allowed_tools: 工具名列表。
            - None：不过滤（返回全部）
            - 含 '*'：不过滤（返回全部）
            - []：禁止调用任何工具（返回空列表）
            - ['search_kb', ...]：只允许白名单内工具

    Returns:
        LLM function-calling 格式的工具列表
    """
    bus = get_bus()
    all_tools = bus.get_tools_for_llm()

    if allowed_tools is None or '*' in allowed_tools:
        return all_tools

    allowed = set(allowed_tools)
    return [t for t in all_tools if t['function']['name'] in allowed]


def run_agent_loop(messages, *, system_prompt=None, tools=None, max_rounds=30,
                   progress_callback=None):
    """统一的 react loop。

    Args:
        messages: 对话历史 [{role, content}]
        system_prompt: 可选，插入到 messages 最前（作为 system 消息）
        tools: 可选，已过滤的工具列表（None 表示不启用工具）
        max_rounds: 最大工具调用轮次
        progress_callback: 可选回调 fn(event_type, data)

    Returns:
        {'response': str, 'tool_calls': list, 'rounds': int}
    """
    provider, model, kwargs = get_active_llm()
    if not provider:
        return {'response': '未配置 LLM', 'tool_calls': [], 'rounds': 0}

    from common.llm import LLMService
    adapter = LLMService.get_adapter(provider, **kwargs)

    full_messages = list(messages)
    if system_prompt:
        # 确保 system prompt 在最前面
        if full_messages and full_messages[0].get('role') == 'system':
            full_messages[0] = {'role': 'system', 'content': system_prompt}
        else:
            full_messages.insert(0, {'role': 'system', 'content': system_prompt})

    tool_call_log = []
    current_round = 0

    while current_round < max_rounds:
        current_round += 1

        adapter_instance = adapter(**kwargs) if isinstance(adapter, type) else adapter
        message = adapter_instance.chat(full_messages, model=model, tools=tools)

        # 返回字符串（错误）时直接返回
        if isinstance(message, str):
            return {'response': message, 'tool_calls': tool_call_log, 'rounds': current_round - 1}

        has_tool_calls = hasattr(message, 'tool_calls') and message.tool_calls

        # 调工具前的口语化思考文字 → 通知回调
        thinking_text = (message.content or '').strip() if hasattr(message, 'content') else ''
        if thinking_text and has_tool_calls and progress_callback:
            try:
                progress_callback('thinking_text', {'text': thinking_text})
            except Exception:
                pass

        if not has_tool_calls:
            return {
                'response': message.content or '',
                'tool_calls': tool_call_log,
                'rounds': current_round - 1,
            }

        # 把 assistant 消息加入历史
        full_messages.append(message_to_dict(message))

        bus = get_bus()
        for tc in message.tool_calls:
            tool_name = tc.function.name
            try:
                tool_args = json.loads(tc.function.arguments) if tc.function.arguments else {}
            except json.JSONDecodeError:
                tool_args = {}

            if progress_callback:
                try:
                    progress_callback('tool_start', {
                        'name': tool_name,
                        'arguments': tool_args,
                        'round': current_round,
                    })
                except Exception:
                    pass

            result = None
            result_text = ''
            try:
                result = bus.call_tool(tool_name, tool_args)
                result_text = extract_tool_result_text(result)
            except Exception as e:
                result_text = f'工具调用失败: {str(e)}'

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

            full_messages.append({
                'role': 'tool',
                'tool_call_id': tc.id,
                'content': result_text,
            })

    return {
        'response': '已达到最大工具调用次数限制，以下是最后一次工具调用的结果。请尝试简化您的请求。',
        'tool_calls': tool_call_log,
        'rounds': current_round,
    }
