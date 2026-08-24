"""DeepSeek Harness (DSH) 桥接层。

PersonLLMWiki 与 DSH 的唯一交互入口，收敛 DSH 的进程管理与 CLI 语法变化。

职责：
- 发现：DSH_URL 健康检查；已在跑 → 复用；未在跑 → 按 DSH_CMD 拉起
- 版本门禁：dsh --version ≥ 最低版本才启用 DSH 模式
- headless：控制台定时任务调用封装（dsh --profile headless "prompt"）

铁律：
- 只管理进程，不碰 DSH 文件；$DSH_HOME 与 ~/.personllmwiki 数据永不相交
- 优雅降级：DSH 缺失/版本过低 → 状态返回 not_installed / version_low，其余功能照常

状态机：
    not_installed  未配置 DSH_CMD 或命令不存在
    version_low    已安装但版本低于门禁（>=0.1.0-rc.6）
    starting       已拉起、进程存活但 web 未就绪（首次初始化可能耗时较长）
    not_running    已安装但 DSH web 未在运行（3080 无响应）
    running        已安装且 DSH web 健康
"""

import http.client
import json
import os
import shutil
import subprocess
import threading
import urllib.request
import urllib.error

# 最低版本门禁
MIN_DSH_VERSION = '0.1.0-rc.6'

# 默认 DSH web 地址
DEFAULT_DSH_URL = 'http://127.0.0.1:3080'

# 健康检查超时（秒）
HEALTH_TIMEOUT = 2.0

# 拉起后等待就绪的最大时长（秒）——DSH 首次启动需初始化 web profile（下载依赖），可能较慢
START_TIMEOUT = 300.0

# 状态枚举
STATUS_NOT_INSTALLED = 'not_installed'
STATUS_VERSION_LOW = 'version_low'
STATUS_NOT_RUNNING = 'not_running'
STATUS_STARTING = 'starting'
STATUS_RUNNING = 'running'

# 由本进程拉起的 DSH 句柄（用于 stop 时回收）
_managed_proc = None

# 版本探测结果缓存（避免每次状态查询都跑子进程）
_VERSION_CACHE_TTL = 30.0
_version_cache = {'ts': 0.0, 'value': None}

# 并发保护：start/stop/status 可能被 auto_start 后台线程与前端请求并发调用
_proc_lock = threading.Lock()
_version_lock = threading.Lock()


def _valid_http_url(url):
    """仅允许 http/https，防止 file:// 等 scheme 被当作健康检查目标或注入 iframe。"""
    import re
    return bool(re.match(r'^https?://', (url or '').strip()))


def _is_loopback_url(url):
    """校验 URL host 为回环地址（127.x / localhost / ::1），防止 SSRF。"""
    import ipaddress
    from urllib.parse import urlparse
    try:
        parsed = urlparse((url or '').strip())
    except ValueError:
        return False
    if parsed.scheme not in ('http', 'https'):
        return False
    host = (parsed.hostname or '').lower()
    if host == 'localhost':
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def is_local_origin(origin):
    """校验请求 Origin 是否为本机（回环/localhost），用于 DSH 写操作防 CSRF/Drive-by。"""
    if not origin:
        return True
    import ipaddress
    from urllib.parse import urlparse
    try:
        host = (urlparse(origin).hostname or '').lower()
    except ValueError:
        return False
    if host == 'localhost':
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


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
        'dsh_mirror_url': cfg.get('dsh_mirror_url', ''),
        'dsh_registry': cfg.get('dsh_registry', ''),
    }


def set_config(dsh_cmd=None, dsh_url=None, auto_start=None, dsh_mirror_url=None, dsh_registry=None):
    """更新 DSH 配置（仅更新传入的非 None 字段）。返回完整配置。"""
    cfg = _read_config()
    if dsh_cmd is not None:
        if not isinstance(dsh_cmd, str):
            raise ValueError('DSH 命令必须是字符串')
        cmd = dsh_cmd.strip()
        # 仅允许文件名以 dsh 命名的可执行文件；目录路径由 _resolve_dsh_cmd 收敛到候选文件名
        if cmd and os.path.isfile(cmd) and os.path.basename(cmd).lower() not in ('dsh', 'dsh.exe', 'dsh.cmd'):
            raise ValueError('DSH 命令文件必须是 dsh / dsh.exe / dsh.cmd')
        cfg['dsh_cmd'] = cmd
    if dsh_url is not None:
        if not isinstance(dsh_url, str):
            raise ValueError('DSH 地址必须是字符串')
        url = (dsh_url or '').strip() or DEFAULT_DSH_URL
        if not _valid_http_url(url) or not _is_loopback_url(url):
            raise ValueError('DSH URL 仅支持 http/https 且 host 必须为回环地址（127.0.0.1/localhost）')
        cfg['dsh_url'] = url
    if auto_start is not None:
        cfg['auto_start'] = bool(auto_start)
    if dsh_mirror_url is not None:
        if not isinstance(dsh_mirror_url, str):
            raise ValueError('DSH 下载源必须是字符串')
        mirror = dsh_mirror_url.strip()
        if mirror and not _valid_http_url(mirror):
            raise ValueError('DSH 下载源仅支持 http/https')
        cfg['dsh_mirror_url'] = mirror
    if dsh_registry is not None:
        if not isinstance(dsh_registry, str):
            raise ValueError('DSH npm registry 必须是字符串')
        registry = dsh_registry.strip()
        if registry and not _valid_http_url(registry):
            raise ValueError('DSH npm registry 仅支持 http/https')
        cfg['dsh_registry'] = registry
    _write_config(cfg)
    # 命令变更后，版本缓存失效
    with _version_lock:
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
        # npm 安装：可执行文件位于 node_modules/.bin/ 下（如 D:\DeepSeek Harness）
        for candidate in ('dsh.cmd', 'dsh.exe', 'dsh'):
            p = os.path.join(configured, 'node_modules', '.bin', candidate)
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
    with _version_lock:
        if time.time() - _version_cache['ts'] < _VERSION_CACHE_TTL:
            return _version_cache['value']

    cmd = _resolve_dsh_cmd()
    if not cmd:
        return None
    try:
        out = subprocess.run(
            [cmd, '--version'],
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=10,
            cwd=os.path.dirname(cmd),
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        text = (out.stdout or '').strip() or (out.stderr or '').strip()
        version = _parse_version(text)
    except (subprocess.SubprocessError, OSError):
        version = None

    # 仅缓存成功的探测结果；失败(None)不落缓存，避免放大"版本过低"误判
    with _version_lock:
        _version_cache['ts'] = time.time() if version else 0.0
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
    if not _valid_http_url(target) or not _is_loopback_url(target):
        return False
    try:
        # 禁用重定向跟随，防止回环地址被 302 引导至内网/云元数据（盲 SSRF 加固）
        class _NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None

        opener = urllib.request.build_opener(_NoRedirect)
        req = urllib.request.Request(target, headers={'User-Agent': 'PersonLLMWiki-DSHBridge'})
        with opener.open(req, timeout=timeout) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as e:
        # 3xx 重定向（已被禁跟随）仍说明服务存活，避免把根路径 302 误判为未运行
        return 300 <= e.code < 400
    except (urllib.error.URLError, OSError, ValueError):
        return False


# ─── 状态 ──────────────────────────────────────────────────

def get_status():
    """获取 DSH 完整状态，供桌面壳 DSH 模式与设置页使用。

    Returns:
        dict:
            status:  not_installed / version_low / starting / not_running / running
            installed / version / version_ok / running / url / cmd / min_version
    """
    global _managed_proc
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
        if running:
            status = STATUS_RUNNING
        elif _managed_proc is not None:
            if _managed_proc.poll() is None:
                # 本进程拉起的 DSH 仍在启动（首次初始化 web profile 可能较慢）
                status = STATUS_STARTING
            else:
                # 进程已退出：清理句柄，避免误判为"仍在启动"
                with _proc_lock:
                    if _managed_proc is not None and _managed_proc.poll() is not None:
                        _managed_proc = None
                status = STATUS_NOT_RUNNING
        else:
            status = STATUS_NOT_RUNNING

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

    非阻塞：拉起后立即返回 status=starting；后台线程等待健康检查
    （最长时间 START_TIMEOUT，DSH 首次启动需初始化 web profile 可能较慢），
    前端通过轮询 get_status() 观察 starting → running / not_running。

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
    if status['status'] == STATUS_STARTING:
        return {'started': True, 'status': STATUS_STARTING, 'error': ''}

    cmd = _resolve_dsh_cmd()
    global _managed_proc
    # 默认以 `dsh web` 启动（监听 3080）；DSH CLI 语法变化收敛于此。
    # 锁内双重检查，防止 auto_start 后台线程与前端点击并发重复拉起。
    with _proc_lock:
        if check_health():
            return {'started': True, 'status': STATUS_RUNNING, 'error': ''}
        if _managed_proc is not None and _managed_proc.poll() is None:
            return {'started': True, 'status': STATUS_STARTING, 'error': ''}
        try:
            new_proc = subprocess.Popen(
                [cmd, 'web', '--no-open'],
                cwd=os.path.dirname(cmd),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            )
        except (OSError, subprocess.SubprocessError) as e:
            return {'started': False, 'status': STATUS_NOT_RUNNING, 'error': f'启动 DSH 失败: {e}'}
        _managed_proc = new_proc

    # 后台等待健康检查（不阻塞调用方；首次初始化可能耗时较长）。
    # 超时或进程退出：清理句柄，状态经 get_status 回落到 not_running。
    def _wait_ready(proc):
        import time
        deadline = time.time() + START_TIMEOUT
        while time.time() < deadline:
            if check_health():
                return
            if proc.poll() is not None:
                break
            time.sleep(1)
        with _proc_lock:
            if _managed_proc is proc:
                _managed_proc = None

    threading.Thread(target=_wait_ready, args=(new_proc,), daemon=True).start()

    return {'started': True, 'status': STATUS_STARTING, 'error': ''}


def stop():
    """停止由本进程拉起的 DSH web（best-effort）。

    若 DSH 由用户自启（非本进程拉起），不强制 kill，仅做健康检查反馈。
    """
    global _managed_proc
    with _proc_lock:
        proc, _managed_proc = _managed_proc, None
    if proc is not None and proc.poll() is None:
        try:
            if os.name == 'nt':
                subprocess.run(
                    ['taskkill', '/PID', str(proc.pid), '/T', '/F'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=10,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                )
            else:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        pass
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
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout,
            cwd=os.path.dirname(cmd),
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
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
    except (urllib.error.URLError, OSError, ValueError, http.client.HTTPException) as e:
        return {'installed': installed, 'latest': None, 'has_update': False,
                'error': f'获取最新版本失败: {e}'}

    iv = _version_tuple(installed) if installed else None
    lv = _version_tuple(latest) if latest else None
    has_update = bool(iv and lv and lv > iv)

    return {'installed': installed, 'latest': latest, 'has_update': has_update, 'error': ''}


# ─── 运行时安装 / 更新 ────────────────────────────────────

# DSH 运行时安装目录（按用户隔离，升级=换 app、留 home）
DSH_HOME_BASE = os.path.join(
    os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'), 'DeepSeekHarness')

# 默认 npm registry（增量更新用）
DSH_DEFAULT_REGISTRY = 'https://registry.npmjs.org'


def get_dsh_home():
    r"""DSH 运行时安装目录（%LOCALAPPDATA%\DeepSeekHarness）。"""
    return DSH_HOME_BASE


def get_dsh_data_home():
    """DSH 数据目录（profiles/skills/sessions 等）：优先 $DSH_HOME 环境变量，默认 ~/.dsh。"""
    env = os.environ.get('DSH_HOME', '').strip()
    if env:
        return env
    return os.path.join(os.path.expanduser('~'), '.dsh')


def _get_mirror_url():
    """下载源：环境变量 DSH_MIRROR_URL 优先，其次配置 dsh_mirror_url。空串表示未配置。"""
    env = (os.environ.get('DSH_MIRROR_URL') or '').strip()
    if env:
        return env
    return (_read_config().get('dsh_mirror_url') or '').strip()


def _get_registry():
    """npm registry：环境变量 DSH_NPM_REGISTRY 优先，其次配置，最后默认 npmjs。"""
    env = (os.environ.get('DSH_NPM_REGISTRY') or '').strip()
    if env:
        return env
    return (_read_config().get('dsh_registry') or '').strip() or DSH_DEFAULT_REGISTRY


def get_runtime_info():
    """运行时安装/更新元信息（设置页「重新安装 / 一键更新」展示与决策用）。"""
    return {
        'home': get_dsh_home(),
        'app_dir': os.path.join(get_dsh_home(), 'app'),
        'mirror_url': _get_mirror_url(),
        'registry': _get_registry(),
        'installed': is_installed(),
        'version': get_version(),
    }


def _install_guidance():
    """下载源未配置时的降级文本引导。"""
    return ('尚未配置 DSH 运行时下载源（DSH_MIRROR_URL / dsh_mirror_url）。'
            '请配置公司镜像 zip 或 npm registry 后重试，'
            '或使用「关联已有 DSH」填写已安装的 dsh.cmd / 安装目录。')


def _fetch_runtime_manifest(mirror):
    """从下载源读取 dsh-runtime-latest.json 清单（Nexus raw 兜底路径）。

    清单格式：{"version": "0.1.0-rc.6", "url": "...zip", "sha256": "..."}
    """
    url = mirror.rstrip('/') + '/dsh-runtime-latest.json'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'PersonLLMWiki-DSHBridge'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except (urllib.error.URLError, OSError, ValueError, http.client.HTTPException):
        return None
    if isinstance(data, dict) and data.get('url'):
        return {
            'version': data.get('version'),
            'url': data.get('url'),
            'sha256': data.get('sha256') or '',
        }
    return None


def get_runtime_latest():
    """获取运行时 zip 最新版本信息（下载地址 + SHA256）。

    zip 场景查公司镜像清单 dsh-runtime-latest.json；下载源为空时返回空 url（降级文本引导）。
    """
    mirror = _get_mirror_url()
    if not mirror:
        return {'version': None, 'url': '', 'sha256': '', 'error': ''}
    m = _fetch_runtime_manifest(mirror)
    if m:
        return {'version': m['version'], 'url': m['url'], 'sha256': m['sha256'], 'error': ''}
    return {'version': None, 'url': '', 'sha256': '',
            'error': '无法从下载源获取 dsh-runtime-latest.json 清单'}


def _sha256_file(path):
    """计算文件 SHA256（十六进制）。"""
    import hashlib
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def _download_file(url, dest):
    """下载文件到 dest（流式）。"""
    req = urllib.request.Request(url, headers={'User-Agent': 'PersonLLMWiki-DSHBridge'})
    with urllib.request.urlopen(req, timeout=300) as resp:
        with open(dest, 'wb') as f:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)


def _extract_runtime(zip_path, home, replace_app=True):
    r"""解压运行时 zip 到 home。

    - app\   ：replace_app=True 时整体替换（带备份回滚），否则只补缺
    - home\  ：永不覆盖，仅补缺（会话保留）
    - 其余根文件（如 version.txt）写入 home 根
    """
    import zipfile
    app_dir = os.path.join(home, 'app')
    home_dir = os.path.join(home, 'home')
    os.makedirs(home_dir, exist_ok=True)

    with zipfile.ZipFile(zip_path) as z:
        names = [n for n in z.namelist() if not n.endswith('/')]

        # 归一化顶层目录（zip 可能包了一层根目录）
        top_dirs = set()
        for n in names:
            parts = [p for p in n.split('/') if p]
            if parts:
                top_dirs.add(parts[0])
        wrapper = next(iter(top_dirs)) if len(top_dirs) == 1 else None

        def rel_parts(name):
            parts = [p for p in name.split('/') if p]
            if wrapper and parts and parts[0] == wrapper:
                parts = parts[1:]
            return parts

        # 替换 app 前先备份，失败可回滚
        backup = None
        if replace_app and os.path.isdir(app_dir):
            backup = app_dir + '_backup'
            if os.path.isdir(backup):
                shutil.rmtree(backup)
            shutil.move(app_dir, backup)

        try:
            for name in names:
                parts = rel_parts(name)
                if not parts:
                    continue
                top = parts[0].lower()
                if top == 'home':
                    dest = os.path.join(home_dir, *parts[1:])
                    if os.path.exists(dest):
                        continue  # home 永不覆盖
                elif top == 'app':
                    dest = os.path.join(app_dir, *parts[1:])
                else:
                    dest = os.path.join(home, *parts)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with z.open(name) as src, open(dest, 'wb') as dst:
                    shutil.copyfileobj(src, dst)
        except Exception:
            if backup and os.path.isdir(backup):
                if os.path.isdir(app_dir):
                    shutil.rmtree(app_dir)
                shutil.move(backup, app_dir)
            raise
        else:
            if backup and os.path.isdir(backup):
                shutil.rmtree(backup)


def _write_version_file(home, version):
    """写入 version.txt。"""
    try:
        with open(os.path.join(home, 'version.txt'), 'w', encoding='utf-8') as f:
            f.write(version or '')
    except OSError:
        pass


def _auto_link_app(home):
    """重装后自动关联 app 内 dsh 可执行文件到配置。"""
    app_dir = os.path.join(home, 'app')
    for candidate in ('dsh.cmd', 'dsh.exe', 'dsh'):
        p = os.path.join(app_dir, candidate)
        if os.path.isfile(p):
            set_config(dsh_cmd=p)
            return p
    for candidate in ('dsh.cmd', 'dsh.exe', 'dsh'):
        p = os.path.join(app_dir, 'node_modules', '.bin', candidate)
        if os.path.isfile(p):
            set_config(dsh_cmd=p)
            return p
    return None


def install_runtime():
    """重新安装：下载运行时 zip → 校验 SHA256 → 解压到 home（app 替换 + home 初建）→ 自动关联。

    不覆盖 home\（会话保留）；下载源未配置或清单缺失时返回文本引导。
    """
    latest = get_runtime_latest()
    url = latest.get('url')
    if not url:
        return {'success': False, 'error': _install_guidance()}

    sha256 = latest.get('sha256') or ''
    version = latest.get('version')
    home = get_dsh_home()
    os.makedirs(home, exist_ok=True)

    # 停止正在运行的 DSH，避免 app 文件句柄占用
    stop()

    import tempfile
    tmp = tempfile.mkdtemp(prefix='dsh_runtime_')
    zip_path = os.path.join(tmp, 'dsh-runtime.zip')
    try:
        _download_file(url, zip_path)
        if sha256:
            actual = _sha256_file(zip_path)
            if actual.lower() != sha256.lower():
                shutil.rmtree(tmp, ignore_errors=True)
                return {'success': False,
                        'error': 'SHA256 校验失败，安装已中止（期望 ' + sha256[:16] + '…）'}
        _extract_runtime(zip_path, home, replace_app=True)
    except Exception as e:
        shutil.rmtree(tmp, ignore_errors=True)
        return {'success': False, 'error': '安装失败: ' + str(e)}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    _write_version_file(home, version)
    linked = _auto_link_app(home)

    msg = 'DSH 运行时安装完成（' + (version or 'latest') + '）'
    if linked:
        msg += '，已自动关联'
    else:
        msg += '，但未找到 dsh 可执行文件，请手动关联'
    return {'success': True, 'message': msg, 'version': version, 'home': home, 'error': ''}


def _is_npm_app(app_dir):
    """app 目录是否声明了 @deepseek-ai/dsh 依赖（npm 增量更新适用）。"""
    pkg = os.path.join(app_dir, 'package.json')
    if not os.path.isfile(pkg):
        return False
    try:
        with open(pkg, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError):
        return False
    deps = data.get('dependencies') or {}
    return '@deepseek-ai/dsh' in deps or 'dsh' in deps


def _locate_node(app_dir):
    """定位便携/系统 node 可执行文件。"""
    for p in (os.path.join(app_dir, 'node', 'node.exe'),
              os.path.join(app_dir, 'node.exe'),
              os.path.join(get_dsh_home(), 'node', 'node.exe')):
        if os.path.isfile(p):
            return p
    return shutil.which('node')


def _npm_update(app_dir):
    """npm 增量更新：npm install @deepseek-ai/dsh@latest（cwd=app）。"""
    registry = _get_registry()
    node = _locate_node(app_dir)
    npm_cli = os.path.join(os.path.dirname(node), 'node_modules', 'npm', 'bin', 'npm-cli.js') if node else ''

    if node and os.path.isfile(npm_cli):
        cmd = [node, npm_cli, 'install', '@deepseek-ai/dsh@latest', '--registry', registry]
    else:
        npm = shutil.which('npm') or shutil.which('npm.cmd')
        if not npm:
            return {'success': False, 'method': 'npm',
                    'error': '未找到 npm，无法增量更新；请使用「重新安装」'}
        cmd = [npm, 'install', '@deepseek-ai/dsh@latest', '--registry', registry]

    stop()
    try:
        proc = subprocess.run(cmd, cwd=app_dir, capture_output=True, text=True,
                              encoding='utf-8', errors='replace', timeout=600,
                              creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except subprocess.TimeoutExpired:
        return {'success': False, 'method': 'npm', 'error': 'npm 安装超时（>600s）'}
    except (OSError, subprocess.SubprocessError) as e:
        return {'success': False, 'method': 'npm', 'error': 'npm 安装失败: ' + str(e)}

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or '').strip()[-500:]
        return {'success': False, 'method': 'npm', 'error': 'npm 安装失败: ' + detail}

    _sync_profile(app_dir)
    with _version_lock:
        _version_cache['ts'] = 0.0
        _version_cache['value'] = None
    return {'success': True, 'method': 'npm',
            'message': 'DSH 增量更新完成，请重启 DSH 生效', 'error': ''}


def _sync_profile(app_dir):
    """更新后做一次 profile 同步（best-effort，失败不致命）。"""
    cmd = _resolve_dsh_cmd()
    if not cmd:
        return
    try:
        subprocess.run([cmd, 'plugin', '--profile', 'web'],
                       capture_output=True, text=True, encoding='utf-8',
                       errors='replace', timeout=60, cwd=os.path.dirname(cmd),
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired):
        pass


def update_runtime():
    r"""一键更新：npm 增量优先；否则走 zip 换 app\ 留 home\。"""
    home = get_dsh_home()
    app_dir = os.path.join(home, 'app')

    if _is_npm_app(app_dir):
        return _npm_update(app_dir)

    # zip 路径
    latest = get_runtime_latest()
    url = latest.get('url')
    if not url:
        return {'success': False, 'method': 'zip', 'error': _install_guidance()}

    sha256 = latest.get('sha256') or ''
    version = latest.get('version')
    os.makedirs(home, exist_ok=True)
    stop()

    import tempfile
    tmp = tempfile.mkdtemp(prefix='dsh_update_')
    zip_path = os.path.join(tmp, 'dsh-runtime.zip')
    try:
        _download_file(url, zip_path)
        if sha256:
            actual = _sha256_file(zip_path)
            if actual.lower() != sha256.lower():
                shutil.rmtree(tmp, ignore_errors=True)
                return {'success': False, 'method': 'zip',
                        'error': 'SHA256 校验失败，更新已中止'}
        _extract_runtime(zip_path, home, replace_app=True)
    except Exception as e:
        shutil.rmtree(tmp, ignore_errors=True)
        return {'success': False, 'method': 'zip', 'error': '更新失败: ' + str(e)}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    _write_version_file(home, version)
    _auto_link_app(home)
    return {'success': True, 'method': 'zip',
            'message': 'DSH 运行时更新完成（' + (version or 'latest') + '），请重启 DSH 生效',
            'version': version, 'error': ''}
