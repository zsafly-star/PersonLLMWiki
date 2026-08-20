"""DeepSeek Harness (DSH) 桥接层。

PersonLLMWiki 与 DSH 的唯一交互入口，收敛 DSH 的进程管理与 CLI 语法变化。

职责：
- 发现：DSH_URL 健康检查；已在跑 → 复用；未在跑 → 按 DSH_CMD 拉起
- 版本门禁：dsh --version ≥ 最低版本才启用「智能体」Tab
- headless：控制台定时任务调用封装（dsh --profile headless "prompt"）

铁律：
- 只管理进程，不碰 DSH 文件；$DSH_HOME 与 ~/.personllmwiki 数据永不相交
- 优雅降级：DSH 缺失/版本过低 → 状态返回 not_installed / version_low，其余功能照常

状态机：
    not_installed  未配置 DSH_CMD 或命令不存在
    version_low    已安装但版本低于门禁（>=0.1.0-rc.6）
    not_running    已安装但 DSH web 未在运行（3080 无响应）
    running        已安装且 DSH web 健康
"""

import json
import os
import shutil
import subprocess
import urllib.request
import urllib.error

# 最低版本门禁
MIN_DSH_VERSION = '0.1.0-rc.6'

# 默认 DSH web 地址
DEFAULT_DSH_URL = 'http://127.0.0.1:3080'

# 健康检查超时（秒）
HEALTH_TIMEOUT = 2.0

# 状态枚举
STATUS_NOT_INSTALLED = 'not_installed'
STATUS_VERSION_LOW = 'version_low'
STATUS_NOT_RUNNING = 'not_running'
STATUS_RUNNING = 'running'

# 由本进程拉起的 DSH 句柄（用于 stop 时回收）
_managed_proc = None

# 版本探测结果缓存（避免每次状态查询都跑子进程）
_VERSION_CACHE_TTL = 30.0
_version_cache = {'ts': 0.0, 'value': None}


def _valid_http_url(url):
    """仅允许 http/https，防止 file:// 等 scheme 被当作健康检查目标或注入 iframe。"""
    import re
    return bool(re.match(r'^https?://', (url or '').strip()))


# ─── 配置读写 ──────────────────────────────────────────────

def _config_path():
    """DSH 配置存储路径：~/.personllmwiki/instance/dsh_config.json"""
    from config import Config
    return os.path.join(Config.INSTANCE_PATH, 'dsh_config.json')


def _read_config():
    """读取 DSH 配置，不存在返回空 dict。"""
    path = _config_path()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, IOError):
        return {}


def _write_config(config):
    """原子写入 DSH 配置。"""
    import tempfile
    path = _config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix='.dsh_config-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def get_config():
    """获取 DSH 配置（带默认值）。"""
    cfg = _read_config()
    return {
        'dsh_cmd': cfg.get('dsh_cmd', ''),
        'dsh_url': cfg.get('dsh_url', DEFAULT_DSH_URL),
        'auto_start': bool(cfg.get('auto_start', False)),
    }


def set_config(dsh_cmd=None, dsh_url=None, auto_start=None):
    """更新 DSH 配置（仅更新传入的非 None 字段）。返回完整配置。"""
    cfg = _read_config()
    if dsh_cmd is not None:
        cfg['dsh_cmd'] = dsh_cmd.strip()
    if dsh_url is not None:
        url = (dsh_url or '').strip() or DEFAULT_DSH_URL
        if not _valid_http_url(url):
            raise ValueError('DSH URL 仅支持 http/https')
        cfg['dsh_url'] = url
    if auto_start is not None:
        cfg['auto_start'] = bool(auto_start)
    _write_config(cfg)
    # 命令变更后，版本缓存失效
    _version_cache['ts'] = 0.0
    _version_cache['value'] = None
    return get_config()


# ─── 命令探测 ──────────────────────────────────────────────

def _resolve_dsh_cmd():
    """解析 DSH 命令路径：优先配置，回退 PATH。

    Returns:
        str | None: 可执行的 dsh 命令路径；None 表示未安装。
    """
    cfg = get_config()
    configured = cfg.get('dsh_cmd', '')
    if configured and os.path.isfile(configured):
        return configured
    if configured:
        # 配置的是目录（如安装目录），尝试定位 dsh 可执行文件
        for candidate in ('dsh.cmd', 'dsh.exe', 'dsh'):
            p = os.path.join(configured, candidate)
            if os.path.isfile(p):
                return p
    # 回退 PATH
    found = shutil.which('dsh')
    return found


def is_installed():
    """DSH 是否已安装（命令可解析）。"""
    return _resolve_dsh_cmd() is not None


# ─── 版本 ──────────────────────────────────────────────────

def get_version():
    """执行 dsh --version 并解析版本号。

    Returns:
        str | None: 版本号字符串；None 表示无法获取。
    """
    import time
    if time.time() - _version_cache['ts'] < _VERSION_CACHE_TTL:
        return _version_cache['value']

    cmd = _resolve_dsh_cmd()
    if not cmd:
        return None
    try:
        out = subprocess.run(
            [cmd, '--version'],
            capture_output=True, text=True, timeout=10,
            cwd=os.path.dirname(cmd),
        )
        text = (out.stdout or '').strip() or (out.stderr or '').strip()
        version = _parse_version(text)
    except (subprocess.SubprocessError, OSError):
        version = None

    _version_cache['ts'] = time.time()
    _version_cache['value'] = version
    return version


def _parse_version(text):
    """从 dsh --version 输出中提取版本号（如 "0.1.0-rc.6"）。"""
    import re
    if not text:
        return None
    # 匹配 x.y.z[-rc.N] 或 @deepseek-ai/dsh 后的版本
    m = re.search(r'(\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)', text)
    return m.group(1) if m else (text.strip() or None)


def _version_tuple(version):
    """把版本号拆为可比较元组，pre-release 视为低于正式版。

    例如 "0.1.0-rc.6" -> (0, 1, 0, 'rc', 6)
    """
    import re
    m = re.match(r'^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z]+)\.?(\d+))?$', version or '')
    if not m:
        return None
    major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3))
    pre_label = m.group(4)
    pre_num = int(m.group(5)) if m.group(5) else 0
    # 正式版 > 任意 pre-release：正式版第 4 位为 1，pre-release 为 0
    return (major, minor, patch, 1 if pre_label is None else 0, pre_label or '', pre_num)


def version_ok(version):
    """版本是否满足门禁（>= MIN_DSH_VERSION）。

    Args:
        version: str | None

    Returns:
        bool: None（未知版本）或无法解析时按不满足处理（fail-closed）。
    """
    if not version:
        return False
    vt = _version_tuple(version)
    mt = _version_tuple(MIN_DSH_VERSION)
    if vt is None or mt is None:
        # 无法解析 → 门禁不通过（fail-closed），避免放行未知版本
        return False
    return vt >= mt


# ─── 健康检查 ──────────────────────────────────────────────

def check_health(url=None, timeout=HEALTH_TIMEOUT):
    """检查 DSH web 是否健康（HTTP 200）。

    Returns:
        bool: True 表示 DSH web 正在运行。
    """
    target = (url or get_config().get('dsh_url') or DEFAULT_DSH_URL).rstrip('/')
    if not _valid_http_url(target):
        return False
    try:
        req = urllib.request.Request(target, headers={'User-Agent': 'PersonLLMWiki-DSHBridge'})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


# ─── 状态 ──────────────────────────────────────────────────

def get_status():
    """获取 DSH 完整状态，供前端「智能体」Tab 与设置页使用。

    Returns:
        dict:
            status:  not_installed / version_low / not_running / running
            installed / version / version_ok / running / url / cmd / min_version
    """
    cfg = get_config()
    cmd = _resolve_dsh_cmd()
    installed = cmd is not None
    version = get_version() if installed else None
    ok = version_ok(version)

    if not installed:
        running = False
        status = STATUS_NOT_INSTALLED
    elif not ok:
        running = False
        status = STATUS_VERSION_LOW
    else:
        running = check_health(cfg.get('dsh_url'))
        status = STATUS_RUNNING if running else STATUS_NOT_RUNNING

    return {
        'status': status,
        'installed': installed,
        'version': version,
        'version_ok': ok,
        'running': running,
        'url': cfg.get('dsh_url') or DEFAULT_DSH_URL,
        'cmd': cmd or '',
        'auto_start': cfg.get('auto_start', False),
        'min_version': MIN_DSH_VERSION,
    }


# ─── 启停 ──────────────────────────────────────────────────

def start(timeout=30.0):
    """拉起 DSH web（若未在跑）。只管理进程，不碰 DSH 文件。

    Returns:
        dict: {started, status, error}
    """
    status = get_status()
    if status['status'] == STATUS_NOT_INSTALLED:
        return {'started': False, 'status': STATUS_NOT_INSTALLED, 'error': 'DSH 未安装'}
    if status['status'] == STATUS_VERSION_LOW:
        return {'started': False, 'status': STATUS_VERSION_LOW,
                'error': f'DSH 版本过低（{status["version"]} < {MIN_DSH_VERSION}）'}
    if status['status'] == STATUS_RUNNING:
        return {'started': True, 'status': STATUS_RUNNING, 'error': ''}

    cmd = _resolve_dsh_cmd()
    global _managed_proc
    # 默认以 `dsh web` 启动（监听 3080）；DSH CLI 语法变化收敛于此
    try:
        _managed_proc = subprocess.Popen(
            [cmd, 'web'],
            cwd=os.path.dirname(cmd),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except (OSError, subprocess.SubprocessError) as e:
        _managed_proc = None
        return {'started': False, 'status': STATUS_NOT_RUNNING, 'error': f'启动 DSH 失败: {e}'}

    # 等待健康检查
    import time
    deadline = time.time() + timeout
    while time.time() < deadline:
        if check_health():
            return {'started': True, 'status': STATUS_RUNNING, 'error': ''}
        time.sleep(0.5)

    return {'started': False, 'status': STATUS_NOT_RUNNING,
            'error': 'DSH 已拉起但未在超时内就绪，请检查 3080 端口'}


def stop():
    """停止由本进程拉起的 DSH web（best-effort）。

    若 DSH 由用户自启（非本进程拉起），不强制 kill，仅做健康检查反馈。
    """
    global _managed_proc
    proc, _managed_proc = _managed_proc, None
    if proc is not None and proc.poll() is None:
        try:
            if os.name == 'nt':
                subprocess.run(
                    ['taskkill', '/PID', str(proc.pid), '/T', '/F'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=10,
                )
            else:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        except (OSError, subprocess.SubprocessError):
            pass

    return {'stopped': not check_health()}


# ─── headless 调用 ─────────────────────────────────────────

def run_headless(prompt, timeout=600):
    """控制台定时任务 headless 调用封装。

    Args:
        prompt: 任务提示词
        timeout: 超时秒数

    Returns:
        dict: {success, output, error, exit_code}
    """
    status = get_status()
    if status['status'] in (STATUS_NOT_INSTALLED, STATUS_VERSION_LOW):
        return {'success': False, 'output': '', 'error': f'DSH 不可用（{status["status"]}）', 'exit_code': None}

    cmd = _resolve_dsh_cmd()
    try:
        proc = subprocess.run(
            [cmd, '--profile', 'headless', prompt],
            capture_output=True, text=True, timeout=timeout,
            cwd=os.path.dirname(cmd),
        )
        return {
            'success': proc.returncode == 0,
            'output': (proc.stdout or '') + (proc.stderr or ''),
            'error': '' if proc.returncode == 0 else (proc.stderr or proc.stdout or '执行失败'),
            'exit_code': proc.returncode,
        }
    except subprocess.TimeoutExpired:
        return {'success': False, 'output': '', 'error': f'执行超时（>{timeout}s）', 'exit_code': None}
    except (OSError, subprocess.SubprocessError) as e:
        return {'success': False, 'output': '', 'error': str(e), 'exit_code': None}


# ─── 更新检查 ──────────────────────────────────────────────

def check_update():
    """检查 npm registry 上 @deepseek-ai/dsh 的最新版本。

    Returns:
        dict: {installed, latest, has_update, error}
        installed / latest 可能为 None（无法获取）。
    """
    installed = get_version()

    try:
        req = urllib.request.Request(
            'https://registry.npmjs.org/@deepseek-ai/dsh/latest',
            headers={'User-Agent': 'PersonLLMWiki-DSHBridge'}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        latest = data.get('version') if isinstance(data, dict) else None
    except (urllib.error.URLError, OSError, ValueError) as e:
        return {'installed': installed, 'latest': None, 'has_update': False,
                'error': f'获取最新版本失败: {e}'}

    iv = _version_tuple(installed) if installed else None
    lv = _version_tuple(latest) if latest else None
    has_update = bool(iv and lv and lv > iv)

    return {'installed': installed, 'latest': latest, 'has_update': has_update, 'error': ''}
