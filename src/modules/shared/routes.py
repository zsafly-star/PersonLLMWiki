"""共享中心模块（§10.10 一期：浏览 / 详情 / 安装）。

浏览共享仓库（shared/）中的 skills / workflows / agents / mcp：
- 复用 INSTANCE_MODE=personal + COMMON_GIT_REPO 的 git 同步管道（共享中心只是其 UI 化）；
- 未启用公共库（single 模式）时回退到本地 ~/.personllmwiki/shared/。

manifest 定稿见《DSH集成架构设计方案.md》§7.5（v0.5）。
"""
import json
import os
import re
import shutil

from flask import Blueprint, render_template, request

from common.response import success_response, error_response
from config import Config

shared_bp = Blueprint('shared', __name__, template_folder='templates')

# 共享仓库子目录 → (类型, 描述文件)
_KINDS = (
    ('skills', 'skill', 'SKILL.md'),
    ('workflows', 'workflow', 'workflow.json'),
    ('agents', 'agent', 'agent.json'),
    ('mcp', 'mcp-server', 'service.json'),
)

_DEFAULT_SOURCE_LEVEL = '同事'


# ─── 路径解析 ──────────────────────────────────────────────

def _get_shared_root():
    """共享仓库根目录：优先公共库同步目录，回退本地 ~/.personllmwiki/shared/。"""
    common = Config.COMMON_RESOURCE_PATH
    if common and os.path.isdir(common):
        return os.path.join(common, 'shared')
    return os.path.join(Config.USER_DATA_DIR, 'shared')


def _get_dsh_home():
    """DSH 运行时安装目录（只读引用，不改 dsh_bridge.py）。"""
    try:
        from common.dsh_bridge import get_dsh_home
        return get_dsh_home()
    except Exception:
        return os.path.join(
            os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'),
            'DeepSeekHarness')


def _ensure_shared_root():
    """确保共享仓库根存在；不存在则创建 §7.5 示例结构（含 1 个示例 agent.json）。"""
    root = _get_shared_root()
    if os.path.isdir(root):
        return root

    os.makedirs(root, exist_ok=True)
    for sub in ('skills', 'workflows', 'agents', 'mcp'):
        os.makedirs(os.path.join(root, sub), exist_ok=True)

    # 示例 agent（§7.5：annual-report）
    example_dir = os.path.join(root, 'agents', 'annual-report')
    os.makedirs(example_dir, exist_ok=True)
    example = {
        'name': 'annual-report',
        'version': '1.2.0',
        'type': 'agent',
        'description': '年度报告生成智能体示例',
        'requires_dsh': '>=0.1.0',
        'requires_mcp': ['personllmwiki'],
        'install': {'kind': 'copy-to', 'target': 'agents/'},
        'author': 'official',
        'sources': [],
        'source_level': '官方库',
    }
    with open(os.path.join(example_dir, 'agent.json'), 'w', encoding='utf-8') as f:
        json.dump(example, f, ensure_ascii=False, indent=2)

    index = (
        '# 共享中心\n\n'
        '本目录为共享仓库，供「共享中心」页面浏览与安装。\n\n'
        '## 结构\n'
        '- skills/    SKILL.md 技能（目录包：SKILL.md + scripts/）\n'
        '- workflows/ DSH workflow 脚本\n'
        '- agents/    agent 定义（agent.json）\n'
        '- mcp/       MCP 服务定义（service.json，凭证留空）\n\n'
        '## 索引\n'
        '- agents/annual-report（官方库）— 年度报告生成智能体示例\n'
    )
    with open(os.path.join(root, 'INDEX.md'), 'w', encoding='utf-8') as f:
        f.write(index)

    readme = '# 共享仓库\n\n发布（git 提交）与审批流留二期。\n'
    with open(os.path.join(root, 'README.md'), 'w', encoding='utf-8') as f:
        f.write(readme)

    return root


def _resolve_item_dir(root, item_path):
    """把相对 path 解析到共享仓库内的目录，防路径穿越。"""
    if not os.path.isdir(root):
        return None
    norm = (item_path or '').replace('\\', '/').strip('/')
    if not norm:
        return None
    parts = norm.split('/')
    if '..' in parts:
        return None
    item_dir = os.path.join(root, *parts)
    real_root = os.path.realpath(root)
    real_item = os.path.realpath(item_dir)
    if real_item != real_root and not real_item.startswith(real_root + os.sep):
        return None
    return item_dir if os.path.isdir(item_dir) else None


# ─── manifest 解析 ─────────────────────────────────────────

def _parse_front_matter(content):
    """解析 SKILL.md 的 YAML front matter，返回 (meta_dict, body)。"""
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n?(.*)', content, re.DOTALL)
    if not match:
        return {}, content
    meta = {}
    for line in match.group(1).split('\n'):
        line = line.strip()
        if not line or line.startswith('#') or ':' not in line:
            continue
        key, _, val = line.partition(':')
        meta[key.strip()] = val.strip().strip('"').strip("'")
    return meta, match.group(2)


def _split_list(value):
    if isinstance(value, list):
        return value
    if not value:
        return []
    return [v.strip() for v in str(value).replace('，', ',').split(',') if v.strip()]


def _manifest_file(item_dir, kind):
    for sub, k, desc_file in _KINDS:
        if k == kind:
            return os.path.join(item_dir, desc_file)
    return None


def _detect_kind(item_dir):
    for sub, kind, desc_file in _KINDS:
        if os.path.isfile(os.path.join(item_dir, desc_file)):
            return kind
    return None


def _load_manifest(item_dir, kind):
    """读取并归一化 manifest，返回 dict；失败返回 None。"""
    manifest_path = _manifest_file(item_dir, kind)
    if not manifest_path or not os.path.isfile(manifest_path):
        return None
    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except IOError:
        return None

    if kind == 'skill':
        meta, _body = _parse_front_matter(content)
        return {
            'name': meta.get('name', os.path.basename(item_dir)),
            'type': kind,
            'version': meta.get('version', ''),
            'description': meta.get('description', ''),
            'author': meta.get('author', ''),
            'source_level': meta.get('source_level', _DEFAULT_SOURCE_LEVEL),
            'requires_dsh': meta.get('requires_dsh', ''),
            'requires_mcp': _split_list(meta.get('requires_mcp', '')),
            'install': {'kind': 'copy-to', 'target': 'skills/'},
            'manifest': meta,
        }

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return None

    if kind == 'mcp-server':
        return {
            'name': data.get('name', os.path.basename(item_dir)),
            'type': kind,
            'version': data.get('version', ''),
            'description': data.get('description', ''),
            'author': data.get('author', ''),
            'source_level': data.get('source_level', _DEFAULT_SOURCE_LEVEL),
            'requires_dsh': data.get('requires_dsh', ''),
            'requires_mcp': data.get('requires_mcp', []),
            'install': {'kind': 'mcp-connect', 'target': 'mcp/'},
            'manifest': data,
        }

    install = data.get('install')
    if not isinstance(install, dict):
        target = 'workflows/' if kind == 'workflow' else 'agents/'
        install = {'kind': 'copy-to', 'target': target}
    return {
        'name': data.get('name', os.path.basename(item_dir)),
        'type': kind,
        'version': data.get('version', ''),
        'description': data.get('description', ''),
        'author': data.get('author', ''),
        'source_level': data.get('source_level', _DEFAULT_SOURCE_LEVEL),
        'requires_dsh': data.get('requires_dsh', ''),
        'requires_mcp': data.get('requires_mcp', []),
        'install': install,
        'manifest': data,
    }


def _scan_items(root):
    items = []
    for sub, kind, _desc_file in _KINDS:
        sub_dir = os.path.join(root, sub)
        if not os.path.isdir(sub_dir):
            continue
        for entry in sorted(os.listdir(sub_dir)):
            item_dir = os.path.join(sub_dir, entry)
            if not os.path.isdir(item_dir):
                continue
            info = _load_manifest(item_dir, kind)
            if info is None:
                continue
            info['path'] = (sub + '/' + entry).replace('\\', '/')
            items.append(info)
    return items


# ─── 安装动作 ──────────────────────────────────────────────

def _copy_target_dir(target, kind):
    target = (target or '').strip().rstrip('/')
    if target in ('skills', 'skills/'):
        return Config.SKILLS_DIR
    home = _get_dsh_home()
    if target in ('workflows', 'workflows/'):
        return os.path.join(home, 'workflows')
    if target in ('agents', 'agents/'):
        return os.path.join(home, 'agents')
    # 兜底按类型
    if kind == 'skill':
        return Config.SKILLS_DIR
    if kind == 'workflow':
        return os.path.join(home, 'workflows')
    return os.path.join(home, 'agents')


def _service_url(svc):
    if svc.get('url'):
        return svc['url']
    host = svc.get('host', '127.0.0.1')
    port = svc.get('port')
    if not port:
        return ''
    path = svc.get('path', '/mcp') or '/mcp'
    if not path.startswith('/'):
        path = '/' + path
    return 'http://{host}:{port}{path}'.format(host=host, port=port, path=path)


def _atomic_write(path, content):
    import tempfile
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix='.cordis-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(content)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def _append_cordis_patch(patch_path, name, url):
    """向 DSH cordis.patch.yml 追加 mcp 连接条目（insert: 语法），幂等。

    条目结构遵循设计文档 §7.5 / §5.1 的 {name, url, token} 连接声明。
    """
    entry_lines = [
        '    - name: ' + name,
        '      url: ' + url,
        '      token: ""',
    ]

    if os.path.isfile(patch_path):
        with open(patch_path, 'r', encoding='utf-8') as f:
            content = f.read()
        if 'name: ' + name in content:
            return False
        stripped = content.rstrip('\n')
        if 'insert:' in content:
            new_content = stripped + '\n' + '\n'.join(entry_lines) + '\n'
        else:
            new_content = stripped + '\n\ninsert:\n  mcpServers:\n' + '\n'.join(entry_lines) + '\n'
    else:
        new_content = 'insert:\n  mcpServers:\n' + '\n'.join(entry_lines) + '\n'

    _atomic_write(patch_path, new_content)
    return True


def _do_install(item_dir, kind, info):
    install = info.get('install') or {}
    install_kind = install.get('kind')
    target = install.get('target', '')

    # 兜底：缺省 install 时按类型推导
    if not install_kind:
        if kind == 'skill':
            install_kind, target = 'copy-to', 'skills/'
        elif kind == 'mcp-server':
            install_kind, target = 'mcp-connect', 'mcp/'
        elif kind == 'workflow':
            install_kind, target = 'copy-to', 'workflows/'
        else:
            install_kind, target = 'copy-to', 'agents/'

    if install_kind == 'copy-to':
        dest_root = _copy_target_dir(target, kind)
        name = info.get('name') or os.path.basename(item_dir)
        dest = os.path.join(dest_root, name)
        os.makedirs(dest_root, exist_ok=True)
        shutil.copytree(item_dir, dest, dirs_exist_ok=True)
        ok = os.path.isdir(dest)
        return success_response({
            'installed': ok,
            'dest': dest,
            'message': '已复制到 ' + dest,
        }, '安装成功' if ok else '安装失败')

    if install_kind == 'mcp-connect':
        return _install_mcp_connect(item_dir, info)

    if install_kind == 'import':
        return success_response(
            {'installed': False, 'message': 'import 为预留动作，暂未实现'}, '已记录')

    return error_response('未知安装类型: ' + str(install_kind))


def _install_mcp_connect(item_dir, info):
    svc_path = os.path.join(item_dir, 'service.json')
    try:
        with open(svc_path, 'r', encoding='utf-8') as f:
            svc = json.load(f)
    except (IOError, json.JSONDecodeError):
        return error_response('service.json 解析失败')

    name = svc.get('name') or info.get('name')
    url = _service_url(svc)
    if not url:
        return error_response('service.json 缺少 host/port 或 url，无法生成连接条目')

    patch_path = os.path.join(_get_dsh_home(), 'profiles', 'web', 'cordis.patch.yml')
    appended = _append_cordis_patch(patch_path, name, url)
    return success_response({
        'installed': appended,
        'patch_path': patch_path,
        'name': name,
        'url': url,
        'message': '已追加 cordis.patch.yml 条目，请重启 DSH 生效' if appended else '该 MCP 已存在，无需重复追加',
    }, '安装成功' if appended else '已存在')


# ─── 路由 ──────────────────────────────────────────────────

@shared_bp.route('/shared')
def shared_page():
    return render_template('shared.html', active_view='shared')


@shared_bp.route('/api/shared/items')
def list_items():
    root = _ensure_shared_root()
    return success_response(_scan_items(root))


@shared_bp.route('/api/shared/items/<path:item_path>')
def item_detail(item_path):
    root = _get_shared_root()
    item_dir = _resolve_item_dir(root, item_path)
    if item_dir is None:
        return error_response('条目不存在', 404)
    kind = _detect_kind(item_dir)
    if kind is None:
        return error_response('无法识别条目类型', 400)
    info = _load_manifest(item_dir, kind)
    if info is None:
        return error_response('manifest 解析失败', 400)
    info['path'] = item_path
    return success_response(info)


@shared_bp.route('/api/shared/install', methods=['POST'])
def install_item():
    data = request.get_json(silent=True) or {}
    item_path = (data.get('path') or '').strip()
    if not item_path:
        return error_response('缺少 path 参数')

    root = _get_shared_root()
    item_dir = _resolve_item_dir(root, item_path)
    if item_dir is None:
        return error_response('条目不存在', 404)
    kind = _detect_kind(item_dir)
    if kind is None:
        return error_response('无法识别条目类型', 400)
    info = _load_manifest(item_dir, kind)
    if info is None:
        return error_response('manifest 解析失败', 400)

    return _do_install(item_dir, kind, info)
