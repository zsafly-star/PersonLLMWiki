"""MCP 检索工具 handlers（Tier 2，消耗 OpenAI Embedding）。

search_kb 接 retrieval.hybrid_search（向量 0.7 + BM25 0.3）。
每次调用都会消耗 Embedding API 配额。
"""
import json

from .errors import INVALID_PARAMS, MCPError


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


def handle_search_kb(args: dict) -> dict:
    """语义检索知识库。

    Args:
        args: {query: str (required), top_k: int (default 5, max 10)}

    Returns:
        [{slug, title, snippet, score, source_type, source}]

    Raises:
        MCPError(-32602): query 缺失或为空
    """
    if 'query' not in args or not isinstance(args.get('query'), str):
        raise MCPError(INVALID_PARAMS, 'query 参数必填且必须是字符串')

    query = args['query'].strip()
    if not query:
        raise MCPError(INVALID_PARAMS, 'query 不能为空')

    top_k = args.get('top_k', 5)
    if not isinstance(top_k, int) or top_k < 1:
        top_k = 5
    top_k = min(top_k, 10)  # 硬上限

    # ── Step 1: 本地检索 ──
    try:
        from modules.wiki.compiler.retrieval import hybrid_search
        local_results = hybrid_search(query, top_k=top_k)
    except Exception as e:
        return _error_content(
            f'检索失败: {e}（注意：本次可能已消耗部分 OpenAI Embedding 配额）'
        )

    # 加载本地页面正文做 snippet
    from modules.wiki.models import WikiPage
    slug_to_page = {p.slug: p for p in WikiPage.query.all()}

    output = []
    seen_slugs = set()

    for slug, title, score in local_results:
        page = slug_to_page.get(slug)
        snippet = ''

        if page:
            body = page.body or ''
            query_terms = query.lower().split()
            paragraphs = body.split('\n\n')
            best_para = ''
            for para in paragraphs:
                lower = para.lower()
                if any(term in lower for term in query_terms):
                    best_para = para
                    break
            if not best_para and paragraphs:
                best_para = paragraphs[0]
            snippet = best_para[:200]
        else:
            try:
                from modules.wiki import wiki_service
                file_data = wiki_service.read_concept_page(slug)
                if file_data:
                    snippet = file_data.get('body', '')[:200]
            except Exception:
                pass

        output.append({
            'slug': slug,
            'title': title,
            'snippet': snippet,
            'score': round(float(score), 4),
            'source_type': 'wiki',
            'source': 'local',
        })
        seen_slugs.add(slug)

    # ── Step 2: 公共库检索（personal 模式，关键词匹配） ──
    try:
        from config import Config
        if Config.INSTANCE_MODE == 'personal' and Config.COMMON_RESOURCE_PATH:
            from modules.wiki.wiki_service import list_common_concept_pages, read_common_concept_page
            common_pages = list_common_concept_pages()
            query_lower = query.lower()
            common_hits = []

            for cp in common_pages:
                slug = cp.get('slug', '')
                if slug in seen_slugs:
                    continue
                title = cp.get('title', '')
                # 简单关键词匹配
                title_lower = title.lower()
                if query_lower in title_lower or any(w in title_lower for w in query_lower.split()):
                    common_hits.append((slug, title, 0.5))
                else:
                    # 也搜索正文
                    try:
                        page_data = read_common_concept_page(slug)
                        if page_data:
                            body_lower = (page_data.get('body', '') or '').lower()
                            if query_lower in body_lower or any(w in body_lower for w in query_lower.split()):
                                common_hits.append((slug, title, 0.3))
                    except Exception:
                        pass

            # 按分数排序，取 top_k
            common_hits.sort(key=lambda x: -x[2])
            for slug, title, score in common_hits[:top_k]:
                snippet = ''
                try:
                    page_data = read_common_concept_page(slug)
                    if page_data:
                        snippet = (page_data.get('body', '') or '')[:200]
                except Exception:
                    pass
                output.append({
                    'slug': slug,
                    'title': title,
                    'snippet': snippet,
                    'score': round(float(score), 4),
                    'source_type': 'wiki',
                    'source': 'common',
                })
    except Exception:
        pass

    if not output:
        return _text_content([])

    return _text_content(output)
