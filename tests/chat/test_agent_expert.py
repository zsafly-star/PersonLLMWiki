"""Agent 专家模式强制流程测试。

覆盖场景：
1. 专家模式自动调用 search_kb + websearch__web_search
2. 预搜索结果注入 full_messages
3. progress_callback 事件顺序正确
4. 快速模式不走强制流程
5. 工具调用失败不中断流程
"""
import json
from unittest.mock import patch, MagicMock

import pytest


# ── Mock 对象 ──────────────────────────────────────────────

class FakeFunction:
    def __init__(self, name, arguments='{}'):
        self.name = name
        self.arguments = arguments


class FakeToolCall:
    def __init__(self, name, arguments='{}', tc_id='tc_1'):
        self.id = tc_id
        self.type = 'function'
        self.function = FakeFunction(name, arguments)


class FakeMessage:
    """模拟 OpenAI message 返回。"""
    def __init__(self, content=None, tool_calls=None):
        self.role = 'assistant'
        self.content = content
        self.tool_calls = tool_calls


class FakeAdapter:
    """模拟 LLM adapter，按预设队列返回响应。自动捕获传入的 messages。"""
    def __init__(self, responses):
        self.responses = list(responses)
        self.idx = 0
        self.captured_messages = []

    def chat(self, messages, model=None, tools=None):
        self.captured_messages.extend(messages)
        if self.idx >= len(self.responses):
            return FakeMessage(content='（无更多响应）')
        resp = self.responses[self.idx]
        self.idx += 1
        return resp

    def __call__(self, **kwargs):
        """LLMService.get_adapter 返回的 adapter 可能是类或实例，
        如果是类则会被实例化，所以支持 __call__ 不需要。"""
        return self


class FakeBus:
    """模拟 MCP client bus。"""
    def __init__(self, tool_results=None):
        self.tool_results = tool_results or {}
        self.call_log = []

    def call_tool(self, name, args):
        self.call_log.append((name, args))
        result = self.tool_results.get(name)
        if result is None:
            return {'content': [{'type': 'text', 'text': '无结果'}]}
        return result

    def get_tools_for_llm(self):
        return []


@pytest.fixture
def mock_llm_env(app):
    """统一的 mock 环境：fake LLM adapter + fake MCP bus。

    用法：
        def test_something(mock_llm_env):
            bus = mock_llm_env['bus']
            adapter = mock_llm_env['adapter']
            adapter.responses = [FakeMessage(content='回答')]
            with mock_llm_env['patches']:
                from common.agent import agent_chat
                result = agent_chat(...)
    """
    bus = FakeBus(tool_results={
        'search_kb': {'content': [{'type': 'text', 'text': '知识库结果'}]},
        'websearch__web_search': {'content': [{'type': 'text', 'text': '联网结果'}]},
    })
    adapter = FakeAdapter([FakeMessage(content='回答')])

    mock_llm = MagicMock()
    mock_llm.get_adapter.return_value = adapter

    patches = [
        patch('common.agent._get_active_llm', return_value=('fake', 'fake-model', {})),
        patch('common.llm.LLMService', mock_llm),
        patch('common.agent.get_bus', return_value=bus),
        patch('common.skill_loader.get_skills_prompt', return_value=''),
    ]
    for p in patches:
        p.start()

    yield {'bus': bus, 'adapter': adapter, 'mock_llm': mock_llm}

    for p in patches:
        p.stop()


# ── 测试用例 ───────────────────────────────────────────────

class TestExpertForcedFlow:
    """专家模式强制流程：search_kb → websearch__web_search → 注入上下文。"""

    def test_expert_calls_search_kb_and_web_search(self, mock_llm_env):
        """专家模式自动调用 search_kb 和 websearch__web_search。"""
        from common.agent import agent_chat
        agent_chat(
            [{'role': 'user', 'content': '什么是RESTful API'}],
            use_tools=True, mode='expert',
            progress_callback=lambda evt, data: None,
        )

        bus = mock_llm_env['bus']
        tool_names = [name for name, _ in bus.call_log]
        assert 'search_kb' in tool_names, "专家模式应自动调用 search_kb"
        assert 'websearch__web_search' in tool_names, "专家模式应自动调用 websearch__web_search"

    def test_expert_injects_context_into_messages(self, mock_llm_env):
        """预搜索结果注入 full_messages 作为 system 消息。"""
        from common.agent import agent_chat
        agent_chat(
            [{'role': 'user', 'content': '测试问题'}],
            use_tools=True, mode='expert',
            progress_callback=lambda evt, data: None,
        )

        adapter = mock_llm_env['adapter']
        injected = [m for m in adapter.captured_messages
                    if m.get('role') == 'system' and '知识库结果' in m.get('content', '')]
        assert len(injected) >= 1, "应注入包含知识库结果的 system 消息"
        assert '联网结果' in injected[-1]['content'], "注入消息应包含联网搜索结果"

    def test_expert_progress_callback_events(self, mock_llm_env):
        """专家模式回调事件顺序正确。"""
        events = []
        from common.agent import agent_chat
        agent_chat(
            [{'role': 'user', 'content': '测试'}],
            use_tools=True, mode='expert',
            progress_callback=lambda evt, data: events.append((evt, data.get('name', data.get('stage_name', '')))),
        )

        event_types = [e[0] for e in events]
        assert 'tool_start' in event_types
        assert 'tool_result' in event_types
        assert 'custom_stage_start' in event_types
        assert 'custom_stage_end' in event_types

        tool_starts = [(e[0], e[1]) for e in events if e[0] == 'tool_start']
        assert len(tool_starts) >= 2
        assert tool_starts[0][1] == 'search_kb'
        assert tool_starts[1][1] == 'websearch__web_search'

    def test_expert_search_failure_does_not_break_flow(self, mock_llm_env):
        """知识库或联网搜索失败时，流程不中断。"""
        bus = mock_llm_env['bus']
        def failing_call_tool(name, args):
            raise Exception('连接失败')
        bus.call_tool = failing_call_tool

        from common.agent import agent_chat
        result = agent_chat(
            [{'role': 'user', 'content': '测试'}],
            use_tools=True, mode='expert',
        )

        assert 'response' in result
        assert isinstance(result['response'], str)


class TestQuickModeNoForcedSearch:
    """快速模式不走强制流程。"""

    def test_quick_mode_no_auto_search(self, mock_llm_env):
        """快速模式不自动调用 search_kb 或 websearch__web_search。"""
        from common.agent import agent_chat
        agent_chat(
            [{'role': 'user', 'content': '你好'}],
            use_tools=True, mode='quick',
        )

        bus = mock_llm_env['bus']
        tool_names = [name for name, _ in bus.call_log]
        assert 'search_kb' not in tool_names, "快速模式不应自动调用 search_kb"
        assert 'websearch__web_search' not in tool_names, "快速模式不应自动调用 websearch__web_search"
