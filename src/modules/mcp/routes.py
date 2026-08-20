"""MCP Blueprint — /mcp 端点。

手写 JSON-RPC 2.0 分发器，实现 MCP streamable-HTTP（非 SSE）传输。

支持的 method：
- initialize / notifications/initialized / ping
- tools/list / tools/call
- DELETE /mcp（会话终止）

会话：准无状态。initialize 生成 Mcp-Session-Id（uuid4）存内存 set。
鉴权：可选 token（环境变量 ZSSNOTE_MCP_TOKEN）。
"""
import os
import uuid
from threading import Lock
from typing import Any, Dict, Optional

from flask import Blueprint, Response, jsonify, request

from .errors import (
    INVALID_PARAMS,
    INVALID_REQUEST,
    MCPError,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    UNAUTHORIZED,
)
from .registry import get_tool, list_tools


MCP_PROTOCOL_VERSION = '2025-06-18'
MCP_SERVER_NAME = 'PersonLLMWiki'
MCP_SERVER_VERSION = '1.0.0'

# 合法的 JSON-RPC 2.0 方法
_KNOWN_METHODS = {
    'initialize',
    'notifications/initialized',
    'ping',
    'tools/list',
    'tools/call',
}

# notification（无 id 的请求）集合
_NOTIFICATION_METHODS = {
    'notifications/initialized',
}

mcp_bp = Blueprint('mcp', __name__)

# 会话存储（进程内）
_sessions: set = set()
_sessions_lock = Lock()


def _make_jsonrpc_response(result: Any, request_id: Optional[Any] = None,
                           session_id: Optional[str] = None,
                           extra_headers: Optional[Dict[str, str]] = None) -> Response:
    """构造成功的 JSON-RPC 响应。"""
    body: Dict[str, Any] = {
        'jsonrpc': '2.0',
        'result': result,
    }
    if request_id is not None:
        body['id'] = request_id
    resp = jsonify(body)
    resp.status_code = 200
    if session_id:
        resp.headers['Mcp-Session-Id'] = session_id
    if extra_headers:
        for k, v in extra_headers.items():
            resp.headers[k] = v
    return resp


def _make_jsonrpc_error(code: int, message: str,
                        request_id: Optional[Any] = None,
                        data: Any = None,
                        http_status: int = 200) -> Response:
    """构造 JSON-RPC error 响应。"""
    err: Dict[str, Any] = {'code': code, 'message': message}
    if data is not None:
        err['data'] = data
    body: Dict[str, Any] = {
        'jsonrpc': '2.0',
        'error': err,
    }
    if request_id is not None:
        body['id'] = request_id
    resp = jsonify(body)
    resp.status_code = http_status
    return resp


def _check_token_auth():
    """Token 鉴权，返回权限级别。

    返回值：
    - 'admin' — 管理员，全权限
    - 'submitter' — 提交者，仅 submit_to_public
    - 'open' — 未设置任何 Token，全权限（向后兼容）

    权限分级：
    - 无 Token 配置 → open（向后兼容，全权限）
    - 匹配 ADMIN_TOKEN → admin（全权限）
    - 匹配 SUBMITTER_TOKEN → submitter（仅 submit_to_public + 只读工具）
    """
    from config import Config

    admin_token = Config.MCP_ADMIN_TOKEN
    submitter_token = Config.MCP_SUBMITTER_TOKEN

    # 无任何 Token 配置 → 完全放行
    if not admin_token and not submitter_token:
        return 'admin'

    auth = request.headers.get('Authorization', '')
    token = auth.replace('Bearer ', '') if auth.startswith('Bearer ') else ''

    if admin_token and token == admin_token:
        return 'admin'
    if submitter_token and token == submitter_token:
        return 'submitter'

    raise MCPError(UNAUTHORIZED, 'Unauthorized')


# 管理员专属工具（submitter 不可调用）
_ADMIN_ONLY_TOOLS = {
    'write_note', 'compile_wiki', 'approve_candidate',
    'reject_candidate', 'create_folder',
}


def _check_tool_permission(permission_level, tool_name):
    """检查工具调用权限"""
    if permission_level == 'admin' or permission_level == 'open':
        return
    if permission_level == 'submitter':
        if tool_name in _ADMIN_ONLY_TOOLS:
            raise MCPError(UNAUTHORIZED, f'权限不足：{tool_name} 需要管理员权限')


def _new_session() -> str:
    sid = str(uuid.uuid4())
    with _sessions_lock:
        _sessions.add(sid)
    return sid


def _is_valid_session(sid: str) -> bool:
    if not sid:
        return False
    with _sessions_lock:
        return sid in _sessions


def _is_notification(body: Dict[str, Any]) -> bool:
    """判断是否是 notification（无 id 的请求）。"""
    return 'id' not in body


def _handle_initialize(params: Dict[str, Any], body: Dict[str, Any]):
    sid = _new_session()
    result = {
        'protocolVersion': MCP_PROTOCOL_VERSION,
        'capabilities': {
            'tools': {},
        },
        'serverInfo': {
            'name': MCP_SERVER_NAME,
            'version': MCP_SERVER_VERSION,
        },
    }
    return _make_jsonrpc_response(result, body.get('id'), session_id=sid)


def _handle_ping(body: Dict[str, Any]):
    return _make_jsonrpc_response({}, body.get('id'))


def _handle_tools_list(body: Dict[str, Any]):
    tools = [t.to_public_dict() for t in list_tools()]
    return _make_jsonrpc_response({'tools': tools}, body.get('id'))


def _handle_tools_call(params: Dict[str, Any], body: Dict[str, Any]):
    if not isinstance(params, dict) or 'name' not in params:
        raise MCPError(INVALID_PARAMS, 'tools/call 缺少 name 参数')

    name = params.get('name')
    arguments = params.get('arguments', {}) or {}

    tool = get_tool(name)
    if tool is None:
        raise MCPError(INVALID_PARAMS, f'未知工具: {name}')

    try:
        result = tool.handler(arguments)
    except MCPError:
        # MCPError 透传为 JSON-RPC error（协议级错误，如路径越界）
        raise
    except Exception as e:
        # 工具内部异常按 MCP 规范返回 isError=true（非 JSON-RPC error）
        return _make_jsonrpc_response(
            {
                'isError': True,
                'content': [{'type': 'text', 'text': f'{type(e).__name__}: {e}'}],
            },
            body.get('id'),
        )

    # handler 正常返回 {content: [...]} 或 {isError: True, content: [...]}
    if not isinstance(result, dict):
        result = {'content': [{'type': 'text', 'text': str(result)}]}
    if 'content' not in result:
        result = {'content': [{'type': 'text', 'text': json_dumps(result)}]}

    return _make_jsonrpc_response(result, body.get('id'))


def json_dumps(obj):
    import json as _json
    return _json.dumps(obj, ensure_ascii=False)


@mcp_bp.route('/mcp', methods=['POST'])
def mcp_endpoint():
    """MCP JSON-RPC 端点。"""
    # 1. token 鉴权，获取权限级别
    try:
        permission_level = _check_token_auth()
    except MCPError as e:
        return _make_jsonrpc_error(e.code, e.message, request_id=None, http_status=401)

    # 2. 解析 JSON
    raw = request.get_data(as_text=True)
    try:
        import json
        body = json.loads(raw)
    except (ValueError, TypeError):
        return _make_jsonrpc_error(PARSE_ERROR, 'Parse error', request_id=None)

    # 3. 必须是合法 JSON-RPC 对象
    if not isinstance(body, dict):
        return _make_jsonrpc_error(INVALID_REQUEST, 'Invalid Request', request_id=None)
    if body.get('jsonrpc') != '2.0':
        return _make_jsonrpc_error(INVALID_REQUEST, 'Invalid Request',
                                   request_id=body.get('id'))
    method = body.get('method')
    if not method:
        return _make_jsonrpc_error(INVALID_REQUEST, 'Invalid Request',
                                   request_id=body.get('id'))

    # 4. notification（无 id）— 不返回 JSON-RPC 响应
    if _is_notification(body) and method in _NOTIFICATION_METHODS:
        return Response(b'', status=202, mimetype='application/json')

    params = body.get('params', {}) or {}

    # 5. 分发
    try:
        if method == 'initialize':
            return _handle_initialize(params, body)
        if method == 'ping':
            return _handle_ping(body)
        if method == 'tools/list':
            return _handle_tools_list(body)
        if method == 'tools/call':
            _check_tool_permission(permission_level, params.get('name', ''))
            return _handle_tools_call(params, body)
        # 未知方法
        return _make_jsonrpc_error(METHOD_NOT_FOUND, f'Method not found: {method}',
                                   request_id=body.get('id'))
    except MCPError as e:
        return _make_jsonrpc_error(e.code, e.message, request_id=body.get('id'),
                                   data=e.data)
    except Exception as e:
        from flask import current_app
        current_app.logger.exception('MCP dispatch error')
        return _make_jsonrpc_error(-32603, f'Internal error: {e}',
                                   request_id=body.get('id'))


@mcp_bp.route('/mcp', methods=['DELETE'])
def mcp_delete_session():
    """会话终止：客户端通过 DELETE /mcp 结束会话。

    带上 Mcp-Session-Id header，服务端从内存 set 移除。
    """
    sid = request.headers.get('Mcp-Session-Id', '')
    with _sessions_lock:
        _sessions.discard(sid)
    return Response(b'', status=200, mimetype='application/json')
