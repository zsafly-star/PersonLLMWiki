import os
import json
import hashlib

from config import Config
from common.slug_utils import safe_slug as _safe_slug_fn


def ensure_wiki_dirs():
    wiki_root = get_wiki_root()
    for d in ['concepts', 'queries']:
        os.makedirs(os.path.join(wiki_root, d), exist_ok=True)


def get_wiki_root():
    return os.path.join(Config.RESOURCE_BASE_PATH, 'wiki')


def get_common_wiki_root():
    """公共库 Wiki 目录（personal 模式下使用）"""
    if Config.COMMON_WIKI_PATH:
        return Config.COMMON_WIKI_PATH
    return ''


def get_common_concepts_dir():
    """公共库概念页目录"""
    root = get_common_wiki_root()
    return os.path.join(root, 'concepts') if root else ''


def get_concepts_dir():
    return os.path.join(get_wiki_root(), 'concepts')


def get_queries_dir():
    return os.path.join(get_wiki_root(), 'queries')


def compute_hash(content):
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def _source_hashes_path():
    return os.path.join(get_wiki_root(), 'source_hashes.json')


def save_source_hashes(hashes):
    with open(_source_hashes_path(), 'w', encoding='utf-8') as f:
        json.dump(hashes, f, ensure_ascii=False, indent=2)


def load_source_hashes():
    path = _source_hashes_path()
    if os.path.isfile(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def scan_article_files():
    article_path = Config.ARTICLE_PATH
    if not os.path.isdir(article_path):
        return []

    files = []
    for root, dirs, filenames in os.walk(article_path):
        for name in sorted(filenames):
            if not name.endswith('.md') or name.lower() == 'index.md':
                continue
            filepath = os.path.join(root, name)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                stat = os.stat(filepath)
                files.append({
                    'name': name,
                    'path': filepath,
                    'title': os.path.splitext(name)[0],
                    'hash': compute_hash(content),
                    'size': stat.st_size,
                    'modified': stat.st_mtime,
                    'content': content,
                })
            except (PermissionError, UnicodeDecodeError):
                continue
    return files


def save_concept_page(slug, title, body, summary='', sources=None, kind='concept', confidence=0.0):
    concepts_dir = get_concepts_dir()
    os.makedirs(concepts_dir, exist_ok=True)

    safe_slug = _safe_slug_fn(slug)
    filepath = os.path.join(concepts_dir, safe_slug + '.md')

    frontmatter = {
        'title': title,
        'slug': safe_slug,
        'kind': kind,
        'summary': summary,
        'sources': sources or [],
        'confidence': confidence,
    }

    fm_lines = '---\n'
    fm_lines += json.dumps(frontmatter, ensure_ascii=False, indent=2)
    fm_lines += '\n---\n\n'

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(fm_lines + body)

    return filepath


def read_concept_page(slug):
    concepts_dir = get_concepts_dir()
    safe_slug = _safe_slug_fn(slug)
    filepath = os.path.join(concepts_dir, safe_slug + '.md')

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


def list_concept_pages():
    concepts_dir = get_concepts_dir()
    if not os.path.isdir(concepts_dir):
        return []

    pages = []
    for name in sorted(os.listdir(concepts_dir)):
        if not name.endswith('.md'):
            continue
        page_data = read_concept_page(name[:-3])
        if page_data:
            fm = page_data['frontmatter']
            fm['slug'] = name[:-3]
            fm['body_length'] = len(page_data['body'])
            fm['source'] = 'local'
            pages.append(fm)
    return pages


def list_common_concept_pages():
    """列出公共库概念页（只读，source='common'）"""
    concepts_dir = get_common_concepts_dir()
    if not concepts_dir or not os.path.isdir(concepts_dir):
        return []

    pages = []
    for name in sorted(os.listdir(concepts_dir)):
        if not name.endswith('.md'):
            continue
        filepath = os.path.join(concepts_dir, name)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
        except (PermissionError, UnicodeDecodeError):
            continue

        fm = {}
        body = content
        if content.startswith('---\n'):
            end = content.find('\n---\n', 4)
            if end != -1:
                try:
                    fm = json.loads(content[4:end])
                except json.JSONDecodeError:
                    pass
                body = content[end + 5:].strip()

        fm['slug'] = name[:-3]
        fm['body_length'] = len(body)
        fm['source'] = 'common'
        pages.append(fm)
    return pages


def read_common_concept_page(slug):
    """读取公共库概念页（只读）"""
    concepts_dir = get_common_concepts_dir()
    if not concepts_dir:
        return None

    safe_slug = _safe_slug_fn(slug)
    filepath = os.path.join(concepts_dir, safe_slug + '.md')

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


def delete_concept_page(slug):
    concepts_dir = get_concepts_dir()
    safe_slug = _safe_slug_fn(slug)
    filepath = os.path.join(concepts_dir, safe_slug + '.md')
    if os.path.isfile(filepath):
        os.remove(filepath)
        return True
    return False


def save_query_page(slug, question, answer):
    queries_dir = get_queries_dir()
    os.makedirs(queries_dir, exist_ok=True)

    filepath = os.path.join(queries_dir, slug + '.md')
    content = f'# {question}\n\n{answer}\n'

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    return filepath


def list_query_pages():
    queries_dir = get_queries_dir()
    if not os.path.isdir(queries_dir):
        return []

    queries = []
    for name in sorted(os.listdir(queries_dir)):
        if not name.endswith('.md'):
            continue
        path = os.path.join(queries_dir, name)
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        lines = content.strip().split('\n')
        title = lines[0].lstrip('# ').strip() if lines else name
        queries.append({
            'slug': name[:-3],
            'title': title,
            'file': name,
        })
    return queries


def generate_index():
    pages = list_concept_pages()
    queries = list_query_pages()

    lines = ['# Wiki Index\n']

    if pages:
        lines.append('## Concepts\n')
        for p in pages:
            title = p.get('title', p.get('slug', 'Unknown'))
            summary = p.get('summary', '')
            lines.append(f'- [[{title}]] — {summary}\n' if summary else f'- [[{title}]]\n')
        lines.append('\n')

    if queries:
        lines.append('## Saved Queries\n')
        for q in queries:
            lines.append(f'- {q["title"]}\n')
        lines.append('\n')

    index_path = os.path.join(get_wiki_root(), 'index.md')
    with open(index_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)

    return index_path
