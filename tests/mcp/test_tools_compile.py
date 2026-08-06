"""MCP 编译工具 handler 测试：compile_wiki + get_compile_status。

compile_wiki 异步触发编译，产出进入待审批状态。
get_compile_status 轮询进度，替代 SSE 推送。

测试策略：mock wiki_compiler，验证 handler 包装逻辑。
"""
import json
from unittest.mock import patch

import pytest


class TestCompileWiki:

    def test_starts_compile_and_returns_started(self, app):
        with app.app_context():
            with patch('modules.wiki.compiler.pipeline.compile_wiki',
                       return_value={'status': 'started'}) as mock_compile:
                from modules.mcp.tools_write import handle_compile_wiki
                result = handle_compile_wiki({})

        data = json.loads(result['content'][0]['text'])
        assert data.get('started') is True
        assert 'message' in data
        # 应调用 compile_wiki
        assert mock_compile.called

    def test_passes_incremental_default_true(self, app):
        with app.app_context():
            captured = {}

            def fake_compile(app_ref, incremental=True, init=False):
                captured['incremental'] = incremental
                captured['init'] = init
                return {'status': 'started'}

            with patch('modules.wiki.compiler.pipeline.compile_wiki',
                       side_effect=fake_compile):
                from modules.mcp.tools_write import handle_compile_wiki
                handle_compile_wiki({})

        assert captured['incremental'] is True
        assert captured['init'] is False

    def test_passes_init_flag(self, app):
        with app.app_context():
            captured = {}

            def fake_compile(app_ref, incremental=True, init=False):
                captured['init'] = init
                return {'status': 'started'}

            with patch('modules.wiki.compiler.pipeline.compile_wiki',
                       side_effect=fake_compile):
                from modules.mcp.tools_write import handle_compile_wiki
                handle_compile_wiki({'init': True})

        assert captured['init'] is True

    def test_already_running_returns_started_false(self, app):
        """编译已在进行中时返回 started=false。"""
        with app.app_context():
            with patch('modules.wiki.compiler.pipeline.compile_wiki',
                       return_value={'status': 'already_running'}):
                from modules.mcp.tools_write import handle_compile_wiki
                result = handle_compile_wiki({})

        data = json.loads(result['content'][0]['text'])
        assert data.get('started') is False

    def test_compile_failure_returns_isError_with_cost_warning(self, app):
        """编译失败时返回 isError 并提示可能已消耗 LLM 配额。"""
        with app.app_context():
            with patch('modules.wiki.compiler.pipeline.compile_wiki',
                       side_effect=RuntimeError('LLM error')):
                from modules.mcp.tools_write import handle_compile_wiki
                result = handle_compile_wiki({})

        assert result.get('isError') is True
        text = result['content'][0]['text']
        assert '配额' in text or 'LLM' in text


class TestGetCompileStatus:

    def test_returns_current_status_fields(self, app):
        fake_status = {
            'running': True,
            'progress': '提取概念 (3/10)',
            'errors': [],
            'completed': 3,
            'total': 10,
        }
        with app.app_context():
            with patch('modules.wiki.compiler.pipeline.get_compile_status',
                       return_value=fake_status):
                from modules.mcp.tools_read import handle_get_compile_status
                result = handle_get_compile_status({})

        data = json.loads(result['content'][0]['text'])
        assert data['running'] is True
        assert data['progress'] == '提取概念 (3/10)'
        assert data['completed'] == 3
        assert data['total'] == 10
        assert isinstance(data['errors'], list)

    def test_idle_status(self, app):
        fake_status = {
            'running': False,
            'progress': '',
            'errors': [],
            'completed': 0,
            'total': 0,
        }
        with app.app_context():
            with patch('modules.wiki.compiler.pipeline.get_compile_status',
                       return_value=fake_status):
                from modules.mcp.tools_read import handle_get_compile_status
                result = handle_get_compile_status({})

        data = json.loads(result['content'][0]['text'])
        assert data['running'] is False
