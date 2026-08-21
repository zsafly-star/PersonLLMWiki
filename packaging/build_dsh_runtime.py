"""DSH 运行时包自动构建与发布（模式 A：GitLab Release 资产）。

功能：
1. 查询 npm 最新 @deepseek-ai/dsh 版本
2. 与 GitLab 最近 Release tag 对比，无新版则退出
3. 构建 app\\（便携 Node + @deepseek-ai/dsh + 依赖 + package.json + dsh.cmd）→ zip + SHA256
4. 上传 zip 到 GitLab（/projects/:id/uploads）→ 创建 Release 并挂资产链接（模式 A）
   - 模式 B（Nexus raw 文件体 + GitLab 挂链接）作为 --mode B 扩展位
5. 触发：GitLab CI schedule（如每 6 小时）或 Windows 计划任务

用法：
  python build_dsh_runtime.py [--version X.Y.Z] [--mode A|B] [--dry-run]

环境变量（凭证一律从环境变量读取，不硬编码）：
  GITLAB_URL        默认 http://gitlab.xiangyuniot.com
  GITLAB_PROJECT    AiTeam/personllmwiki
  GITLAB_TOKEN      必填（PAT，api scope）
  NPM_REGISTRY      可选（默认 https://registry.npmjs.org）
  NODE_VERSION      可选（默认 24.19.0，与开发机一致）
  NEXUS_URL/NEXUS_TOKEN/NEXUS_REPO  模式 B 用

退出码：0=完成或已是最新，1=失败。
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
import urllib.error
import uuid
import zipfile

DSH_PKG = '@deepseek-ai/dsh'
TAG_PREFIX = 'dsh-runtime-v'
DEFAULT_NODE_VERSION = '24.19.0'
NODE_ZIP_URL = ('https://nodejs.org/dist/v{v}/node-v{v}-win-x64.zip')

GITLAB_URL = os.environ.get('GITLAB_URL', 'http://gitlab.xiangyuniot.com')
GITLAB_PROJECT = os.environ.get('GITLAB_PROJECT', 'AiTeam/personllmwiki')
NPM_REGISTRY = os.environ.get('NPM_REGISTRY', 'https://registry.npmjs.org')


def _log(msg):
    print(f'[build_dsh_runtime] {msg}', flush=True)


# Windows 控制台 GBK 下保证中文日志可读
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


def _http_json(url, method='GET', headers=None, body=None, timeout=30):
    """HTTP JSON 请求，返回 (status, data)。data 为 dict/list 或 None。"""
    req = urllib.request.Request(url, method=method, headers=headers or {})
    if body is not None:
        req.data = json.dumps(body).encode('utf-8')
        req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            data = json.loads(raw) if raw else None
            return resp.status, data
    except urllib.error.HTTPError as e:
        detail = e.read().decode('utf-8', errors='replace')[:500]
        return e.code, {'error': detail}
    except Exception as e:
        return -1, {'error': str(e)}


def _gitlab_headers():
    token = os.environ.get('GITLAB_TOKEN', '')
    if not token:
        raise SystemExit('[build_dsh_runtime] 缺少 GITLAB_TOKEN 环境变量')
    return {'PRIVATE-TOKEN': token}


def _project_url():
    return f'{GITLAB_URL}/api/v4/projects/{urllib.parse.quote(GITLAB_PROJECT, safe="")}'


def npm_latest_version():
    """查询 npm registry 最新版本。"""
    status, data = _http_json(f'{NPM_REGISTRY}/{DSH_PKG.replace("/", "%2F")}/latest')
    if status != 200 or not data:
        raise SystemExit(f'[build_dsh_runtime] 查询 npm 最新版本失败: {data}')
    return data.get('version')


def gitlab_latest_tag():
    """查询 GitLab 最近一个 dsh-runtime Release tag。"""
    status, data = _http_json(f'{_project_url()}/releases?per_page=100', headers=_gitlab_headers())
    if status != 200:
        raise SystemExit(f'[build_dsh_runtime] 查询 GitLab Releases 失败({status}): {data}')
    for rel in data or []:
        tag = rel.get('tag_name', '')
        if tag.startswith(TAG_PREFIX):
            return tag
    return None


def download_node(node_version, cache_dir):
    """下载便携 Node Windows zip（带缓存）。返回 zip 路径。"""
    url = NODE_ZIP_URL.format(v=node_version)
    cache_zip = os.path.join(cache_dir, f'node-v{node_version}-win-x64.zip')
    if not os.path.isfile(cache_zip):
        _log(f'下载便携 Node {node_version}...')
        urllib.request.urlretrieve(url, cache_zip)
        _log(f'下载完成: {cache_zip}')
    else:
        _log(f'使用缓存: {cache_zip}')
    return cache_zip


def build_app_dir(workdir, version, node_version, registry):
    """构建 app\\：node + package.json + npm install + dsh.cmd。"""
    app_dir = os.path.join(workdir, 'app')
    node_dir = os.path.join(app_dir, 'node')

    # 1. 便携 Node
    cache_dir = os.path.join(os.environ.get('TEMP', os.path.expanduser('~')), 'personllmwiki_build_cache')
    os.makedirs(cache_dir, exist_ok=True)
    node_zip = download_node(node_version, cache_dir)
    os.makedirs(node_dir, exist_ok=True)
    with zipfile.ZipFile(node_zip) as z:
        # node zip 顶层是 node-vX-win-x64/，解压时剥掉一层
        for member in z.namelist():
            parts = member.split('/', 1)
            if len(parts) == 2 and parts[1]:
                target = os.path.join(node_dir, parts[1].replace('/', os.sep))
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with z.open(member) as src, open(target, 'wb') as dst:
                    shutil.copyfileobj(src, dst)

    node_exe = os.path.join(node_dir, 'node.exe')
    if not os.path.isfile(node_exe):
        raise SystemExit(f'[build_dsh_runtime] node.exe 未找到: {node_exe}')

    # 2. package.json（声明 dsh 依赖）
    package = {
        'name': 'dsh-runtime',
        'private': True,
        'version': version,
        'dependencies': {DSH_PKG: version},
    }
    with open(os.path.join(app_dir, 'package.json'), 'w', encoding='utf-8') as f:
        json.dump(package, f, indent=2, ensure_ascii=False)

    # 3. npm install（registry 可配，加速走内网 proxy）
    _log(f'npm install {DSH_PKG}@{version}（可能较慢，依赖树 ~250MB）...')
    npm_cli = os.path.join(node_dir, 'node_modules', 'npm', 'bin', 'npm-cli.js')
    cmd = [node_exe, npm_cli, 'install', '--no-audit', '--no-fund']
    if registry:
        cmd += ['--registry', registry]
    result = subprocess.run(cmd, cwd=app_dir, capture_output=True, text=True, timeout=1800)
    if result.returncode != 0:
        raise SystemExit(f'[build_dsh_runtime] npm install 失败: {result.stderr[:800]}')
    _log('npm install 完成')

    # 4. dsh.cmd 启动器（设 DSH_HOME 指向同级 home\\，启动 web）
    launcher = (
        '@echo off\r\n'
        'setlocal\r\n'
        'set "DSH_HOME=%~dp0..\\home"\r\n'
        'set "PATH=%~dp0node;%PATH%"\r\n'
        '"%~dp0node\\node.exe" "%~dp0node\\node_modules\\npm\\bin\\npm-cli.js" '
        'exec --prefix "%~dp0" dsh web %*\r\n'
    )
    with open(os.path.join(app_dir, 'dsh.cmd'), 'w', encoding='utf-8') as f:
        f.write(launcher)

    return app_dir


def make_zip(workdir, app_dir, version):
    """打包 app\\ → dsh-runtime-{version}.zip + SHA256。"""
    zip_path = os.path.join(workdir, f'dsh-runtime-{version}.zip')
    _log(f'打包 {zip_path} ...')
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as z:
        for root, _, files in os.walk(app_dir):
            for fn in files:
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, workdir)
                z.write(full, rel.replace(os.sep, '/'))
    sha = hashlib.sha256()
    with open(zip_path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            sha.update(chunk)
    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    _log(f'zip 完成: {size_mb:.1f} MB, sha256={sha.hexdigest()}')
    return zip_path, sha.hexdigest(), round(size_mb, 1)


def upload_to_gitlab(zip_path, filename):
    """上传 zip 到 GitLab /uploads，返回完整可下载 URL。"""
    boundary = '----dshbuild' + uuid.uuid4().hex
    with open(zip_path, 'rb') as f:
        data = f.read()
    head = (
        f'--{boundary}\r\n'
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f'Content-Type: application/octet-stream\r\n\r\n'
    ).encode('utf-8')
    body = head + data + f'\r\n--{boundary}--\r\n'.encode('utf-8')

    headers = _gitlab_headers()
    headers['Content-Type'] = f'multipart/form-data; boundary={boundary}'
    req = urllib.request.Request(f'{_project_url()}/uploads', data=body, method='POST', headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            result = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise SystemExit(f'[build_dsh_runtime] 上传失败({e.code}): {e.read().decode("utf-8", "replace")[:500]}')
    full_path = result.get('full_path') or result.get('url', '')
    return f'{GITLAB_URL}{full_path}'


def create_gitlab_release(version, asset_url, sha256, notes):
    """创建 GitLab Release 并挂资产链接（模式 A）。"""
    tag = f'{TAG_PREFIX}{version}'
    body = {
        'name': f'DSH Runtime {version}',
        'tag_name': tag,
        'ref': 'main',
        'description': f'DSH 运行时包 v{version}\n\nsha256: `{sha256}`\n\n{notes}',
        'assets': {
            'links': [{
                'name': f'dsh-runtime-{version}.zip',
                'url': asset_url,
                'link_type': 'other',
            }]
        },
    }
    status, data = _http_json(f'{_project_url()}/releases', method='POST',
                              headers=_gitlab_headers(), body=body, timeout=60)
    if status not in (200, 201):
        raise SystemExit(f'[build_dsh_runtime] 创建 Release 失败({status}): {data}')
    _log(f'Release 创建完成: {tag} → {asset_url}')
    return tag


def publish_mode_b(workdir, zip_path, version, sha256):
    """模式 B（扩展位）：zip 传 Nexus raw，GitLab Release 挂 Nexus 链接。"""
    nexus_url = os.environ.get('NEXUS_URL', '')
    nexus_token = os.environ.get('NEXUS_TOKEN', '')
    nexus_repo = os.environ.get('NEXUS_REPO', 'nexus_pub_hosted_repo')
    if not nexus_url or not nexus_token:
        raise SystemExit('[build_dsh_runtime] 模式 B 需要 NEXUS_URL / NEXUS_TOKEN')
    # 上传 Nexus（curl -F 已验证的字段格式）
    cmd = ['curl.exe', '-s', '-u', f'admin:{nexus_token}',
           '-F', f'raw.directory=dsh', '-F', f'raw.asset1=@{zip_path}',
           '-F', f'raw.asset1.filename={os.path.basename(zip_path)}',
           f'{nexus_url}/service/rest/v1/components?repository={nexus_repo}']
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise SystemExit(f'[build_dsh_runtime] Nexus 上传失败: {result.stderr[:500]}')
    asset_url = f'{nexus_url}/repository/{nexus_repo}/dsh/{os.path.basename(zip_path)}'
    return create_gitlab_release(version, asset_url, sha256, notes='（文件体托管于 Nexus raw）')


def main():
    args = sys.argv[1:]
    version_override = None
    mode = 'A'
    dry_run = False
    if '--dry-run' in args:
        dry_run = True
        args.remove('--dry-run')
    for i, a in enumerate(args):
        if a == '--version' and i + 1 < len(args):
            version_override = args[i + 1]
        elif a == '--mode' and i + 1 < len(args):
            mode = args[i + 1].upper()
    if mode not in ('A', 'B'):
        raise SystemExit(f'[build_dsh_runtime] 未知模式: {mode}（仅 A/B）')

    version = version_override or npm_latest_version()
    _log(f'最新版本: {version}')

    latest_tag = gitlab_latest_tag()
    if latest_tag == f'{TAG_PREFIX}{version}':
        _log(f'GitLab 已有 {latest_tag}，无新版，退出')
        return 0
    _log(f'GitLab 当前: {latest_tag or "无"} → 构建 {version}')
    if dry_run:
        _log('[dry-run] 仅检查版本，跳过构建与发布')
        return 0

    workdir = tempfile.mkdtemp(prefix='dsh-runtime-build-')
    try:
        node_version = os.environ.get('NODE_VERSION', DEFAULT_NODE_VERSION)
        registry = os.environ.get('NPM_REGISTRY', '')
        app_dir = build_app_dir(workdir, version, node_version, registry)
        zip_path, sha256, size_mb = make_zip(workdir, app_dir, version)
        notes = f'构建于本地脚本；Node v{node_version}；体积 {size_mb} MB。'

        if mode == 'A':
            asset_url = upload_to_gitlab(zip_path, os.path.basename(zip_path))
            create_gitlab_release(version, asset_url, sha256, notes)
        else:
            publish_mode_b(workdir, zip_path, version, sha256)
        _log('全部完成')
        return 0
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == '__main__':
    sys.exit(main())
