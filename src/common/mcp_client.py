"""MCP 客户端总线（Phase 4）。

LEGACY（1.1 标记，仅保留注释、不改运行逻辑）：
- 按三层架构收敛，外部 MCP 能力统一由 DSH 承接。
- 内置对话 agent 不再经本总线暴露远程工具。
- 本模块仅保留给内置 subprocess 服务（如 pdf-mcp）的生命周期管理与 MCP 管理 UI。
- 1.1 评估移除，详见 doc/01-架构/01-架构与集成.md 第三部分。

连接外部 MCP 服务器，统一工具发现和调用。
支持本地直连（进程内调用）和远程 HTTP 两种模式。

配置文件：resource/instance/mcp_servers.json
"""

import os
import json
import threading
import requests

from config import Config


_bus_lock = threading.RLock()
_bus_instance = None


def _config_path():
    return os.path.join(Config.INSTANCE_PATH, 'mcp_servers.json')


def _load_config():
    path = _config_path()
    if os.path.isfile(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {'servers': []}


def _save_config(config):
    path = _config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


class MCPRemoteClient:
    """连接一个外部 MCP 服务器的客户端。"""

    def __init__(self, name, url, token='', description=''):
        self.name = name
        self.url = url
        self.token = token
        self.description = description
        self._session_id = None
        self._tools = None
        self._connected = False
        self._error = ''

    def _headers(self):
        h = {
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/event-stream',
        }
        if self.token:
            h['Authorization'] = f'Bearer {self.token}'
        if self._session_id:
            h['Mcp-Session-Id'] = self._session_id
        return h

    def _parse_response(self, resp):
        """解析 JSON-RPC 响应，同时支持 JSON 和 SSE 格式"""
        content_type = resp.headers.get('Content-Type', '')

        if 'text/event-stream' in content_type:
            # SSE 格式：提取 data: 行中的 JSON
            text = resp.content.decode('utf-8', errors='replace')
            for line in text.split('\n'):
                line = line.strip()
                if line.startswith('data:'):
                    data_str = line[5:].strip()
                    if data_str:
                        return json.loads(data_str)
            # 没找到 data 行
            raise ValueError(f'SSE 响应中无 data 行')

        # 纯 JSON 格式 — 确保 UTF-8 解码
        resp.encoding = resp.apparent_encoding or 'utf-8'
        return resp.json()

    def _rpc(self, method, params=None):
        """发送 JSON-RPC 请求"""
        payload = {
            'jsonrpc': '2.0',
            'method': method,
            'params': params or {},
            'id': 1,
        }
        resp = requests.post(
            self.url, json=payload,
            headers=self._headers(),
            timeout=(3, 10),
        )
        # 捕获 Mcp-Session-Id（在 response header 中）
        sid = resp.headers.get('Mcp-Session-Id')
        if sid:
            self._session_id = sid
        return self._parse_response(resp)

    def connect(self):
        """初始化连接并发现工具"""
        try:
            # initialize
            result = self._rpc('initialize', {
                'protocolVersion': '2024-11-05',
                'capabilities': {},
                'clientInfo': {'name': 'PersonLLMWiki-Bus', 'version': '1.0'},
            })

            # 发送 initialized 通知
            try:
                requests.post(self.url, json={
                    'jsonrpc': '2.0', 'method': 'notifications/initialized',
                }, headers=self._headers(), timeout=(3, 5))
            except Exception:
                pass

            # 发现工具
            tools_result = self._rpc('tools/list')
            if 'result' in tools_result:
                self._tools = tools_result['result'].get('tools', [])
            elif 'error' in tools_result:
                self._error = f"tools/list 错误: {tools_result['error']}"
                self._tools = []
            else:
                self._tools = []

            self._connected = True
            if not self._tools and not self._error:
                self._error = ''
            return True

        except requests.exceptions.ConnectionError:
            self._error = f'无法连接: {self.url}'
            self._connected = False
            return False
        except Exception as e:
            self._error = str(e)
            self._connected = False
            return False

    def call_tool(self, name, arguments):
        """调用远程工具"""
        result = self._rpc('tools/call', {
            'name': name,
            'arguments': arguments or {},
        })

        if 'error' in result:
            return {
                'isError': True,
                'content': [{'type': 'text', 'text': result['error'].get('message', 'Unknown error')}],
            }
        return result.get('result', {'content': [{'type': 'text', 'text': 'No result'}]})

    def list_tools(self):
        """返回此服务器提供的工具列表"""
        if self._tools is None:
            return []
        # 给工具名加 server 前缀，避免冲突
        return [
            {
                **tool,
                'name': f'{self.name}__{tool["name"]}',
                '_server': self.name,
                '_original_name': tool['name'],
            }
            for tool in self._tools
        ]

    def status(self):
        return {
            'name': self.name,
            'url': self.url,
            'description': self.description,
            'connected': self._connected,
            'tool_count': len(self._tools or []),
            'error': self._error,
        }


class MCPClientBus:
    """MCP 客户端总线——管理多个 MCP 服务器连接 + 本地工具。"""

    def __init__(self):
        self._remote_clients = {}  # name -> MCPRemoteClient
        self._local_tools_cache = None

    def load_servers(self):
        """从配置文件加载并连接所有服务器"""
        config = _load_config()
        for server in config.get('servers', []):
            self.add_server(
                server['name'],
                server['url'],
                server.get('token', ''),
                server.get('description', ''),
            )

    def add_server(self, name, url, token='', description='', persist=True):
        """添加并连接一个 MCP 服务器。

        persist=False 用于内置预制服务器（如 pdf-mcp 子进程），
        每次启动 token 变化，不写入配置文件。
        """
        # 先在锁内创建/注册 client，锁外执行网络连接
        with _bus_lock:
            if name in self._remote_clients:
                client = self._remote_clients[name]
            else:
                client = MCPRemoteClient(name, url, token, description)
                self._remote_clients[name] = client

        # 网络连接在锁外执行，避免阻塞其他读取操作
        client.connect()

        if persist:
            with _bus_lock:
                # 持久化到配置文件
                config = _load_config()
                config['servers'] = [
                    s for s in config.get('servers', []) if s['name'] != name
                ]
                config['servers'].append({
                    'name': name, 'url': url,
                    'token': token, 'description': description,
                })
                _save_config(config)

        return client.status()

    def remove_server(self, name):
        """移除一个 MCP 服务器"""
        with _bus_lock:
            if name in self._remote_clients:
                del self._remote_clients[name]

            config = _load_config()
            config['servers'] = [
                s for s in config.get('servers', []) if s['name'] != name
            ]
            _save_config(config)

    def reconnect(self, name):
        """重新连接服务器"""
        with _bus_lock:
            client = self._remote_clients.get(name)
        if client:
            return client.connect()  # 网络连接在锁外执行
        return False

    def get_server_tools(self, name):
        """获取指定 MCP 服务器的工具列表"""
        with _bus_lock:
            client = self._remote_clients.get(name)
        if client and client._connected:
            return client.list_tools()
        return []

    def get_all_tools(self):
        """获取所有可用工具（本地 + 远程），统一格式"""
        tools = []

        # 本地工具
        try:
            from modules.mcp.registry import list_tools
            for tool in list_tools():
                tools.append({
                    'name': tool.name,
                    'description': tool.description,
                    'input_schema': tool.input_schema,
                    '_source': 'local',
                })
        except Exception:
            pass

        # 远程工具
        with _bus_lock:
            for client in self._remote_clients.values():
                if client._connected:
                    tools.extend(client.list_tools())

        return tools

    def get_tools_for_llm(self):
        """获取 LLM function calling 格式的工具列表"""
        tools = self.get_all_tools()
        return [
            {
                'type': 'function',
                'function': {
                    'name': t['name'],
                    'description': t.get('description', ''),
                    'parameters': t.get('input_schema', {
                        'type': 'object', 'properties': {},
                    }),
                },
            }
            for t in tools
        ]

    def call_tool(self, full_name, arguments):
        """统一工具调用入口。

        本地工具直接调用 handler；
        远程工具名格式为 server__tool_name，路由到对应 MCPRemoteClient。
        """
        # 远程工具
        if '__' in full_name:
            parts = full_name.split('__', 1)
            server_name, tool_name = parts[0], parts[1]
            with _bus_lock:
                client = self._remote_clients.get(server_name)
            if client:
                return client.call_tool(tool_name, arguments)
            return {
                'isError': True,
                'content': [{'type': 'text', 'text': f'MCP 服务器不存在: {server_name}'}],
            }

        # 本地工具
        from modules.mcp.registry import get_tool
        tool = get_tool(full_name)
        if tool is None:
            return {
                'isError': True,
                'content': [{'type': 'text', 'text': f'未知工具: {full_name}'}],
            }

        try:
            return tool.handler(arguments)
        except Exception as e:
            return {
                'isError': True,
                'content': [{'type': 'text', 'text': f'{type(e).__name__}: {e}'}],
            }

    def list_servers(self):
        """列出所有服务器状态"""
        with _bus_lock:
            return [client.status() for client in self._remote_clients.values()]


def get_bus():
    """获取全局 MCPClientBus 单例"""
    global _bus_instance
    if _bus_instance is None:
        with _bus_lock:
            if _bus_instance is None:
                _bus_instance = MCPClientBus()
        # load_servers 在锁外执行，避免网络连接阻塞其他读取
        _bus_instance.load_servers()
    return _bus_instance
