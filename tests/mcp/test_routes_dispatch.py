"""MCP /mcp 端点 JSON-RPC 分发测试。

覆盖：
- 协议握手 initialize（返回 protocolVersion / capabilities / serverInfo）
- notifications/initialized（notification，无 JSON-RPC 响应）
- ping（返回空 result）
- tools/list（返回工具清单数组）
- tools/call 成功路径（调 handler，返回 content）
- tools/call 未知工具（-32602 Invalid params）
- tools/call handler 抛 MCPError（透传 JSON-RPC error）
- tools/call handler 抛普通异常（isError=true）
- method 不存在（-32601 Method not found）
- 非 JSON body（-32700 Parse error）
- 缺 method 字段（-32600 Invalid request）
- Mcp-Session-Id 校验：initialize 创建 session，后续请求需要带
- 可选 token 鉴权：设置了 MCP_TOKEN 后无 Authorization → -32001
"""
import json

import pytest


# ---------- helpers ----------

def rpc(client, method, params=None, request_id=1, session_id=None, raw=None, headers=None):
    """发一个 JSON-RPC 请求。raw 非 None 时直接用 raw 作为 body。"""
    body = raw if raw is not None else {
        'jsonrpc': '2.0',
        'id': request_id,
        'method': method,
    }
    if params is not None:
        body['params'] = params

    h = {'Content-Type': 'application/json'}
    if session_id:
        h['Mcp-Session-Id'] = session_id
    if headers:
        h.update(headers)

    return client.post('/mcp', data=json.dumps(body), headers=h)


def assert_rpc_success(resp):
    """断言响应是成功的 JSON-RPC（有 result，无 error）。"""
    assert resp.status_code == 200, resp.get_data(as_text=True)
    payload = resp.get_json()
    assert payload is not None, '响应不是 JSON'
    assert 'error' not in payload, f'意外错误: {payload}'
    assert 'result' in payload
    return payload


def assert_rpc_error(resp, expected_code):
    """断言响应是 JSON-RPC error 且 code 匹配。"""
    payload = resp.get_json()
    assert payload is not None, '响应不是 JSON'
    assert 'error' in payload, f'应该返回 error，实际: {payload}'
    assert payload['error']['code'] == expected_code, (
        f'错误码应为 {expected_code}，实际 {payload["error"]["code"]}: {payload["error"].get("message")}'
    )
    return payload


# ---------- initialize / 握手 ----------

class TestInitialize:

    def test_initialize_returns_protocol_version_and_capabilities(self, client):
        resp = rpc(client, 'initialize', params={
            'protocolVersion': '2025-06-18',
            'capabilities': {},
            'clientInfo': {'name': 'test-client', 'version': '0.0.1'},
        })
        payload = assert_rpc_success(resp)
        result = payload['result']
        assert result['protocolVersion'] == '2025-06-18'
        assert 'capabilities' in result
        assert 'serverInfo' in result
        assert 'name' in result['serverInfo']

    def test_initialize_assigns_session_id(self, client):
        resp = rpc(client, 'initialize', params={})
        assert 'Mcp-Session-Id' in resp.headers
        sid = resp.headers['Mcp-Session-Id']
        assert sid and len(sid) > 0

    def test_initialize_id_zero_is_valid(self, client):
        resp = rpc(client, 'initialize', params={}, request_id=0)
        payload = resp.get_json()
        assert payload is not None
        assert payload.get('id') == 0


# ---------- notification ----------

class TestNotification:

    def test_initialized_notification_no_jsonrpc_body(self, client):
        # notification：无 id 的请求
        body = {'jsonrpc': '2.0', 'method': 'notifications/initialized'}
        resp = client.post('/mcp', data=json.dumps(body),
                           headers={'Content-Type': 'application/json'})
        # notification 规范要求服务端不返回 JSON-RPC 响应
        assert resp.status_code in (202, 200)
        # body 应为空（不能是 JSON-RPC 响应对象）
        assert resp.data == b'' or resp.data.strip() in (b'', b'null')


# ---------- ping ----------

class TestPing:

    def test_ping_returns_empty_result(self, client):
        resp = rpc(client, 'ping')
        assert_rpc_success(resp)


# ---------- tools/list ----------

class TestToolsList:

    def test_list_returns_tools_array(self, client):
        resp = rpc(client, 'tools/list')
        payload = assert_rpc_success(resp)
        result = payload['result']
        assert 'tools' in result
        assert isinstance(result['tools'], list)

    def test_listed_tool_has_required_fields(self, client):
        from modules.mcp.registry import register_tool, clear_registry, Tool
        clear_registry()
        register_tool(Tool(
            name='dummy',
            description='测试工具',
            input_schema={'type': 'object', 'properties': {}},
            handler=lambda args: {'content': [{'type': 'text', 'text': 'ok'}]},
        ))
        try:
            resp = rpc(client, 'tools/list')
            payload = assert_rpc_success(resp)
            tools = payload['result']['tools']
            assert any(t['name'] == 'dummy' for t in tools)
            dummy = next(t for t in tools if t['name'] == 'dummy')
            assert 'description' in dummy
            assert 'inputSchema' in dummy
        finally:
            clear_registry()


# ---------- tools/call ----------

class TestToolsCall:

    def test_call_invokes_handler_and_returns_content(self, client):
        from modules.mcp.registry import register_tool, clear_registry, Tool
        clear_registry()
        register_tool(Tool(
            name='echo',
            description='回显参数',
            input_schema={
                'type': 'object',
                'properties': {'msg': {'type': 'string'}},
                'required': ['msg'],
            },
            handler=lambda args: {'content': [{'type': 'text', 'text': args.get('msg', '')}]},
        ))
        try:
            resp = rpc(client, 'tools/call', params={
                'name': 'echo',
                'arguments': {'msg': 'hello'},
            })
            payload = assert_rpc_success(resp)
            result = payload['result']
            assert 'content' in result
            assert result['content'][0]['text'] == 'hello'
        finally:
            clear_registry()

    def test_call_unknown_tool_returns_invalid_params(self, client):
        from modules.mcp.registry import clear_registry
        clear_registry()
        resp = rpc(client, 'tools/call', params={
            'name': 'does_not_exist',
            'arguments': {},
        })
        assert_rpc_error(resp, -32602)

    def test_call_handler_raises_mcperror_returns_error(self, client):
        from modules.mcp.registry import register_tool, clear_registry, Tool
        from modules.mcp.errors import MCPError, INVALID_PARAMS
        clear_registry()

        def bad_handler(args):
            raise MCPError(INVALID_PARAMS, '坏参数')

        register_tool(Tool(
            name='bad',
            description='会失败的工具',
            input_schema={'type': 'object'},
            handler=bad_handler,
        ))
        try:
            resp = rpc(client, 'tools/call', params={'name': 'bad', 'arguments': {}})
            assert_rpc_error(resp, -32602)
        finally:
            clear_registry()

    def test_call_handler_raises_generic_exception_returns_isError(self, client):
        """工具内部异常按 MCP 规范返回 isError=true（非 JSON-RPC error）。"""
        from modules.mcp.registry import register_tool, clear_registry, Tool
        clear_registry()

        def crash_handler(args):
            raise RuntimeError('boom')

        register_tool(Tool(
            name='crash',
            description='会崩溃的工具',
            input_schema={'type': 'object'},
            handler=crash_handler,
        ))
        try:
            resp = rpc(client, 'tools/call', params={'name': 'crash', 'arguments': {}})
            payload = resp.get_json()
            assert payload is not None
            # 规范要求：工具异常返回 isError=true（仍 200 OK）
            assert resp.status_code == 200
            result = payload.get('result', {})
            assert result.get('isError') is True
            assert 'content' in result
        finally:
            clear_registry()

    def test_call_missing_name_returns_invalid_params(self, client):
        resp = rpc(client, 'tools/call', params={'arguments': {}})
        assert_rpc_error(resp, -32602)


# ---------- method 分发错误 ----------

class TestMethodDispatch:

    def test_unknown_method_returns_method_not_found(self, client):
        resp = rpc(client, 'nonexistent/method')
        assert_rpc_error(resp, -32601)

    def test_missing_method_field_returns_invalid_request(self, client):
        # 只有 jsonrpc 和 id，没有 method
        body = {'jsonrpc': '2.0', 'id': 1}
        resp = client.post('/mcp', data=json.dumps(body),
                           headers={'Content-Type': 'application/json'})
        assert_rpc_error(resp, -32600)


# ---------- JSON 解析错误 ----------

class TestParseErrors:

    def test_invalid_json_returns_parse_error(self, client):
        resp = client.post('/mcp', data='not json{',
                           headers={'Content-Type': 'application/json'})
        assert_rpc_error(resp, -32700)


# ---------- 可选 token 鉴权 ----------

class TestTokenAuth:

    def test_token_set_but_missing_header_returns_unauthorized(self, client, monkeypatch):
        monkeypatch.setenv('ZSSNOTE_MCP_TOKEN', 'secret')
        resp = rpc(client, 'ping')
        assert_rpc_error(resp, -32001)

    def test_token_set_wrong_value_returns_unauthorized(self, client, monkeypatch):
        monkeypatch.setenv('ZSSNOTE_MCP_TOKEN', 'secret')
        resp = rpc(client, 'ping', headers={'Authorization': 'Bearer wrong'})
        assert_rpc_error(resp, -32001)

    def test_token_set_correct_value_passes(self, client, monkeypatch):
        monkeypatch.setenv('ZSSNOTE_MCP_TOKEN', 'secret')
        resp = rpc(client, 'ping', headers={'Authorization': 'Bearer secret'})
        assert_rpc_success(resp)
