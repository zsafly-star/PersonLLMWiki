"""MCP 集成测试：模拟 WorkBuddy 客户端的完整交互流程。

覆盖设计方案 §11 的"集成测试"要求：
- initialize → tools/list → tools/call 完整流程
- 编译流程：compile_wiki → 轮询 get_compile_status → list_candidates → approve
- 路径安全边界
"""
import json
import os
from unittest.mock import patch

import pytest


def rpc(client, method, params=None, sid=None):
    """发 JSON-RPC 请求并返回 (status, headers, body_dict)。"""
    body = {'jsonrpc': '2.0', 'id': 1, 'method': method}
    if params is not None:
        body['params'] = params
    headers = {'Content-Type': 'application/json'}
    if sid:
        headers['Mcp-Session-Id'] = sid
    resp = client.post('/mcp', data=json.dumps(body), headers=headers)
    try:
        payload = resp.get_json()
    except Exception:
        payload = None
    return resp.status_code, dict(resp.headers), payload


class TestWorkBuddyFullFlow:
    """模拟 WorkBuddy 客户端从连接到完成多个操作的完整流程。"""

    def test_full_session_lifecycle(self, app, client, db):
        """完整会话生命周期：initialize → tools/list → 多个 tools/call。"""
        # 1. initialize
        status, headers, payload = rpc(client, 'initialize', {
            'protocolVersion': '2025-06-18',
            'capabilities': {},
            'clientInfo': {'name': 'workbuddy', 'version': '1.0'},
        })
        assert status == 200
        sid = headers.get('Mcp-Session-Id')
        assert sid
        assert payload['result']['protocolVersion'] == '2025-06-18'
        assert payload['result']['serverInfo']['name'] == 'PersonLLMWiki'

        # 2. notifications/initialized（客户端通知初始化完成）
        body = {'jsonrpc': '2.0', 'method': 'notifications/initialized'}
        resp = client.post('/mcp', data=json.dumps(body),
                           headers={'Content-Type': 'application/json',
                                    'Mcp-Session-Id': sid})
        assert resp.status_code in (200, 202)

        # 3. tools/list
        status, _, payload = rpc(client, 'tools/list', sid=sid)
        assert status == 200
        tool_names = [t['name'] for t in payload['result']['tools']]
        # 应包含全部 13 个工具
        expected = {
            'list_folders', 'read_note', 'list_wiki_pages', 'read_wiki_page',
            'get_compile_status', 'list_candidates', 'get_graph',
            'search_kb', 'write_note', 'compile_wiki',
            'approve_candidate', 'reject_candidate', 'create_folder',
        }
        assert expected.issubset(set(tool_names)), (
            f'缺失工具: {expected - set(tool_names)}'
        )

        # 4. tools/call create_folder
        status, _, payload = rpc(client, 'tools/call', {
            'name': 'create_folder', 'arguments': {'path': '工作笔记'},
        }, sid=sid)
        assert status == 200
        result = json.loads(payload['result']['content'][0]['text'])
        assert result['created'] is True

        # 5. tools/call write_note
        status, _, payload = rpc(client, 'tools/call', {
            'name': 'write_note',
            'arguments': {
                'path': '工作笔记/会议纪要.md',
                'content': '# 周会\n\n## 议题\n\n1. 进度同步\n2. 风险评估\n',
            },
        }, sid=sid)
        assert status == 200
        result = json.loads(payload['result']['content'][0]['text'])
        assert result['created'] is True

        # 6. tools/call list_folders
        status, _, payload = rpc(client, 'tools/call', {
            'name': 'list_folders', 'arguments': {},
        }, sid=sid)
        assert status == 200
        folders = json.loads(payload['result']['content'][0]['text'])
        names = [f['name'] for f in folders]
        assert '工作笔记' in names

        # 7. tools/call read_note
        status, _, payload = rpc(client, 'tools/call', {
            'name': 'read_note',
            'arguments': {'path': '工作笔记/会议纪要.md', 'full': True},
        }, sid=sid)
        assert status == 200
        note = json.loads(payload['result']['content'][0]['text'])
        assert '周会' in note['content']

        # 8. DELETE 会话
        resp = client.delete('/mcp', headers={'Mcp-Session-Id': sid})
        assert resp.status_code == 200

    def test_compile_and_approval_flow(self, app, client, db):
        """编译 + 审批流程：compile → status → candidates → approve。"""
        sid = rpc(client, 'initialize')[1].get('Mcp-Session-Id')

        # compile_wiki（mock 真实编译）
        with patch('modules.wiki.compiler.pipeline.compile_wiki',
                   return_value={'status': 'started'}):
            status, _, payload = rpc(client, 'tools/call', {
                'name': 'compile_wiki', 'arguments': {'incremental': True},
            }, sid=sid)
        assert status == 200
        result = json.loads(payload['result']['content'][0]['text'])
        assert result['started'] is True

        # get_compile_status（mock）
        with patch('modules.wiki.compiler.pipeline.get_compile_status',
                   return_value={'running': True, 'progress': '提取中', 'completed': 2, 'total': 5, 'errors': []}):
            status, _, payload = rpc(client, 'tools/call', {
                'name': 'get_compile_status', 'arguments': {},
            }, sid=sid)
        assert status == 200
        status_data = json.loads(payload['result']['content'][0]['text'])
        assert status_data['running'] is True

        # 准备一个 pending 候选页
        from modules.wiki.models import WikiPage
        with app.app_context():
            page = WikiPage(
                title='LLM 生成的概念', slug='llm_concept', body='# 内容',
                summary='', sources='[]', links='[]',
                review_status='pending',
            )
            db.session.add(page)
            db.session.commit()
            page_id = page.id

        # list_candidates
        status, _, payload = rpc(client, 'tools/call', {
            'name': 'list_candidates', 'arguments': {},
        }, sid=sid)
        assert status == 200
        candidates = json.loads(payload['result']['content'][0]['text'])
        assert len(candidates) == 1
        assert candidates[0]['id'] == page_id

        # approve_candidate
        status, _, payload = rpc(client, 'tools/call', {
            'name': 'approve_candidate', 'arguments': {'id': page_id},
        }, sid=sid)
        assert status == 200
        result = json.loads(payload['result']['content'][0]['text'])
        assert result['approved'] is True

        # 验证已转为 approved
        with app.app_context():
            page = db.session.get(WikiPage, page_id)
            assert page.review_status == 'approved'

    def test_security_boundaries_through_protocol(self, app, client, db):
        """通过 MCP 协议触发安全边界。"""
        sid = rpc(client, 'initialize')[1].get('Mcp-Session-Id')

        # 路径越界
        status, _, payload = rpc(client, 'tools/call', {
            'name': 'write_note',
            'arguments': {'path': '../../../etc/evil.md', 'content': 'bad'},
        }, sid=sid)
        assert payload['error']['code'] == -32602

        # 非法扩展名
        status, _, payload = rpc(client, 'tools/call', {
            'name': 'write_note',
            'arguments': {'path': 'evil.exe', 'content': 'bad'},
        }, sid=sid)
        assert payload['error']['code'] == -32602

        # 未知工具
        status, _, payload = rpc(client, 'tools/call', {
            'name': 'delete_note',  # 设计上故意不提供
            'arguments': {},
        }, sid=sid)
        assert payload['error']['code'] == -32602

    def test_all_tools_have_valid_schema(self, app, client, db):
        """tools/list 返回的所有工具必须有合法的 inputSchema。"""
        sid = rpc(client, 'initialize')[1].get('Mcp-Session-Id')
        status, _, payload = rpc(client, 'tools/list', sid=sid)
        tools = payload['result']['tools']

        for tool in tools:
            assert 'name' in tool, f'工具缺 name: {tool}'
            assert 'description' in tool, f'{tool["name"]} 缺 description'
            assert 'inputSchema' in tool, f'{tool["name"]} 缺 inputSchema'
            schema = tool['inputSchema']
            assert schema.get('type') == 'object', f'{tool["name"]} schema type 不是 object'
            assert 'properties' in schema, f'{tool["name"]} schema 缺 properties'

    def test_protocol_error_handling(self, app, client, db):
        """协议级错误处理。"""
        # 非 JSON
        resp = client.post('/mcp', data='not json',
                           headers={'Content-Type': 'application/json'})
        payload = resp.get_json()
        assert payload['error']['code'] == -32700

        # 缺 method
        body = {'jsonrpc': '2.0', 'id': 1}
        resp = client.post('/mcp', data=json.dumps(body),
                           headers={'Content-Type': 'application/json'})
        payload = resp.get_json()
        assert payload['error']['code'] == -32600

        # 未知 method
        status, _, payload = rpc(client, 'some/unknown/method')
        assert payload['error']['code'] == -32601
