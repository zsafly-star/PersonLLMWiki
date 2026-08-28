"""记忆语义检索（独立向量索引，与 wiki 检索隔离）。

向量索引文件：memories/memories_embeddings.json
复用 wiki 的公开 Embedding 函数，余弦相似度本地实现。
所有涉及 Embedding 的函数均防御性 try/except，未配置时降级为空。
"""
import os
import json
import hashlib
import logging
import threading
from functools import lru_cache

from config import Config
from modules.memory.storage import list_memories, read_memory, _safe_slug
from modules.wiki.compiler.retrieval import compute_embedding, compute_embedding_batch

_logger = logging.getLogger(__name__)

# 索引文件读写锁：防并发写坏 memories_embeddings.json（对齐 wiki retrieval 的 _embeddings_lock）
_index_lock = threading.Lock()


def _index_path():
    return os.path.join(Config.MEMORIES_DIR, 'memories_embeddings.json')


def _load_index():
    """读索引；异常/不存在返回 {}。"""
    path = _index_path()
    if os.path.isfile(path):
        try:
            with _index_lock:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def _save_index(data):
    path = _index_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with _index_lock:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def _cosine(a, b):
    """本地余弦相似度；长度不等返回 0.0。"""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


@lru_cache(maxsize=128)
def _cached_query_vec(text):
    return compute_embedding(text)


def rebuild_memory_index():
    """全量重建：扫所有 status != revoked 的记忆，批量算向量，写索引。"""
    try:
        memories = [m for m in list_memories() if m.get('status') != 'revoked']
        if not memories:
            _save_index({})
            return 0

        index = {}
        to_embed = []
        for m in memories:
            slug = m.get('slug')
            if not slug:
                continue
            data = read_memory(slug)
            if not data:
                continue
            body = data.get('body', '')
            content_hash = hashlib.sha256(body.encode('utf-8')).hexdigest()
            index[slug] = {
                'vector': [],
                'hash': content_hash,
                'kind': m.get('kind', 'other'),
                'title': slug,
            }
            to_embed.append((slug, body))

        if to_embed:
            try:
                vectors = compute_embedding_batch([b for _, b in to_embed])
            except Exception as e:
                _logger.warning('Embedding 批量计算失败: %s', e)
                vectors = None
            if vectors and len(vectors) == len(to_embed):
                for i, (slug, _b) in enumerate(to_embed):
                    index[slug]['vector'] = vectors[i]

        _save_index(index)
        return len(index)
    except Exception as e:
        _logger.warning('重建记忆索引失败: %s', e)
        return 0


def update_memory_embedding(slug):
    """增量更新单条记忆向量；记忆不存在或 revoked 时从索引删除。失败打日志不抛。"""
    try:
        safe_slug = _safe_slug(slug)
        index = _load_index()

        data = read_memory(slug)
        if not data or data['frontmatter'].get('status') == 'revoked':
            if safe_slug in index:
                del index[safe_slug]
                _save_index(index)
            return

        body = data.get('body', '')
        content_hash = hashlib.sha256(body.encode('utf-8')).hexdigest()

        existing = index.get(safe_slug)
        if existing and existing.get('hash') == content_hash and existing.get('vector'):
            return

        vec = compute_embedding(body)
        index[safe_slug] = {
            'vector': vec,
            'hash': content_hash,
            'kind': data['frontmatter'].get('kind', 'other'),
            'title': safe_slug,
        }
        _save_index(index)
    except Exception as e:
        _logger.warning('更新记忆向量失败（slug=%s）: %s', slug, e)


def search_memory(query, top_k=5, kind=None):
    """懒建索引 → 余弦检索 → 过滤 revoked → 返回 top 结果。失败返回 []。"""
    try:
        index = _load_index()
        if not index:
            if list_memories():
                rebuild_memory_index()
                index = _load_index()

        if not index:
            return []

        # 过滤 revoked（依据当前文件系统状态，而非索引快照）
        active_slugs = {m.get('slug') for m in list_memories() if m.get('status') != 'revoked'}

        query_vec = _cached_query_vec(query)

        scored = []
        for slug, data in index.items():
            if slug not in active_slugs:
                continue
            if 'vector' not in data or not data['vector']:
                continue
            k = data.get('kind', 'other')
            if kind is not None and k != kind:
                continue
            sim = _cosine(query_vec, data['vector'])
            weight = 1.1 if k in ('preference', 'fact') else 1.0
            scored.append((slug, k, sim * weight))

        scored.sort(key=lambda x: x[2], reverse=True)

        results = []
        for slug, k, score in scored[:top_k]:
            if score <= 0:
                continue
            data = read_memory(slug)
            body = data.get('body', '') if data else ''
            results.append({
                'slug': slug,
                'kind': k,
                'score': round(score, 4),
                'body': body[:200],
            })
        return results
    except Exception:
        return []
