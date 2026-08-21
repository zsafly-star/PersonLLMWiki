"""MCP 客户端总线管理路由（Phase 4）。

管理外部 MCP 服务器连接，提供统一工具发现/调用接口。
"""

from flask import Blueprint, request
from common.response import success_response, error_response
from common.mcp_client import get_bus
from .registry import list_tools as list_builtin_tools

mcp_client_bp = Blueprint('mcp_client', __name__)


# ═══ 内置工具分组 ═══

_BUILTIN_GROUPS = [
    {
        'id': 'knowledge',
        'name': '知识库',
        'icon': 'books',
        'description': 'Wiki 知识管理、文章读写、语义检索、知识星链、编译审批',
        'tool_patterns': [
            'list_folders', 'read_note', 'list_wiki_pages', 'read_wiki_page',
            'get_compile_status', 'list_candidates', 'get_graph', 'search_kb',
            'write_note', 'compile_wiki', 'approve_candidate',
            'reject_candidate', 'create_folder',
        ],
    },
    {
        'id': 'task',
        'name': '任务管理',
        'icon': 'check',
        'description': '创建待办、提交公共库',
        'tool_patterns': [
            'create_todo', 'submit_to_public',
        ],
    },
]


def _get_local_tool_safe(name):
    """安全获取本地工具（不存在返回 None）"""
    try:
        from .registry import get_tool as _get
        return _get(name)
    except Exception:
        return None


@mcp_client_bp.route('/api/mcp/builtin', methods=['GET'])
def list_builtin():
    """列出内置 MCP 工具分组及状态"""
    all_tools = {t.name: t for t in list_builtin_tools()}
    groups = []

    for g in _BUILTIN_GROUPS:
        tools = []
        for name in g['tool_patterns']:
            t = all_tools.get(name)
            if t:
                tools.append({
                    'name': t.name,
                    'description': t.description,
                    'cost': t.cost,
                })

        group = {
            'id': g['id'],
            'name': g['name'],
            'icon': g['icon'],
            'description': g['description'],
            'tools': tools,
            'tool_count': len(tools),
            'available': True,
        }

        groups.append(group)

    total_tools = sum(g['tool_count'] for g in groups)
    return success_response({
        'groups': groups,
        'total_tools': total_tools,
        'total_groups': len(groups),
    })


# ═══ 统一服务列表（内置 + 自定义） ═══

@mcp_client_bp.route('/api/mcp/services', methods=['GET'])
def list_all_services():
    """统一列出所有 MCP 服务（内置 + 自定义），带来源/位置标签。

    合并两个数据源：
    - bin/mcp/*/service.json → builtin 服务（source=builtin, location 从声明读取）
    - mcp_servers.json 配置  → custom 服务（source=custom, location=remote）
    运行时状态（connected/tool_count）从 MCPClientBus._remote_clients 获取。
    """
    from common.builtin_mcp_manager import get_status as _builtin_status
    from common.mcp_client import _bus_lock, _load_config

    bus = get_bus()

    # 获取运行时连接状态（锁内拷贝，锁外读取）
    with _bus_lock:
        runtime = {name: c.status() for name, c in bus._remote_clients.items()}
        config = _load_config()

    services = []
    seen_names = set()

    # 1. 内置服务（bin/mcp/*/service.json）
    from .registry import list_tools as _local_tool_count
    from flask import request as _req
    host_url = _req.host_url.rstrip('/') if _req else 'http://localhost:5000'

    builtin_statuses = _builtin_status()
    for name, st in builtin_statuses.items():
        seen_names.add(name)
        rt = runtime.get(name, {})
        st_type = st.get('type', '')
        # embedded 类型：从 _BUILTIN_GROUPS 计算工具数，personllmwiki 返回全部
        if st_type == 'embedded':
            if name == 'personllmwiki':
                # personllmwiki 工具数 = 全部本地工具
                tc = len(_local_tool_count())
            else:
                tc = sum(1 for g in _BUILTIN_GROUPS
                         if g.get('id') == name
                         for _ in g.get('tool_patterns', [])
                         if _get_local_tool_safe(_))
            url = f'{host_url}/mcp'
            err = ''
        else:
            tc = rt.get('tool_count') or st.get('tool_count', 0)
            url = rt.get('url', '')
            # 已连接且有工具 → 清除残留旧错误（启动竞态导致）
            err = st.get('error', '') or rt.get('error', '')
            if st.get('running') and (tc or st.get('tool_count')):
                err = ''
        services.append({
            'name': name,
            'description': st.get('description', ''),
            'source': st.get('source', 'builtin'),
            'location': st.get('location', 'local'),
            'type': st_type,
            'connected': st.get('running', False),
            'tool_count': tc,
            'url': url,
            'error': err,
                'can_delete': False,
                'can_reconnect': st_type == 'subprocess',
            })

    # 2. 自定义服务（mcp_servers.json，排除已列出的内置服务）
    for svc in config.get('servers', []):
        name = svc['name']
        if name in seen_names:
            continue
        seen_names.add(name)
        rt = runtime.get(name, {})
        services.append({
            'name': name,
            'description': svc.get('description', ''),
            'source': 'custom',
            'location': 'remote',
            'type': 'remote',
            'connected': rt.get('connected', False),
            'tool_count': rt.get('tool_count', 0),
            'url': svc.get('url', ''),
            'error': rt.get('error', ''),
            'can_delete': True,
            'can_reconnect': True,
        })

    # 3. PersonLLMWiki 自身 MCP Server：embedded 类型，始终可用，不依赖后台线程
    if 'personllmwiki' not in seen_names:
        services.append({
            'name': 'personllmwiki',
            'description': 'PersonLLMWiki 自身 MCP Server，提供知识库读写、Wiki 编译、搜索等工具',
            'source': 'builtin',
            'location': 'local',
            'type': 'embedded',
            'connected': True,
            'tool_count': len(_local_tool_count()),
            'url': f'{host_url}/mcp',
            'error': '',
            'can_delete': False,
            'can_reconnect': False,
        })

    return success_response({
        'services': services,
        'total': len(services),
        'builtin_count': sum(1 for s in services if s['source'] == 'builtin'),
        'custom_count': sum(1 for s in services if s['source'] == 'custom'),
    })


@mcp_client_bp.route('/api/mcp/servers', methods=['GET'])
def list_servers():
    """列出所有 MCP 服务器状态"""
    bus = get_bus()
    return success_response(bus.list_servers())


@mcp_client_bp.route('/api/mcp/servers', methods=['POST'])
def add_server():
    """添加 MCP 服务器"""
    data = request.get_json(silent=True) or {}
    name = data.get('name')
    url = data.get('url')

    if not name or not url:
        return error_response('name 和 url 必填', 400)

    bus = get_bus()
    status = bus.add_server(name, url, data.get('token', ''), data.get('description', ''))
    return success_response(status, '服务器已添加')


@mcp_client_bp.route('/api/mcp/servers/<name>', methods=['DELETE'])
def remove_server(name):
    """移除 MCP 服务器"""
    bus = get_bus()
    bus.remove_server(name)
    return success_response(None, '服务器已移除')


@mcp_client_bp.route('/api/mcp/servers/<name>/reconnect', methods=['POST'])
def reconnect_server(name):
    """重新连接 MCP 服务器。
    
    内置 subprocess 服务：通过 builtin_mcp_manager 重启子进程。
    自定义/remote 服务：通过 MCPClientBus 重连。
    """
    from common.builtin_mcp_manager import is_running, get_builtin_names, _discover_services, start_service, _stop_service

    # 内置服务 → 重启子进程 + 重新注册
    if name in get_builtin_names():
        svcs = _discover_services()
        svc = next((s for s in svcs if s['name'] == name), None)
        if not svc:
            return error_response(f'内置服务 {name} 未找到', 404)
        svc_type = svc.get('type', '')
        if svc_type == 'embedded':
            return error_response('embedded 服务无需重连', 400)
        if svc_type == 'binary':
            return error_response('binary 服务无需重连', 400)
        # subprocess：停止旧子进程，重新启动
        _stop_service(name)
        import time
        time.sleep(1)
        result = start_service(svc)
        if result.get('running'):
            return success_response({'name': name, 'tool_count': result.get('tool_count', 0)}, '重新连接成功')
        else:
            return error_response(result.get('error', '重新连接失败'), 400)

    # 自定义服务 → MCPClientBus 重连
    bus = get_bus()
    if bus.reconnect(name):
        return success_response(None, '重新连接成功')
    return error_response('重新连接失败', 400)


@mcp_client_bp.route('/api/mcp/servers/<name>/tools', methods=['GET'])
def list_server_tools(name):
    """列出指定 MCP 服务器的工具。

    对于 subprocess/remote 类型，从 MCPClientBus 获取工具列表。
    对于内置 binary/embedded 类型，从本地 MCP Server 注册表获取对应工具。
    """
    bus = get_bus()
    tools = bus.get_server_tools(name)
    if tools:
        return success_response(tools)

    # 内置 binary/embedded 服务：从本地工具注册表按 _BUILTIN_GROUPS 匹配
    from .registry import list_tools as _list_local_tools
    from common.builtin_mcp_manager import get_status as _builtin_status
    from .registry import get_tool as _get_local_tool

    builtin = _builtin_status().get(name)
    if builtin and builtin.get('type') in ('binary', 'embedded'):
        # 按 _BUILTIN_GROUPS 中的 tool_patterns 匹配
        for group in _BUILTIN_GROUPS:
            if group.get('id') == name and 'tool_patterns' in group:
                local_tools = []
                for pattern in group['tool_patterns']:
                    t = _get_local_tool(pattern)
                    if t:
                        local_tools.append({
                            'name': t.name,
                            'description': t.description,
                            'inputSchema': t.input_schema,
                            '_original_name': t.name,
                        })
                return success_response(local_tools)
        # PersonLLMWiki embedded：无分组匹配，返回全部本地工具
        if name == 'personllmwiki':
            all_tools = _list_local_tools()
            return success_response([{
                'name': t.name,
                'description': t.description,
                'inputSchema': t.input_schema,
                '_original_name': t.name,
            } for t in all_tools])

    return success_response([])


@mcp_client_bp.route('/api/mcp/tools', methods=['GET'])
def list_all_tools():
    """列出所有可用工具（本地 + 远程）"""
    bus = get_bus()
    return success_response(bus.get_all_tools())


@mcp_client_bp.route('/api/mcp/builtin-services', methods=['GET'])
def list_builtin_services():
    """列出 bin/mcp/manifest.json 中注册的所有内置服务及运行状态"""
    try:
        from common.builtin_mcp_manager import get_status
        statuses = get_status()
        services = list(statuses.values())
        running_count = sum(1 for s in services if s.get('running'))
        return success_response({
            'services': services,
            'total': len(services),
            'running': running_count,
        })
    except Exception as e:
        return error_response(str(e), 500)


@mcp_client_bp.route('/api/skills', methods=['GET'])
def list_skills():
    """列出 bin/skills/ 下所有可用技能"""
    try:
        from common.skill_loader import list_skills as _list
        skills = _list()
        return success_response({
            'skills': skills,
            'total': len(skills),
        })
    except Exception as e:
        return error_response(str(e), 500)


@mcp_client_bp.route('/api/skills/<name>', methods=['GET'])
def get_skill_detail(name):
    """获取指定技能的完整 SKILL.md 内容"""
    try:
        from common.skill_loader import load_skill
        skill = load_skill(name)
        if skill is None:
            return error_response(f'技能不存在: {name}', 404)
        return success_response(skill)
    except Exception as e:
        return error_response(str(e), 500)
