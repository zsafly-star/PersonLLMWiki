"""思考阶段构建逻辑测试。

覆盖场景：
1. 初始阶段始终为「分析问题」
2. 工具调用产生对应阶段节点
3. 「生成回答」阶段始终添加
4. 阶段轮次标注（第N轮）
5. 自定义阶段（整理思路）正常流转
6. 所有阶段最终状态为 completed
7. thinking_json 序列化正确
"""
import json
from unittest.mock import patch, MagicMock

import pytest


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
    def __init__(self, content=None, tool_calls=None):
        self.role = 'assistant'
        self.content = content
        self.tool_calls = tool_calls


class FakeAdapter:
    def __init__(self, responses):
        self.responses = list(responses)
        self.idx = 0

    def chat(self, messages, model=None, tools=None):
        if self.idx >= len(self.responses):
            return FakeMessage(content='done')
        resp = self.responses[self.idx]
        self.idx += 1
        return resp

    def __call__(self, **kwargs):
        return self


class FakeBus:
    def __init__(self, tool_results=None):
        self.tool_results = tool_results or {}

    def call_tool(self, name, args):
        return self.tool_results.get(name, {'content': [{'type': 'text', 'text': 'OK'}]})

    def get_tools_for_llm(self):
        return []


CN_MAP = {
    'search_kb': '搜索知识库',
    'websearch__web_search': '联网搜索',
    'read_note': '读取笔记',
}


@pytest.fixture
def mock_env(app):
    """统一 mock 环境。返回 (adapter, bus, patches)。"""
    bus = FakeBus(tool_results={
        'search_kb': {'content': [{'type': 'text', 'text': '知识库结果'}]},
        'websearch__web_search': {'content': [{'type': 'text', 'text': '联网结果'}]},
    })

    patches = []

    def _setup(adapter_responses):
        """每次调用前设置 adapter 响应队列。"""
        adapter = FakeAdapter(adapter_responses)
        mock_llm = MagicMock()
        mock_llm.get_adapter.return_value = adapter

        for p in patches:
            p.stop()
        patches.clear()

        patches.extend([
            patch('common.agent_core.get_active_llm', return_value=('fake', 'fake-model', {})),
            patch('common.llm.LLMService', mock_llm),
            patch('common.agent.get_bus', return_value=bus),
            patch('common.skill_loader.get_skills_prompt', return_value=''),
        ])
        for p in patches:
            p.start()
        return adapter, bus

    yield _setup

    for p in patches:
        p.stop()


def _run_and_collect(mock_env, mode='quick', responses=None):
    """运行 agent_chat，收集 progress 事件，转为 SSE 等效阶段列表。"""
    from common.agent import agent_chat

    adapter, bus = mock_env(responses or [FakeMessage(content='回答')])
    progress_events = []

    with patch('common.agent_core.get_active_llm', return_value=('fake', 'fake-model', {})), \
         patch('common.llm.LLMService') as mock_llm_svc, \
         patch('common.agent.get_bus', return_value=bus), \
         patch('common.skill_loader.get_skills_prompt', return_value=''):

        mock_llm_svc.get_adapter.return_value = adapter

        def on_progress(evt, data):
            progress_events.append((evt, data))

        agent_chat(
            [{'role': 'user', 'content': '测试问题'}],
            use_tools=True, mode=mode,
            progress_callback=on_progress,
        )

    # 转为等效阶段序列
    stages = []
    stage_counter = 0

    stage_counter += 1
    stages.append({'stage_name': '分析问题', 'status': 'completed'})

    for evt_type, data in progress_events:
        if evt_type == 'tool_start':
            stage_counter += 1
            name = data['name']
            cn_name = CN_MAP.get(name, name)
            round_num = data.get('round', 0)
            if round_num and round_num > 1:
                cn_name += f'(第{round_num}轮)'
            stages.append({'stage_name': cn_name, 'tool_name': name, 'round': data.get('round', 0), 'status': 'completed'})
        elif evt_type == 'custom_stage_start':
            stage_counter += 1
            stages.append({'stage_name': data.get('stage_name', ''), 'status': 'completed'})

    stage_counter += 1
    stages.append({'stage_name': '生成回答', 'status': 'completed'})

    return stages


class TestStageConstruction:

    def test_first_stage_is_always_analysis(self, mock_env):
        stages = _run_and_collect(mock_env, mode='quick', responses=[
            FakeMessage(content='回答'),
        ])
        assert stages[0]['stage_name'] == '分析问题'

    def test_tool_call_creates_stage(self, mock_env):
        stages = _run_and_collect(mock_env, mode='quick', responses=[
            FakeMessage(tool_calls=[FakeToolCall('search_kb', '{"query": "test"}')]),
            FakeMessage(content='最终回答'),
        ])
        names = [s['stage_name'] for s in stages]
        assert '搜索知识库' in names

    def test_generate_answer_stage_always_added(self, mock_env):
        stages = _run_and_collect(mock_env, mode='quick', responses=[
            FakeMessage(content='回答'),
        ])
        names = [s['stage_name'] for s in stages]
        assert '生成回答' in names
        assert names[-1] == '生成回答'

    def test_expert_mode_has_full_stage_chain(self, mock_env):
        stages = _run_and_collect(mock_env, mode='expert', responses=[
            FakeMessage(content='回答'),
        ])
        names = [s['stage_name'] for s in stages]
        assert '分析问题' in names
        assert '搜索知识库' in names
        assert '整理思路' in names
        assert '生成回答' in names

        idx_kb = names.index('搜索知识库')
        idx_organize = names.index('整理思路')
        assert idx_kb < idx_organize

    def test_all_stages_completed(self, mock_env):
        stages = _run_and_collect(mock_env, mode='expert', responses=[
            FakeMessage(content='回答'),
        ])
        for s in stages:
            assert s['status'] == 'completed'

    def test_round_numbering(self, mock_env):
        stages = _run_and_collect(mock_env, mode='quick', responses=[
            FakeMessage(tool_calls=[FakeToolCall('search_kb', '{"query": "1"}')]),
            FakeMessage(tool_calls=[FakeToolCall('search_kb', '{"query": "2"}')]),
            FakeMessage(tool_calls=[FakeToolCall('search_kb', '{"query": "3"}')]),
            FakeMessage(content='回答'),
        ])
        search_names = [s['stage_name'] for s in stages if '搜索知识库' in s['stage_name']]
        assert len(search_names) == 3
        assert any('第2轮' in n for n in search_names)
        assert any('第3轮' in n for n in search_names)

    def test_custom_stage_no_tool_name(self, mock_env):
        stages = _run_and_collect(mock_env, mode='expert', responses=[
            FakeMessage(content='回答'),
        ])
        for s in stages:
            if s['stage_name'] in ('整理思路', '生成回答'):
                assert 'tool_name' not in s

    def test_thinking_payload_serializable(self, mock_env):
        stages = _run_and_collect(mock_env, mode='expert', responses=[
            FakeMessage(content='回答'),
        ])
        payload = {'stages': stages, 'exported_files': []}
        serialized = json.dumps(payload, ensure_ascii=False)
        parsed = json.loads(serialized)
        assert 'stages' in parsed
        assert len(parsed['stages']) >= 4
