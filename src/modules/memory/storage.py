import os
import json
from datetime import datetime, timezone

from config import Config
from common.slug_utils import safe_slug


def ensure_memory_dirs():
    """创建 memories/ 与 memories/_raw/。"""
    os.makedirs(get_memories_dir(), exist_ok=True)
    os.makedirs(get_memories_raw_dir(), exist_ok=True)


# 向后兼容别名：routes.py / retrieval.py / tools_memory.py 仍通过 _safe_slug 引用
_safe_slug = safe_slug


def get_memories_dir():
    """返回 Config.MEMORIES_DIR"""
    return Config.MEMORIES_DIR


def get_memories_raw_dir():
    """返回 Config.MEMORIES_RAW_DIR"""
    return Config.MEMORIES_RAW_DIR


def save_memory(slug, body, *, kind, status='auto', source_chat_id=None,
                summary='', basis=None, source_refs=None, related_entities=None):
    """写 memories/<safe_slug>.md，返回文件路径。"""
    ensure_memory_dirs()

    safe_slug = _safe_slug(slug)
    filepath = os.path.join(get_memories_dir(), safe_slug + '.md')

    frontmatter = {
        'slug': safe_slug,
        'kind': kind,
        'status': status,
        'summary': summary,
        'created_at': datetime.now(timezone.utc).isoformat(),
    }

    if source_chat_id is not None:
        frontmatter['source_chat_id'] = source_chat_id

    if kind == 'decision':
        frontmatter['basis'] = basis or ''
        frontmatter['source_refs'] = source_refs or []
        frontmatter['related_entities'] = related_entities or []

    fm_lines = '---\n'
    fm_lines += json.dumps(frontmatter, ensure_ascii=False, indent=2)
    fm_lines += '\n---\n\n'

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(fm_lines + body)

    return filepath


def read_memory(slug):
    """读单条记忆，返回 {'frontmatter': dict, 'body': str, 'raw': str}；不存在返回 None。"""
    safe_slug = _safe_slug(slug)
    filepath = os.path.join(get_memories_dir(), safe_slug + '.md')

    if not os.path.isfile(filepath):
        return None

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    if content.startswith('---\n'):
        end = content.find('\n---\n', 4)
        if end != -1:
            fm_str = content[4:end]
            body = content[end + 5:].strip()
            try:
                frontmatter = json.loads(fm_str)
            except json.JSONDecodeError:
                frontmatter = {}
            return {'frontmatter': frontmatter, 'body': body, 'raw': content}

    return {'frontmatter': {}, 'body': content, 'raw': content}


def update_memory_status(slug, status):
    """把 frontmatter['status'] 改为 status 并重写文件（保留其余原字段）；不存在返回 False。"""
    data = read_memory(slug)
    if data is None:
        return False

    safe_slug = _safe_slug(slug)
    filepath = os.path.join(get_memories_dir(), safe_slug + '.md')

    frontmatter = data['frontmatter']
    frontmatter['status'] = status
    body = data['body']

    fm_lines = '---\n'
    fm_lines += json.dumps(frontmatter, ensure_ascii=False, indent=2)
    fm_lines += '\n---\n\n'

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(fm_lines + body)

    return True


def list_memories(kind=None, status=None, include_body=False):
    """列出记忆，返回 frontmatter 列表（已加 slug 与 body_length）；kind/status 为可选过滤。

    include_body=True 时额外附上 body（供列表卡片预览用，避免二次读盘）。
    """
    memories_dir = get_memories_dir()
    if not os.path.isdir(memories_dir):
        return []

    memories = []
    for name in sorted(os.listdir(memories_dir)):
        if not name.endswith('.md'):
            continue
        memory_data = read_memory(name[:-3])
        if memory_data:
            fm = memory_data['frontmatter']
            fm['slug'] = name[:-3]
            fm['body_length'] = len(memory_data['body'])
            if include_body:
                fm['body'] = memory_data['body']
            memories.append(fm)

    if kind is not None:
        memories = [m for m in memories if m.get('kind') == kind]
    if status is not None:
        memories = [m for m in memories if m.get('status') == status]

    return memories
