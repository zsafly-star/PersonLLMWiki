"""MCP 工作空间工具 handlers。

让任务流水线中的 agent 在「当前任务工作空间」这个电脑文件夹里读写文件：
- list_workspace：列出目录内容
- read_workspace_file：读取文本文件
- write_workspace_file：写入/追加文本文件

路径全部相对工作空间根目录解析（common.workspace_ctx + security.resolve_workspace_path），
防止 agent 越界写盘。工作空间由 orchestrator 在运行节点前设置。
"""
import json
import os
import tempfile

from .errors import INVALID_PARAMS, MCPError
from .security import resolve_workspace_path

# 读取文件的最大字节数，超出的部分截断并提示
_READ_MAX_BYTES = 256 * 1024


def _text_content(obj):
    if isinstance(obj, str):
        text = obj
    else:
        text = json.dumps(obj, ensure_ascii=False)
    return {'content': [{'type': 'text', 'text': text}]}


def _error_content(message: str):
    return {
        'isError': True,
        'content': [{'type': 'text', 'text': message}],
    }


def handle_list_workspace(args: dict) -> dict:
    """列出工作空间目录内容（默认根目录）。

    Args:
        args: {path: str (optional, 默认 '' 表示根目录)}

    Returns:
        [{name, type: 'dir'|'file', path: str, size?: int}]
    """
    sub = args.get('path') or ''
    abs_dir = resolve_workspace_path(sub)

    if not os.path.isdir(abs_dir):
        return _error_content(f'目录不存在: {sub or "."}')

    entries = []
    try:
        names = sorted(os.listdir(abs_dir), key=lambda n: n.lower())
    except PermissionError:
        return _error_content(f'无权限读取: {sub or "."}')

    dirs = []
    files = []
    for name in names:
        if name.startswith('.'):
            continue
        full = os.path.join(abs_dir, name)
        rel = (sub + '/' + name).lstrip('/') if sub else name
        if os.path.isdir(full):
            dirs.append({'name': name, 'type': 'dir', 'path': rel})
        else:
            size = 0
            try:
                size = os.path.getsize(full)
            except OSError:
                pass
            files.append({'name': name, 'type': 'file', 'path': rel, 'size': size})

    return _text_content(dirs + files)


def handle_read_workspace_file(args: dict) -> dict:
    """读取工作空间内的文本文件。

    Args:
        args: {path: str (required)}

    Returns:
        {path, size, truncated, content}
    """
    if 'path' not in args or not args['path']:
        raise MCPError(INVALID_PARAMS, 'path 参数必填')

    abs_path = resolve_workspace_path(args['path'])
    if not os.path.isfile(abs_path):
        return _error_content(f'文件不存在: {args["path"]}')

    try:
        total = os.path.getsize(abs_path)
    except OSError:
        total = 0

    try:
        with open(abs_path, 'r', encoding='utf-8') as f:
            content = f.read(_READ_MAX_BYTES)
            truncated = len(content) < total
    except UnicodeDecodeError:
        return _error_content(f'不是文本文件（无法按 UTF-8 读取）: {args["path"]}')
    except (PermissionError, OSError) as e:
        return _error_content(f'读取失败: {e}')

    return _text_content({
        'path': args['path'],
        'size': total,
        'truncated': truncated,
        'content': content,
    })


def handle_write_workspace_file(args: dict) -> dict:
    """在工作空间内写入或追加文本文件。

    Args:
        args: {
            path: str (required),
            content: str (required),
            mode: str (optional, "overwrite"|"append", default "overwrite"),
        }

    Returns:
        {path, bytes_written, created, mode}
    """
    if 'path' not in args or not args['path']:
        raise MCPError(INVALID_PARAMS, 'path 参数必填')
    if 'content' not in args or not isinstance(args['content'], str):
        raise MCPError(INVALID_PARAMS, 'content 参数必填且必须是字符串')

    raw_path = args['path']
    content = args['content']
    mode = args.get('mode', 'overwrite')
    if mode not in ('overwrite', 'append'):
        raise MCPError(INVALID_PARAMS, 'mode 必须是 overwrite 或 append')

    abs_path = resolve_workspace_path(raw_path)

    parent_dir = os.path.dirname(abs_path)
    if not os.path.isdir(parent_dir):
        os.makedirs(parent_dir, exist_ok=True)

    created = not os.path.exists(abs_path)

    try:
        if mode == 'overwrite':
            fd, tmp_path = tempfile.mkstemp(dir=parent_dir)
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    f.write(content)
                os.replace(tmp_path, abs_path)
            except Exception:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise
        else:
            with open(abs_path, 'a', encoding='utf-8') as f:
                f.write(content)
    except (PermissionError, OSError) as e:
        raise MCPError(INVALID_PARAMS, f'写入失败: {e}')

    return _text_content({
        'path': raw_path,
        'bytes_written': len(content.encode('utf-8')),
        'created': created,
        'mode': mode,
    })
