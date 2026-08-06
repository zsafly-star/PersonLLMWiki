"""向量检索 + BM25 混合搜索。

向量索引：内存常驻 + query embedding LRU 缓存。
BM25 索引：jieba 中文分词 + rank_bm25（IDF 加权、TF 饱和、文档长度归一化）。
"""

import os
import json
import hashlib
import threading
from functools import lru_cache

import jieba
from rank_bm25 import BM25Okapi

from extensions import db
from ..models import WikiPage
from .. import wiki_service


EMBEDDINGS_FILE = 'embeddings.json'

_embeddings_lock = threading.Lock()
_bm25_lock = threading.Lock()

# 内存常驻缓存
_embeddings_cache = None    # dict: slug -> {vector, hash, title}
_bm25_index = None          # BM25Okapi 实例
_bm25_slug_map = []         # BM25 文档顺序对应的 slug 列表
_bm25_title_map = {}        # slug -> title（避免查 DB）


# ────────────────── Embedding 文件读写 ──────────────────

def _embeddings_path():
    return os.path.join(wiki_service.get_wiki_root(), EMBEDDINGS_FILE)


def _load_embeddings():
    path = _embeddings_path()
    if os.path.isfile(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def _save_embeddings(data):
    path = _embeddings_path()
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _get_embeddings():
    """获取向量索引（内存常驻，首次访问时懒加载）"""
    global _embeddings_cache
    if _embeddings_cache is not None:
        return _embeddings_cache
    _embeddings_cache = _load_embeddings()
    return _embeddings_cache


# ────────────────── Embedding 计算（API 模式） ──────────────────

def _get_embedding_client():
    """从 EmbeddingConfig 获取 OpenAI 兼容 client"""
    from common.embedding_config import EmbeddingConfigService
    config = EmbeddingConfigService.get_active()
    if not config:
        raise RuntimeError('未配置 Embedding API，请在设置页配置')
    if not config.api_key:
        raise RuntimeError('Embedding API Key 未设置')

    import openai
    kwargs = {'api_key': config.api_key}
    if config.base_url:
        kwargs['base_url'] = config.base_url
    return openai.OpenAI(**kwargs), config.model


def compute_embedding(text):
    """使用 Embedding API 计算单段文本的向量"""
    client, model = _get_embedding_client()
    response = client.embeddings.create(model=model, input=text[:8000])
    return response.data[0].embedding


def compute_embedding_batch(texts):
    """批量计算 embedding（索引构建时使用，大幅加速）"""
    client, model = _get_embedding_client()
    # OpenAI API 单次最多 2048 条，分批处理
    results = []
    batch_size = 100
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        response = client.embeddings.create(
            model=model,
            input=[t[:8000] for t in batch],
        )
        results.extend([d.embedding for d in response.data])
    return results


@lru_cache(maxsize=128)
def _cached_query_embedding(query_text):
    """缓存 query embedding，相同查询不重复调 API"""
    return compute_embedding(query_text)


# ────────────────── 余弦相似度 ──────────────────

def _cosine_similarity(a, b):
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ────────────────── BM25 索引 ──────────────────

def _tokenize(text):
    """jieba 中文分词（搜索模式，长词再切短词）"""
    return [t for t in jieba.cut_for_search(text) if t.strip()]


def _rebuild_bm25_from_db():
    """从数据库重建 BM25 索引"""
    global _bm25_index, _bm25_slug_map, _bm25_title_map

    pages = WikiPage.query.all()
    if not pages:
        with _bm25_lock:
            _bm25_index = None
            _bm25_slug_map = []
            _bm25_title_map = {}
        return

    corpus = []
    slug_map = []
    title_map = {}
    for page in pages:
        text = f"{page.title} {page.summary or ''} {page.body or ''}"
        tokens = _tokenize(text)
        corpus.append(tokens)
        slug_map.append(page.slug)
        title_map[page.slug] = page.title

    with _bm25_lock:
        _bm25_index = BM25Okapi(corpus)
        _bm25_slug_map = slug_map
        _bm25_title_map = title_map


def _get_bm25():
    """获取 BM25 索引（内存常驻，首次访问时懒加载）"""
    global _bm25_index
    if _bm25_index is None:
        _rebuild_bm25_from_db()
    return _bm25_index, _bm25_slug_map, _bm25_title_map


def _bm25_search(question, top_k=10):
    """BM25 关键词检索（真 BM25 + jieba 分词，纯内存）"""
    bm25, slug_map, title_map = _get_bm25()
    if bm25 is None or not slug_map:
        return []

    query_tokens = _tokenize(question)
    if not query_tokens:
        return []

    scores = bm25.get_scores(query_tokens)

    ranked = sorted(
        enumerate(scores),
        key=lambda x: x[1],
        reverse=True,
    )[:top_k]

    results = []
    for idx, score in ranked:
        if score <= 0:
            continue
        slug = slug_map[idx]
        results.append((slug, title_map.get(slug, slug), float(score)))

    return results


# ────────────────── 向量检索 ──────────────────

def find_relevant_pages(question, top_k=5):
    """向量语义检索（内存常驻 + query 缓存）"""
    embeddings = _get_embeddings()
    if not embeddings:
        return []

    try:
        question_vec = _cached_query_embedding(question)
    except RuntimeError:
        return []

    scored = []
    for slug, data in embeddings.items():
        if 'vector' not in data:
            continue
        sim = _cosine_similarity(question_vec, data['vector'])
        scored.append((slug, data.get('title', slug), sim))

    scored.sort(key=lambda x: x[2], reverse=True)
    return [(slug, title, score) for slug, title, score in scored[:top_k]]


# ────────────────── 混合检索 ──────────────────

def hybrid_search(question, top_k=5):
    """向量 0.7 + BM25 0.3 混合检索（零 DB 查询）"""
    vector_results = find_relevant_pages(question, top_k=top_k * 2)
    keyword_results = _bm25_search(question, top_k=top_k * 2)

    combined = {}
    for slug, title, score in vector_results:
        combined[slug] = combined.get(slug, 0) + score * 0.7

    max_kw = max((s for _, _, s in keyword_results), default=1) or 1
    for slug, title, score in keyword_results:
        normalized = score / max_kw
        combined[slug] = combined.get(slug, 0) + normalized * 0.3

    ranked = sorted(combined.items(), key=lambda x: x[1], reverse=True)

    slug_title_map = {}
    for slug, title, _ in vector_results + keyword_results:
        slug_title_map[slug] = title

    return [(slug, slug_title_map.get(slug, slug), score) for slug, score in ranked[:top_k]]


# ────────────────── 索引更新（编译后调用）──────────────────

def update_page_embeddings():
    """更新向量索引和 BM25 索引（编译后调用）"""
    global _embeddings_cache

    pages = WikiPage.query.all()

    # --- 向量索引 ---
    embeddings = _load_embeddings()

    # 筛选出需要重新 embed 的页面（新增或内容变更）
    to_embed = []
    for page in pages:
        text_to_embed = f"{page.title} {page.summary or ''} {page.body[:2000] if page.body else ''}"
        content_hash = hashlib.sha256(text_to_embed.encode('utf-8')).hexdigest()

        if page.slug in embeddings and embeddings[page.slug].get('hash') == content_hash:
            continue

        to_embed.append((page.slug, page.title, text_to_embed, content_hash))

    # 批量计算 embedding（比逐条快 10x+）
    if to_embed:
        texts = [item[2] for item in to_embed]
        try:
            vectors = compute_embedding_batch(texts)
        except RuntimeError as e:
            print(f'[embedding] 批量计算失败: {e}')
            vectors = None

        if vectors:
            for i, (slug, title, _, content_hash) in enumerate(to_embed):
                embeddings[slug] = {
                    'vector': vectors[i],
                    'hash': content_hash,
                    'title': title,
                }

    # 清理已删除页面的旧索引
    slugs_in_db = {p.slug for p in pages}
    stale = [s for s in embeddings if s not in slugs_in_db]
    for s in stale:
        del embeddings[s]

    with _embeddings_lock:
        _save_embeddings(embeddings)
        _embeddings_cache = embeddings

    # --- BM25 索引 ---
    _rebuild_bm25_from_db()

    return len(pages), len(stale)
