"""OfficeCLI 文档工具集成。

内嵌 OfficeCLI 二进制（https://github.com/iOfficeAI/OfficeCLI），
实现对 Word/Excel/PPT 文档的读写操作。二进制预置于 bin/officecli/ 目录，
支持 linux-x64、linux-arm64、mac-arm64、mac-x64、win-x64、win-arm64。
"""

import os
import sys
import json
import shutil
import subprocess
import platform

_BIN_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'bin', 'mcp', 'officecli'))


def _get_platform_id():
    """返回 OfficeCLI 的平台标识（如 linux-x64, win-x64, mac-arm64）"""
    system = platform.system().lower()  # windows / linux / darwin
    machine = platform.machine().lower()

    if system == 'darwin':
        system = 'mac'
    elif system == 'windows':
        system = 'win'

    if machine in ('x86_64', 'amd64'):
        arch = 'x64'
    elif machine in ('aarch64', 'arm64'):
        arch = 'arm64'
    else:
        arch = 'x64'

    return f'{system}-{arch}'


def _get_binary_name():
    """返回本地存储的二进制文件名"""
    pid = _get_platform_id()
    ext = '.exe' if sys.platform == 'win32' else ''
    return f'officecli-{pid}{ext}'


def _get_officecli_path():
    """获取 OfficeCLI 可执行文件路径"""
    # 优先级 1: 环境变量
    env_path = os.environ.get('OFFICECLI_PATH', '')
    if env_path and os.path.isfile(env_path):
        return env_path

    # 优先级 2: 本地 bin/officecli/ 目录
    binary_name = _get_binary_name()
    local_path = os.path.join(_BIN_DIR, binary_name)
    if os.path.isfile(local_path):
        return local_path

    # 优先级 3: 系统 PATH
    if shutil.which('officecli'):
        return 'officecli'

    return None


def _run_officecli(args, timeout=120):
    """执行 OfficeCLI 命令

    Returns:
        (returncode, stdout, stderr)
    """
    cli_path = _get_officecli_path()
    if not cli_path:
        return -1, '', f'OfficeCLI 不可用（平台: {_get_platform_id()}），'
        f'请将对应二进制放入 bin/officecli/ 目录'

    try:
        result = subprocess.run(
            [cli_path] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding='utf-8',
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        return -1, '', f'OfficeCLI 未找到: {cli_path}'
    except subprocess.TimeoutExpired:
        return -1, '', 'OfficeCLI 执行超时'
    except Exception as e:
        return -1, '', str(e)


def _text_content(obj):
    if isinstance(obj, str):
        text = obj
    else:
        text = json.dumps(obj, ensure_ascii=False, indent=2)
    return {'content': [{'type': 'text', 'text': text}]}


def _error_content(msg):
    return {'isError': True, 'content': [{'type': 'text', 'text': msg}]}


# ═══ Read ═══

def handle_read_document(args: dict) -> dict:
    """读取 Office 文档，返回 HTML 渲染内容（AI 可读）。"""
    path = args.get('path', '')
    if not path:
        return _error_content('path 参数必填')
    if not os.path.isfile(path):
        return _error_content(f'文件不存在: {path}')

    rc, stdout, stderr = _run_officecli(['view', path, 'html'])
    if rc != 0:
        return _error_content(stderr or '读取失败')
    return _text_content({'path': path, 'content': stdout, 'format': 'html'})


def handle_get_structure(args: dict) -> dict:
    """获取 Office 文档的 JSON 结构化数据。"""
    path = args.get('path', '')
    if not path:
        return _error_content('path 参数必填')
    if not os.path.isfile(path):
        return _error_content(f'文件不存在: {path}')

    selector = args.get('selector', '/')
    rc, stdout, stderr = _run_officecli(['get', path, selector, '--json'])
    if rc != 0:
        return _error_content(stderr or '读取失败')
    try:
        return _text_content(json.loads(stdout))
    except json.JSONDecodeError:
        return _text_content(stdout)


def handle_get_outline(args: dict) -> dict:
    """获取文档大纲（PPT 幻灯片标题、Word 段落等）。"""
    path = args.get('path', '')
    if not path:
        return _error_content('path 参数必填')
    if not os.path.isfile(path):
        return _error_content(f'文件不存在: {path}')

    rc, stdout, stderr = _run_officecli(['view', path, 'outline'])
    if rc != 0:
        return _error_content(stderr or '读取失败')
    return _text_content({'path': path, 'outline': stdout})


# ═══ Create & Write ═══

def handle_create_document(args: dict) -> dict:
    """创建新的空白 Office 文档。"""
    path = args.get('path', '')
    if not path:
        return _error_content('path 参数必填')

    rc, stdout, stderr = _run_officecli(['create', path])
    if rc != 0:
        return _error_content(stderr or '创建失败')
    return _text_content({'path': path, 'created': True})


def handle_add_element(args: dict) -> dict:
    """向 Office 文档添加元素。"""
    path = args.get('path', '')
    target = args.get('target', '/')
    element_type = args.get('type', '')
    props = args.get('props', {})

    if not path:
        return _error_content('path 参数必填')
    if not element_type:
        return _error_content('type 参数必填')

    cmd = ['add', path, target, '--type', element_type]
    for key, val in props.items():
        cmd.extend(['--prop', f'{key}={val}'])

    rc, stdout, stderr = _run_officecli(cmd)
    if rc != 0:
        return _error_content(stderr or '执行失败')
    return _text_content({'path': path, 'action': 'add', 'type': element_type,
                          'target': target, 'result': stdout or 'ok'})


def handle_set_element(args: dict) -> dict:
    """修改 Office 文档中的元素属性。"""
    path = args.get('path', '')
    selector = args.get('selector', '')
    props = args.get('props', {})

    if not path:
        return _error_content('path 参数必填')
    if not selector:
        return _error_content('selector 参数必填')
    if not props:
        return _error_content('props 参数必填')

    cmd = ['set', path, selector]
    for key, val in props.items():
        cmd.extend(['--prop', f'{key}={val}'])

    rc, stdout, stderr = _run_officecli(cmd)
    if rc != 0:
        return _error_content(stderr or '执行失败')
    return _text_content({'path': path, 'action': 'set', 'selector': selector,
                          'result': stdout or 'ok'})


# ═══ Excel 专项 ═══

def handle_list_sheets(args: dict) -> dict:
    """列出 Excel 文件中的所有工作表。"""
    path = args.get('path', '')
    if not path:
        return _error_content('path 参数必填')
    if not os.path.isfile(path):
        return _error_content(f'文件不存在: {path}')

    rc, stdout, stderr = _run_officecli(['get', path, '/', '--json'])
    if rc != 0:
        return _error_content(stderr or '读取失败')

    try:
        data = json.loads(stdout)
        sheets = data.get('sheets', []) if isinstance(data, dict) else []
        return _text_content({'path': path, 'sheets': sheets})
    except json.JSONDecodeError:
        return _error_content('无法解析文档结构')


def handle_read_sheet(args: dict) -> dict:
    """读取 Excel 工作表数据。"""
    path = args.get('path', '')
    if not path:
        return _error_content('path 参数必填')
    if not os.path.isfile(path):
        return _error_content(f'文件不存在: {path}')

    sheet = args.get('sheet', 'Sheet1')
    cell_range = args.get('range', '')
    selector = f'${sheet}'
    if cell_range:
        selector = f'${sheet}:{cell_range}'

    rc, stdout, stderr = _run_officecli(['get', path, selector, '--json'])
    if rc != 0:
        return _error_content(stderr or '读取失败')
    try:
        return _text_content(json.loads(stdout))
    except json.JSONDecodeError:
        return _text_content({'sheet': sheet, 'data': stdout})


def handle_write_cells(args: dict) -> dict:
    """向 Excel 工作表批量写入单元格数据。"""
    path = args.get('path', '')
    sheet = args.get('sheet', 'Sheet1')
    cells = args.get('cells', [])

    if not path:
        return _error_content('path 参数必填')
    if not cells:
        return _error_content('cells 参数必填')

    results = []
    for cell in cells:
        cell_ref = cell.get('cell', '')
        value = cell.get('value', '')
        if not cell_ref:
            continue
        cmd = ['set', path, f'${sheet}:{cell_ref}', '--prop', f'value={value}']
        rc, stdout, stderr = _run_officecli(cmd)
        results.append({'cell': cell_ref, 'ok': rc == 0,
                        'error': stderr if rc != 0 else None})

    return _text_content({'path': path, 'sheet': sheet, 'results': results})


def is_officecli_available():
    """检查 OfficeCLI 是否可用"""
    cli_path = _get_officecli_path()
    if not cli_path:
        return False
    try:
        result = subprocess.run(
            [cli_path, '--version'], capture_output=True, text=True, timeout=5,
            encoding='utf-8',
        )
        return result.returncode == 0 and bool(result.stdout)
    except Exception:
        return False


def get_officecli_status():
    """返回 OfficeCLI 状态信息（供 API 查询）"""
    cli_path = _get_officecli_path()
    if cli_path:
        try:
            result = subprocess.run(
                [cli_path, '--version'], capture_output=True, text=True, timeout=5,
                encoding='utf-8',
            )
            return {
                'available': True,
                'path': cli_path,
                'version': result.stdout.strip() if result.returncode == 0 else 'unknown',
                'platform': _get_platform_id(),
            }
        except Exception as e:
            print(f'[officecli] status error: {e}', flush=True)
    return {
        'available': False,
        'error': 'OfficeCLI 未安装',
        'platform': _get_platform_id(),
    }
