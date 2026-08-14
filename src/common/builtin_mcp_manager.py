"""内置服务统一管理器。

扫描 bin/mcp/*/service.json，自动发现并管理所有内置服务。
每个服务自包含在自己的文件夹下，与 Skills 的 SKILL.md 自描述模式一致。

服务类型：
- subprocess：pip 安装的 MCP 服务器，子进程拉起 → 健康检查 → 注册到 MCPClientBus
- binary：预编译二进制（如 OfficeCLI），由 tools_*.py 直接调用，此处仅做状态探测

新增一个内置服务只需在 bin/mcp/ 下创建文件夹 + service.json，无需写新的 runner。

目录约定：
  ~/.personllmwiki/mcp/<name>/           每个服务一个文件夹（自包含）
  ~/.personllmwiki/mcp/<name>/service.json   服务声明
  ~/.personllmwiki/mcp/<name>/launcher.py    启动脚本（subprocess 类型）
  ~/.personllmwiki/mcp/<name>/models/        模型等运行时数据（ensure_dirs 声明）
  ~/.personllmwiki/mcp/<name>/cache/         缓存
  ~/.personllmwiki/skills/<name>/SKILL.md    Skill 工作流指令
"""
import os
import sys
import json
import time
import shutil
import secrets
import atexit
import threading
import subprocess

# MCP_DIR（~/.personllmwiki/mcp/，首次启动时从 seed/ 播种）
def _get_bin_mcp_dir():
    """获取 MCP 服务目录，统一从 Config.MCP_DIR 读取。"""
    try:
        from config import Config
        return Config.MCP_DIR
    except Exception:
        pass
    _SRC_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(_SRC_ROOT, 'bin', 'mcp')

# 运行时状态
_procs = {}          # name -> subprocess.Popen
_tokens = {}         # name -> 生成的 auth token
_statuses = {}       # name -> {available, running, tool_count, error}
_lock = threading.Lock()


def _is_windows():
    return sys.platform == 'win32'


# ─── service.json 发现 ─────────────────────────────────────────

def _discover_services():
    """扫描 bin/mcp/*/service.json，返回所有服务声明的列表。

    每个文件夹自包含：有 service.json 就是一个服务，没有就跳过。
    删除文件夹 = 移除服务，零配置。
    """
    bin_mcp_dir = _get_bin_mcp_dir()
    services = []
    if not os.path.isdir(bin_mcp_dir):
        return services

    for entry in sorted(os.listdir(bin_mcp_dir)):
        svc_path = os.path.join(bin_mcp_dir, entry, 'service.json')
        if not os.path.isfile(svc_path):
            continue
        try:
            with open(svc_path, 'r', encoding='utf-8') as f:
                svc = json.load(f)
            # service.json 中的 name 应与文件夹名一致，不一致时以文件夹名为准
            svc['name'] = entry
            svc['_bin_dir'] = os.path.join(bin_mcp_dir, entry)
            services.append(svc)
        except (json.JSONDecodeError, IOError):
            continue

    return services


def _resolve_template(value, ctx):
    """替换模板变量：{bin_dir}, {name}。"""
    if not isinstance(value, str):
        return value
    return value.replace('{bin_dir}', ctx.get('bin_dir', '')).replace('{name}', ctx.get('name', ''))


def _resolve_env(env_template, ctx):
    """解析整个 env dict 的模板变量。"""
    return {k: _resolve_template(v, ctx) for k, v in env_template.items()}


# ─── subprocess 服务管理 ───────────────────────────────────────

def _health_check(host, port, health_path, token, timeout):
    """轮询健康检查，等待服务就绪。

    策略：先尝试 HTTP health 端点（200=就绪），失败则退回 TCP 端口探测。

    Returns: (ok: bool, last_error: str)
    """
    import socket
    deadline = time.time() + timeout
    health_url = f'http://{host}:{port}{health_path}'
    headers = {'Authorization': f'Bearer {token}'} if token else {}
    last_http_err = ''
    last_tcp_err = ''

    while time.time() < deadline:
        # 策略 1：HTTP health 端点
        try:
            import requests
            resp = requests.get(health_url, headers=headers, timeout=2)
            if resp.status_code == 200:
                return True, ''
            last_http_err = f'HTTP {resp.status_code}'
        except Exception as e:
            last_http_err = f'{type(e).__name__}: {e}'[:120]
        # 策略 2：TCP 端口探测（如 FastMCP 无 /health 端点）
        try:
            sock = socket.create_connection((host, port), timeout=1)
            sock.close()
            return True, ''
        except Exception as e:
            last_tcp_err = f'{type(e).__name__}: {e}'[:120]
        time.sleep(0.5)
    return False, f'TCP: {last_tcp_err}' if last_tcp_err else f'HTTP: {last_http_err}'


def _start_subprocess_service(svc):
    """启动一个 subprocess 类型的内置服务。

    Returns: {available, running, tool_count, error}
    """
    name = svc['name']
    command = svc['command']
    host = svc.get('host', '127.0.0.1')
    port = svc.get('port', 8000)
    path = svc.get('path', '/mcp')
    health_path = svc.get('health_path', '/health')
    auth_token_env = svc.get('auth_token_env', '')
    startup_timeout = svc.get('startup_timeout', 30)

    # 解析命令：打包模式下使用 sys.executable（PyInstaller EXE 内嵌 Python 解释器）
    if getattr(sys, 'frozen', False):
        cmd = sys.executable
    else:
        cmd = command + ('.exe' if _is_windows() and not command.endswith('.exe') else '')
        if shutil.which(cmd) is None:
            return {'available': False, 'running': False, 'error': f'{command} 未安装'}

    bin_dir = svc['_bin_dir']

    # 创建声明的子目录
    for sub in svc.get('ensure_dirs', []):
        os.makedirs(os.path.join(bin_dir, sub), exist_ok=True)

    # 生成随机 token
    token = secrets.token_urlsafe(32)
    _tokens[name] = token

    # 构建环境变量（模板替换）
    ctx = {'bin_dir': bin_dir, 'name': name}
    env = os.environ.copy()
    env.update(_resolve_env(svc.get('env', {}), ctx))
    if auth_token_env:
        env[auth_token_env] = token

    # 构建启动命令
    raw_args = svc.get('args', [])
    resolved_args = [_resolve_template(a, ctx) for a in raw_args]
    if getattr(sys, 'frozen', False) and resolved_args:
        # 打包模式：通过 --mcp-launcher 标志让 EXE 只运行脚本
        resolved_args = [f'--mcp-launcher={resolved_args[0]}']
    full_cmd = [cmd] + resolved_args

    # 启动子进程（stderr 重定向到日志文件用于调试）
    creationflags = 0x08000000 if _is_windows() else 0  # CREATE_NO_WINDOW
    stderr_log = os.path.join(bin_dir, 'stderr.log')
    try:
        err_fh = open(stderr_log, 'w', encoding='utf-8')
        proc = subprocess.Popen(
            full_cmd,
            env=env,
            stdout=err_fh,
            stderr=err_fh,
            creationflags=creationflags,
        )
    except Exception as e:
        return {'available': False, 'running': False, 'error': f'启动失败: {e}'}

    with _lock:
        _procs[name] = proc

    # 健康检查
    health_ok, health_err = _health_check(host, port, health_path, token, startup_timeout)
    if not health_ok:
        # 检查进程是否已提前退出
        exit_info = ''
        if proc.poll() is not None:
            exit_code = proc.returncode
            exit_info = f'进程已退出(code={exit_code})，'
        # 读取 stderr 日志辅助诊断
        err_detail = ''
        try:
            err_fh.flush()
            with open(stderr_log, 'r', encoding='utf-8') as f:
                lines = f.readlines()[-10:]
                err_detail = ''.join(lines).strip()[:500]
        except Exception:
            pass
        _stop_service(name)
        err_msg = f'{exit_info}连接失败({health_err})'
        if err_detail:
            err_msg += f': {err_detail}'
        return {'available': False, 'running': False, 'error': err_msg}

    # 注册到 MCPClientBus
    mcp_url = f'http://{host}:{port}{path}'
    try:
        from common.mcp_client import get_bus
        bus = get_bus()
        status = bus.add_server(
            name, mcp_url,
            token=token,
            description=svc.get('description', name),
            persist=False,
        )
        return {
            'available': True, 'running': True,
            'tool_count': status.get('tool_count', 0),
        }
    except Exception as e:
        _stop_service(name)
        return {'available': False, 'running': False, 'error': f'注册失败: {e}'}


def _check_binary_service(svc):
    """检查 binary 类型的服务（如 OfficeCLI）是否可用。

    Returns: {available, running, error, tool_count}
    """
    name = svc['name']
    bin_dir = svc['_bin_dir']
    tool_count = svc.get('tool_count', 0)

    if not os.path.isdir(bin_dir):
        return {'available': False, 'running': False, 'error': f'目录不存在: bin/mcp/{name}/', 'tool_count': tool_count}

    # 检查目录下是否有任何二进制文件
    try:
        files = os.listdir(bin_dir)
        binaries = [f for f in files if not f.startswith('.') and f != 'service.json']
        if not binaries:
            return {'available': False, 'running': False, 'error': '目录为空', 'tool_count': tool_count}
        return {'available': True, 'running': True, 'files': binaries, 'tool_count': tool_count}
    except Exception as e:
        return {'available': False, 'running': False, 'error': str(e), 'tool_count': tool_count}


# ─── embedded 服务 ────────────────────────────────────────

def _check_embedded_service(svc):
    """检查 embedded 类型的服务（如 ZSSNote 自身 MCP Server）。

    嵌入在当前进程内，无需独立启动，始终可用。
    Returns: {available, running, tool_count}
    """
    return {'available': True, 'running': True}


# ─── 公共 API ──────────────────────────────────────────────────

def start_service(svc):
    """启动单个服务并记录状态。"""
    name = svc['name']
    svc_type = svc.get('type', 'subprocess')

    try:
        if svc_type == 'subprocess':
            result = _start_subprocess_service(svc)
        elif svc_type == 'binary':
            result = _check_binary_service(svc)
        elif svc_type == 'embedded':
            result = _check_embedded_service(svc)
        else:
            result = {'available': False, 'running': False, 'error': f'未知类型: {svc_type}'}
    except Exception as e:
        result = {'available': False, 'running': False, 'error': str(e)}

    result['name'] = name
    result['type'] = svc_type
    result['source'] = svc.get('source', 'builtin')
    result['location'] = svc.get('location', 'local')
    result['description'] = svc.get('description', '')
    with _lock:
        _statuses[name] = result
    return result


def _stop_service(name):
    """停止单个服务。"""
    with _lock:
        proc = _procs.pop(name, None)
        _tokens.pop(name, None)

    if proc and proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    # 从 MCPClientBus 移除
    try:
        from common.mcp_client import get_bus, _bus_lock
        bus = get_bus()
        with _bus_lock:
            bus._remote_clients.pop(name, None)
    except Exception:
        pass


def stop_all():
    """停止所有正在运行的服务。"""
    with _lock:
        names = list(_procs.keys())
    for name in names:
        _stop_service(name)


def get_status():
    """获取所有服务的状态。"""
    with _lock:
        return dict(_statuses)


def get_builtin_names():
    """返回所有内置服务名称的集合（供统一 API 区分 builtin vs custom）。"""
    with _lock:
        return set(_statuses.keys())


def is_running(name):
    """检查指定服务是否在运行。"""
    with _lock:
        proc = _procs.get(name)
    return proc is not None and proc.poll() is None


def init_all_async():
    """异步启动所有内置服务（非阻塞，后台线程执行）。

    扫描 bin/mcp/*/service.json 自动发现服务，逐个启动。
    主应用启动时不等待服务就绪，避免拖慢启动。
    """
    def _worker():
        services = _discover_services()
        for svc in services:
            try:
                result = start_service(svc)
                name = svc['name']
                if result.get('running'):
                    tc = result.get('tool_count', '')
                    extra = f'，工具数: {tc}' if tc else ''
                    print(f'[Builtin] {name} 已就绪{extra}')
                else:
                    print(f'[Builtin] {name} 不可用: {result.get("error", "未知")}')
            except Exception as e:
                print(f'[Builtin] {svc.get("name", "?")} 启动异常: {e}')

    t = threading.Thread(target=_worker, daemon=True, name='builtin-services')
    t.start()


def reinit():
    """重新初始化所有内置服务（当资源路径变更时调用）。

    停止所有运行中的服务，清除状态，重新扫描并启动。
    """
    stop_all()
    with _lock:
        _statuses.clear()
        _procs.clear()
        _tokens.clear()
    init_all_async()


# 注册退出钩子
atexit.register(stop_all)
