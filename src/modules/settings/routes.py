from flask import Blueprint, request, render_template
from common.response import success_response, error_response
from common.llm import LLMService
from common.llm_config import LLMConfigService
from common.embedding_config import EmbeddingConfigService
import os
import sys
import json
import shutil

settings_bp = Blueprint('settings', __name__, template_folder='templates')

# ──────────── Profile ────────────

_PROFILE_FILE = None


def _get_profile_path():
    """获取 profile.json 路径（懒计算）"""
    global _PROFILE_FILE
    if _PROFILE_FILE is None:
        from config import Config
        _PROFILE_FILE = os.path.join(Config.INSTANCE_PATH, 'profile.json')
    return _PROFILE_FILE


def _read_profile():
    """读取 profile 数据"""
    path = _get_profile_path()
    if os.path.isfile(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def _write_profile(data):
    """写入 profile 数据"""
    path = _get_profile_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@settings_bp.route('/api/settings/profile', methods=['GET'])
def get_profile():
    """获取用户 profile（用户名、头像）"""
    return success_response(_read_profile())


@settings_bp.route('/api/settings/profile', methods=['POST'])
def save_profile():
    """保存用户 profile"""
    data = request.get_json(silent=True) or {}
    profile = _read_profile()
    if 'username' in data:
        profile['username'] = data['username'].strip()
    if 'avatar' in data:
        profile['avatar'] = data['avatar'].strip()
    _write_profile(profile)
    return success_response(profile, '保存成功')


@settings_bp.route('/settings')
def settings():
    return render_template('settings.html', active_view='settings')


@settings_bp.route('/api/llm/providers', methods=['GET'])
def get_providers():
    providers = LLMService.get_provider_list()
    models = LLMService.get_all_models()
    return success_response({
        'providers': providers,
        'models': models
    })


@settings_bp.route('/api/llm/configs', methods=['GET'])
def get_llm_configs():
    configs = LLMConfigService.get_all()
    return success_response(configs)


@settings_bp.route('/api/llm/configs', methods=['POST'])
def create_llm_config():
    data = request.get_json()
    if not data or 'provider' not in data:
        return error_response('缺少 provider')

    config = LLMConfigService.create(data)
    return success_response(config, '创建成功')


@settings_bp.route('/api/llm/configs/<int:config_id>', methods=['PUT'])
def update_llm_config(config_id):
    data = request.get_json()
    config = LLMConfigService.update(config_id, data)
    if config:
        return success_response(config, '更新成功')
    return error_response('配置不存在', 404)


@settings_bp.route('/api/llm/configs/<int:config_id>', methods=['DELETE'])
def delete_llm_config(config_id):
    success = LLMConfigService.delete(config_id)
    if success:
        return success_response(None, '删除成功')
    return error_response('配置不存在', 404)


@settings_bp.route('/api/llm/configs/<int:config_id>/test', methods=['POST'])
def test_llm_config(config_id):
    result = LLMConfigService.test_connection(config_id)
    if result['success']:
        return success_response(result)
    return error_response(result['message'])


# ──────────── Embedding 配置 ────────────

@settings_bp.route('/api/embedding/config', methods=['GET'])
def get_embedding_config():
    config = EmbeddingConfigService.get_dict()
    return success_response(config)


@settings_bp.route('/api/embedding/config', methods=['POST'])
def save_embedding_config():
    data = request.get_json() or {}
    config = EmbeddingConfigService.save(data)
    return success_response(config, '保存成功')


@settings_bp.route('/api/embedding/test', methods=['POST'])
def test_embedding_config():
    result = EmbeddingConfigService.test_connection()
    if result['success']:
        return success_response(result)
    return error_response(result['message'])


# ──────────── 关于 / 在线更新 ────────────

_VERSIONS_URL = os.getenv(
    'VERSIONS_URL',
    'https://raw.githubusercontent.com/zsafly-star/PersonLLMWiki/main/versions.json'
)

_GITHUB_RELEASES_URL = 'https://api.github.com/repos/zsafly-star/PersonLLMWiki/releases/latest'


def _check_github_release():
    """检查 GitHub Releases 最新版本（安装版升级通道）。

    返回 {latest, current, has_update, notes, date, size_mb, url, kind:'installer'}；
    网络/解析失败返回 None。
    """
    import urllib.request

    req = urllib.request.Request(
        _GITHUB_RELEASES_URL,
        headers={
            'User-Agent': 'PersonLLMWiki-Updater',
            'Accept': 'application/vnd.github+json',
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except Exception:
        return None

    tag = (data.get('tag_name') or '').strip()
    latest = tag.lstrip('vV').strip()
    if not latest:
        return None

    current = _get_current_version()
    has_update = _compare_versions(latest, current) > 0

    url = ''
    size = 0
    for asset in data.get('assets') or []:
        name = asset.get('name') or ''
        if 'PersonLLMWiki-Setup-' in name and name.endswith('.exe'):
            url = asset.get('browser_download_url') or ''
            size = asset.get('size') or 0
            break

    body = data.get('body') or ''
    notes = '\n'.join([ln for ln in body.splitlines() if ln.strip()][:8])

    return {
        'latest': latest,
        'current': current,
        'has_update': has_update,
        'notes': notes,
        'date': (data.get('published_at') or '')[:10],
        'size_mb': round(size / 1024 / 1024, 1) if size else 0,
        'url': url,
        'kind': 'installer',
    }


def _get_app_dir():
    """获取 app 代码目录（src/）"""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _get_project_root():
    """获取项目根目录（PersonLLMWiki/PersonLLMWiki/，app 的上级）"""
    return os.path.dirname(_get_app_dir())


def _get_version_file():
    """获取 VERSION 文件路径"""
    return os.path.join(_get_project_root(), 'VERSION')


def _get_current_version():
    """读取当前版本号。

    sys.frozen（安装版）时优先读打包进去的 app_version.txt（含完整构建号），
    否则回退根目录 VERSION 文件（源码/zip 部署）。
    """
    if getattr(sys, 'frozen', False):
        bases = [getattr(sys, '_MEIPASS', ''), os.path.dirname(sys.executable)]
        for base in bases:
            if not base:
                continue
            vf = os.path.join(base, 'app_version.txt')
            if os.path.isfile(vf):
                with open(vf, 'r', encoding='utf-8') as f:
                    v = f.read().strip()
                if v:
                    return v
    vf = _get_version_file()
    if os.path.isfile(vf):
        with open(vf, 'r') as f:
            return f.read().strip()
    return '0.0.0'


def _is_dev_mode():
    """是否为开发模式（存在 .git 目录）"""
    return os.path.isdir(os.path.join(_get_project_root(), '.git')) or \
           os.path.isdir(os.path.join(_get_app_dir(), '.git'))


def _is_embedded_mode():
    """是否为 embedded 运行模式"""
    return 'runtime' in os.path.dirname(sys.executable).lower()


def _check_dependencies():
    """逐个检测关键依赖是否安装（浅检测，不深度导入避免触发包内部 bug）"""
    import importlib.util
    checks = {}
    deps = [
        ('flask', 'flask'),
        ('flask_sqlalchemy', 'flask-sqlalchemy'),
        ('openai', 'openai'),
        ('requests', 'requests'),
        ('markdown', 'markdown'),
        ('jieba', 'jieba'),
        ('fitz', 'pymupdf'),
        ('fastembed', 'fastembed'),
        ('fastmcp', 'fastmcp'),
        ('rank_bm25', 'rank-bm25'),
        ('apscheduler', 'APScheduler'),
    ]
    for module, pip_name in deps:
        checks[pip_name] = importlib.util.find_spec(module) is not None
    return checks


def _get_disk_info():
    """获取磁盘剩余空间（返回 MB）"""
    try:
        import shutil as _sh
        total, used, free = _sh.disk_usage(_get_project_root())
        return {
            'total_mb': round(total / 1024 / 1024),
            'free_mb': round(free / 1024 / 1024),
        }
    except Exception:
        return None


def _get_mcp_services():
    """获取 MCP 服务清单"""
    from config import Config
    bin_dir = Config.MCP_DIR
    services = []
    if os.path.isdir(bin_dir):
        for name in sorted(os.listdir(bin_dir)):
            svc_path = os.path.join(bin_dir, name)
            if os.path.isdir(svc_path):
                has_json = os.path.isfile(os.path.join(svc_path, 'service.json'))
                services.append({'name': name, 'has_config': has_json})
    return services


@settings_bp.route('/api/settings/version', methods=['GET'])
def get_version_info():
    """返回当前版本信息和环境诊断"""
    project_root = _get_project_root()
    from config import Config
    resource_path = getattr(Config, 'RESOURCE_BASE_PATH', '') or os.path.join(project_root, 'resource')

    # 检测数据目录可写性
    data_writable = os.access(resource_path, os.W_OK) if os.path.isdir(resource_path) else None

    return success_response({
        'current': _get_current_version(),
        'python_version': '%d.%d.%d' % sys.version_info[:3],
        'python_path': sys.executable,
        'mode': 'embedded' if _is_embedded_mode() else ('dev' if _is_dev_mode() else 'standalone'),
        'versions_url': _VERSIONS_URL,
        'can_online_update': not _is_dev_mode(),
        # 环境诊断
        'dependencies': _check_dependencies(),
        'disk': _get_disk_info(),
        'data_writable': data_writable,
        'project_root': project_root,
        'mcp_services': _get_mcp_services(),
    })


# ──────────── 路径设置 ────────────

@settings_bp.route('/api/settings/path', methods=['GET'])
def get_path():
    """返回当前资源路径 + 固定应用数据目录"""
    from config import Config
    return success_response({
        'resource_path': getattr(Config, 'RESOURCE_BASE_PATH', ''),
        'data_dir': getattr(Config, 'USER_DATA_DIR', ''),
        'instance_path': getattr(Config, 'INSTANCE_PATH', ''),
        'mcp_dir': getattr(Config, 'MCP_DIR', ''),
        'skills_dir': getattr(Config, 'SKILLS_DIR', ''),
    })


@settings_bp.route('/api/settings/path', methods=['POST'])
def save_path():
    """保存资源路径到 .env 并创建目录"""
    from config import Config

    data = request.get_json(silent=True) or {}
    path = (data.get('resource_path') or '').strip()

    if not path:
        return error_response('路径不能为空')

    # 转为绝对路径
    path = os.path.abspath(path)

    # .env 固定写入用户数据目录
    env_path = os.path.join(Config.USER_DATA_DIR, '.env')
    os.makedirs(Config.USER_DATA_DIR, exist_ok=True)

    lines = []
    found = False
    if os.path.isfile(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip().startswith('RESOURCE_BASE_PATH='):
                    lines.append('RESOURCE_BASE_PATH=' + path + '\n')
                    found = True
                else:
                    lines.append(line)

    if not found:
        lines.append('RESOURCE_BASE_PATH=' + path + '\n')

    # 先写入临时文件再原子替换，避免文件锁定问题
    import tempfile
    tmp_fd, tmp_path = tempfile.mkstemp(dir=Config.USER_DATA_DIR, suffix='.tmp')
    try:
        with os.fdopen(tmp_fd, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        os.replace(tmp_path, env_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        raise

    # 创建所需子目录（仅用户内容）
    subdirs = ['article', 'img', 'attachments', 'wiki']
    created = []
    for sub in subdirs:
        d = os.path.join(path, sub)
        os.makedirs(d, exist_ok=True)
        created.append(d)

    # 同步更新 Config（当前进程生效）
    Config.RESOURCE_BASE_PATH = path

    # 重新初始化内置 MCP 服务和 Skills（路径变更后重新扫描）
    try:
        from common.builtin_mcp_manager import reinit as _reinit_mcp
        _reinit_mcp()
        print(f'[Settings] 资源路径已切换到 {path}，重新扫描 MCP 服务和 Skills')
    except Exception as e:
        print(f'[Settings] MCP 重新初始化失败（非致命）: {e}')

    return success_response({
        'resource_path': path,
        'created_dirs': created,
    }, '路径保存成功，已创建资源目录')


@settings_bp.route('/api/settings/upgrade/check', methods=['POST'])
def check_upgrade():
    """检查远程是否有新版本（安装版走 GitHub Releases，其余走 versions.json）。"""
    if _is_dev_mode():
        return error_response('开发模式下请使用 git pull 更新代码')

    # 安装版（sys.frozen）→ GitHub Releases
    if getattr(sys, 'frozen', False):
        info = _check_github_release()
        if info is None:
            return error_response('获取版本信息失败（GitHub Releases 不可达）')
        return success_response(info)

    # 源码/zip 部署 → 维持 versions.json 流程
    import urllib.request
    try:
        req = urllib.request.Request(
            _VERSIONS_URL,
            headers={'User-Agent': 'PersonLLMWiki-Web-Updater'}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        return error_response(f'获取版本信息失败: {e}')

    latest = data.get('latest', '0.0.0')
    current = _get_current_version()

    # 版本比较
    has_update = _compare_versions(latest, current) > 0

    info = data.get('versions', {}).get(latest, {})
    return success_response({
        'has_update': has_update,
        'current': current,
        'latest': latest,
        'notes': info.get('notes', ''),
        'date': info.get('date', ''),
        'size_mb': info.get('size_mb', 0),
        'url': info.get('url', ''),
        'kind': 'zip',
    })


@settings_bp.route('/api/settings/upgrade/apply', methods=['POST'])
def apply_upgrade():
    """下载并应用增量更新"""
    if _is_dev_mode():
        return error_response('开发模式下请使用 git pull 更新代码')

    import urllib.request
    import tempfile
    import zipfile
    import shutil

    # Step 1: 获取远程版本信息
    try:
        req = urllib.request.Request(
            _VERSIONS_URL,
            headers={'User-Agent': 'PersonLLMWiki-Web-Updater'}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        return error_response(f'获取版本信息失败: {e}')

    latest = data.get('latest', '0.0.0')
    current = _get_current_version()

    if _compare_versions(latest, current) <= 0:
        return error_response('已是最新版本，无需更新')

    info = data.get('versions', {}).get(latest)
    if not info or not info.get('url'):
        return error_response(f'版本 {latest} 的下载地址不存在')

    app_dir = _get_app_dir()
    version_file = _get_version_file()
    backup_dir = app_dir + '_backup'

    # Step 2: 下载增量包
    tmp_dir = tempfile.mkdtemp(prefix='personllmwiki_web_update_')
    zip_path = os.path.join(tmp_dir, f'update-{latest}.zip')

    try:
        dl_req = urllib.request.Request(
            info['url'],
            headers={'User-Agent': 'PersonLLMWiki-Web-Updater'}
        )
        with urllib.request.urlopen(dl_req, timeout=300) as resp:
            with open(zip_path, 'wb') as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
    except Exception as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return error_response(f'下载更新包失败: {e}')

    # Step 3: 备份当前 app/
    try:
        if os.path.isdir(app_dir):
            if os.path.isdir(backup_dir):
                shutil.rmtree(backup_dir)
            shutil.copytree(app_dir, backup_dir)

        # Step 4: 清空 app_dir 并解压
        if os.path.isdir(app_dir):
            shutil.rmtree(app_dir)
        os.makedirs(app_dir)

        with zipfile.ZipFile(zip_path) as z:
            names = z.namelist()
            top_dirs = set(n.split('/')[0] for n in names if '/' in n)

            for name in z.namelist():
                if name.endswith('/'):
                    continue
                rel = name
                for prefix in top_dirs:
                    if name.startswith(prefix + '/'):
                        rel = name[len(prefix) + 1:]
                        break
                if not rel:
                    continue
                dest = os.path.join(app_dir, rel)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with z.open(name) as src, open(dest, 'wb') as dst:
                    dst.write(src.read())

        # Step 5: 更新 VERSION
        with open(version_file, 'w') as f:
            f.write(latest)

        # Step 6: 清理
        if os.path.isdir(backup_dir):
            shutil.rmtree(backup_dir)
        shutil.rmtree(tmp_dir, ignore_errors=True)

        return success_response({
            'new_version': latest,
        }, f'更新成功！当前版本: {latest}，请重启服务以完成更新')

    except Exception as e:
        # 回滚
        if os.path.isdir(app_dir):
            shutil.rmtree(app_dir, ignore_errors=True)
        if os.path.isdir(backup_dir):
            shutil.move(backup_dir, app_dir)
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return error_response(f'更新失败（已回滚）: {e}')


@settings_bp.route('/api/settings/upgrade/download-setup', methods=['POST'])
def download_setup():
    """下载新版 Setup.exe 到临时目录（安装版升级），返回本地路径与大小。"""
    data = request.get_json(silent=True) or {}
    url = (data.get('url') or '').strip()
    if not url.startswith('https://'):
        return error_response('无效的下载地址')

    import urllib.request
    import tempfile

    local_path = os.path.join(tempfile.gettempdir(), 'PersonLLMWiki-Setup-latest.exe')
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'PersonLLMWiki-Updater'})
        with urllib.request.urlopen(req, timeout=300) as resp:
            with open(local_path, 'wb') as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
    except Exception as e:
        return error_response(f'下载安装包失败: {e}')

    size = os.path.getsize(local_path)
    return success_response({
        'path': local_path,
        'size': size,
        'size_mb': round(size / 1024 / 1024, 1),
    })


@settings_bp.route('/api/settings/upgrade/launch-installer', methods=['POST'])
def launch_installer():
    """退出应用并启动安装器（安装版升级）。"""
    data = request.get_json(silent=True) or {}
    setup_path = (data.get('path') or '').strip()
    if not setup_path or not os.path.isfile(setup_path):
        return error_response('安装包不存在')

    import subprocess
    import threading
    import time

    def _do_launch():
        time.sleep(0.5)  # 等响应发出
        subprocess.Popen(
            [setup_path],
            cwd=os.path.dirname(setup_path),
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        # 启动安装器后请求应用退出（桌面壳走托盘退出；无回调则直接结束进程兜底）
        try:
            from common.desktop_signals import request_quit
            if not request_quit():
                os._exit(0)
        except Exception:
            os._exit(0)

    threading.Thread(target=_do_launch, daemon=True).start()
    return success_response({'status': 'launching'}, '正在启动安装向导...')


def _compare_versions(a, b):
    """比较版本号。返回 1(a>b) / 0(a==b) / -1(a<b)。

    支持 4 段（如 1.0.1.007），缺段补 0；每段取前导数字，容错 v 前缀。
    """
    import re

    def _parts(s):
        out = []
        for seg in str(s or '').strip().lstrip('vV').split('.'):
            m = re.match(r'\d+', seg)
            out.append(int(m.group(0)) if m else 0)
        return out

    pa = _parts(a)
    pb = _parts(b)
    for i in range(max(len(pa), len(pb))):
        va = pa[i] if i < len(pa) else 0
        vb = pb[i] if i < len(pb) else 0
        if va > vb:
            return 1
        if va < vb:
            return -1
    return 0


# ──────────── DeepSeek Harness ────────────

@settings_bp.route('/api/settings/dsh', methods=['GET'])
def get_dsh():
    """DSH 配置 + 状态 + 运行时信息（设置页 DeepSeek Harness 区块）"""
    from common import dsh_bridge
    return success_response({
        'config': dsh_bridge.get_config(),
        'status': dsh_bridge.get_status(),
        'runtime': dsh_bridge.get_runtime_info(),
    })


@settings_bp.route('/api/settings/dsh', methods=['POST'])
def save_dsh():
    """关联已有 DSH：保存 DSH_CMD / DSH_URL，并立即探测版本与运行状态"""
    from common import dsh_bridge
    if not dsh_bridge.is_local_origin(request.headers.get('Origin')):
        return error_response('跨源请求被拒绝', 403)
    data = request.get_json(silent=True) or {}
    try:
        cfg = dsh_bridge.set_config(
            dsh_cmd=data.get('dsh_cmd'),
            dsh_url=data.get('dsh_url'),
            auto_start=data.get('auto_start'),
            dsh_mirror_url=data.get('dsh_mirror_url'),
            dsh_registry=data.get('dsh_registry'),
        )
    except ValueError as e:
        return error_response(str(e))
    return success_response({
        'config': cfg,
        'status': dsh_bridge.get_status(),
    }, '已保存关联')


@settings_bp.route('/api/settings/dsh/start', methods=['POST'])
def start_dsh():
    """拉起 DSH web"""
    from common import dsh_bridge
    if not dsh_bridge.is_local_origin(request.headers.get('Origin')):
        return error_response('跨源请求被拒绝', 403)
    return success_response(dsh_bridge.start())


@settings_bp.route('/api/settings/dsh/stop', methods=['POST'])
def stop_dsh():
    """停止 DSH（best-effort）"""
    from common import dsh_bridge
    if not dsh_bridge.is_local_origin(request.headers.get('Origin')):
        return error_response('跨源请求被拒绝', 403)
    return success_response(dsh_bridge.stop())


@settings_bp.route('/api/settings/dsh/check', methods=['POST'])
def check_dsh_update():
    """更新检查：已装版本 vs npm registry 最新"""
    from common import dsh_bridge
    if not dsh_bridge.is_local_origin(request.headers.get('Origin')):
        return error_response('跨源请求被拒绝', 403)
    return success_response(dsh_bridge.check_update())


@settings_bp.route('/api/settings/dsh/reinstall', methods=['POST'])
def reinstall_dsh():
    """重新安装：下载运行时 zip → 校验 SHA256 → 解压 → 自动关联"""
    from common import dsh_bridge
    if not dsh_bridge.is_local_origin(request.headers.get('Origin')):
        return error_response('跨源请求被拒绝', 403)
    result = dsh_bridge.install_runtime()
    if result.get('success'):
        return success_response(result, result.get('message') or '重新安装完成')
    return error_response(result.get('error') or '重新安装失败')


@settings_bp.route('/api/settings/dsh/update', methods=['POST'])
def update_dsh_runtime():
    """一键更新：npm 增量优先，否则 zip 换 app 留 home"""
    from common import dsh_bridge
    if not dsh_bridge.is_local_origin(request.headers.get('Origin')):
        return error_response('跨源请求被拒绝', 403)
    result = dsh_bridge.update_runtime()
    if result.get('success'):
        return success_response(result, result.get('message') or '更新完成')
    return error_response(result.get('error') or '更新失败')


def _build_insert_entry(token):
    """构造 personllmwiki 的 DSH insert 条目（与 ~/.dsh 现有 cordis.patch.yml 语法一致）。"""
    lines = [
        '- insert:',
        '    - id: mcp-personllmwiki',
        "      name: '@deepseek-ai/dsh-mcp-client'",
        '      config:',
        '        serverName: personllmwiki',
        '        transport: streamable-http',
        '        url: http://127.0.0.1:5000/mcp',
        '        failOnStartupError: false',
    ]
    if token:
        lines.append('        token: ' + token)
    return '\n'.join(lines)


def _find_entry_end(content, start):
    """从 start（serverName: personllmwiki 位置）定位条目块结束：下一个条目边界或文件尾。"""
    candidates = [len(content)]
    for marker in ('\n- insert:', '\n    - id:', '\n- id:'):
        p = content.find(marker, start)
        if p != -1:
            candidates.append(p)
    return min(candidates)


def _add_token_to_entry(content, token):
    """在 personllmwiki 条目 config 块末尾补 token 行。返回 (new_content, changed)。"""
    marker = 'serverName: personllmwiki'
    idx = content.find(marker)
    if idx == -1:
        return content, False
    block_end = _find_entry_end(content, idx)
    if 'token:' in content[idx:block_end]:
        return content, False
    rstrip_end = block_end
    while rstrip_end > idx and content[rstrip_end - 1] in ' \t\r\n':
        rstrip_end -= 1
    new_content = content[:rstrip_end] + '\n        token: ' + token + content[rstrip_end:]
    return new_content, True


def _ensure_personllmwiki_entry(patch_path, token):
    """确保 cordis.patch.yml 含 personllmwiki MCP 连接条目，幂等。
    返回 (mcp_entry, token_replaced)。"""
    if os.path.isfile(patch_path):
        with open(patch_path, 'r', encoding='utf-8') as f:
            content = f.read()
    else:
        content = ''

    has_entry = ('mcp-personllmwiki' in content) or ('serverName: personllmwiki' in content)

    if has_entry:
        mcp_entry = 'exists'
        token_replaced = False
        if token:
            content, token_replaced = _add_token_to_entry(content, token)
    else:
        mcp_entry = 'added'
        content = content.rstrip('\n') + '\n' + _build_insert_entry(token) + '\n'
        token_replaced = bool(token)

    if mcp_entry == 'added' or token_replaced:
        os.makedirs(os.path.dirname(patch_path), exist_ok=True)
        with open(patch_path, 'w', encoding='utf-8') as f:
            f.write(content)

    return mcp_entry, token_replaced


@settings_bp.route('/api/settings/dsh/install-plugin', methods=['POST'])
def install_dsh_plugin():
    """安装 PLW 知识库插件：技能落到 DSH 数据目录 skills/，MCP 连接写入 cordis.patch.yml"""
    from common import dsh_bridge
    from config import Config
    if not dsh_bridge.is_local_origin(request.headers.get('Origin')):
        return error_response('跨源请求被拒绝', 403)

    # 1. 前置校验：DSH 已关联且版本满足
    status = dsh_bridge.get_status()
    if status['status'] in ('not_installed', 'version_low'):
        return error_response('请先关联/安装 DSH（当前状态：%s）' % status['status'])

    # 2. 插件源
    plugin_src = os.path.join(Config.SEED_DIR, 'dsh', 'dsh-personllmwiki')
    if not os.path.isdir(plugin_src):
        return error_response('插件包缺失：%s' % plugin_src)

    # 3. DSH 数据目录
    data_home = dsh_bridge.get_dsh_data_home()
    if not data_home or not data_home.strip():
        return error_response('无法定位 DSH 数据目录')

    # 4. 技能落地：skills/knowledge-base/SKILL.md → <data_home>/skills/knowledge-base/SKILL.md
    skill_src = os.path.join(plugin_src, 'skills', 'knowledge-base', 'SKILL.md')
    skill_dst = os.path.join(data_home, 'skills', 'knowledge-base', 'SKILL.md')
    skill_installed = False
    if os.path.isfile(skill_src):
        os.makedirs(os.path.dirname(skill_dst), exist_ok=True)
        shutil.copy2(skill_src, skill_dst)
        skill_installed = True

    # 5. MCP 连接：写入 <data_home>/profiles/web/cordis.patch.yml（幂等）
    token = Config.MCP_ADMIN_TOKEN or ''
    patch_path = os.path.join(data_home, 'profiles', 'web', 'cordis.patch.yml')
    mcp_entry, token_replaced = _ensure_personllmwiki_entry(patch_path, token)

    return success_response({
        'data_home': data_home,
        'skill_installed': skill_installed,
        'mcp_entry': mcp_entry,
        'token_replaced': token_replaced,
        'note': '请重启 DSH 后生效',
    }, '插件已安装，请重启 DSH 生效')
