from flask import Blueprint, request, render_template
from common.response import success_response, error_response
from common.llm import LLMService
from common.llm_config import LLMConfigService
from common.embedding_config import EmbeddingConfigService
import os
import sys
import json

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
    'https://raw.githubusercontent.com/your-org/PersonLLMWiki/main/versions.json'
)


def _get_app_dir():
    """获取 app 代码目录"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _get_project_root():
    """获取项目根目录（app 的上级）"""
    return os.path.dirname(_get_app_dir())


def _get_version_file():
    """获取 VERSION 文件路径"""
    return os.path.join(_get_project_root(), 'VERSION')


def _get_current_version():
    """读取当前版本号"""
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
    """获取 bin/mcp 下的服务清单"""
    bin_dir = os.path.join(_get_app_dir(), 'bin', 'mcp')
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
    """返回当前资源路径"""
    from config import Config
    return success_response({
        'resource_path': getattr(Config, 'RESOURCE_BASE_PATH', ''),
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

    # 确定 .env 文件位置
    # 打包模式：写到 %APPDATA%\PersonLLMWiki\.env
    import sys as _sys
    if getattr(_sys, 'frozen', False):
        env_path = os.path.join(
            os.getenv('APPDATA', ''), 'PersonLLMWiki', '.env')
        os.makedirs(os.path.dirname(env_path), exist_ok=True)
    else:
        env_path = os.path.join(_get_project_root(), '.env')
        if not os.path.isfile(env_path):
            env_path = os.path.join(_get_app_dir(), '.env')

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

    with open(env_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)

    # 创建所需子目录
    subdirs = ['instance', 'article', 'img', 'attachments', 'wiki', 'bin/mcp', 'bin/skills']
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
    """检查远程是否有新版本"""
    if _is_dev_mode():
        return error_response('开发模式下请使用 git pull 更新代码')

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


def _compare_versions(a, b):
    """比较版本号。返回 1(a>b) / 0(a==b) / -1(a<b)"""
    pa = [int(x) for x in a.split('.')]
    pb = [int(x) for x in b.split('.')]
    for i in range(max(len(pa), len(pb))):
        va = pa[i] if i < len(pa) else 0
        vb = pb[i] if i < len(pb) else 0
        if va > vb:
            return 1
        if va < vb:
            return -1
    return 0
