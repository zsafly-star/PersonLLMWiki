"""MCP 只读工具 handlers（Tier 1，无成本）。

list_folders / read_note 直接读文件系统，不消耗任何外部 API。
list_wiki_pages / read_wiki_page 接 WikiPage 模型 + wiki_service 文件系统回退。
"""
import json
import os

from flask import current_app

from .errors import INVALID_PARAMS, MCPError
from .security import resolve_article_path
from .tools_common import text_content, error_content


def handle_list_folders(args: dict) -> dict:
    """列出 PersonLLMWiki 文章知识库的顶层目录结构。

    Args:
        args: {} 或 {depth: int}（当前只支持 depth=1）

    Returns:
        [{name, path, icon?, note_count?}]
    """
    article_root = current_app.config['ARTICLE_PATH']

    folders = []
    try:
        entries = sorted(os.listdir(article_root))
    except (FileNotFoundError, PermissionError):
        return text_content([])

    for entry in entries:
        entry_path = os.path.join(article_root, entry)
        if not os.path.isdir(entry_path):
            continue
        # 跳过隐藏目录（.zsnote.json 之类元数据）
        if entry.startswith('.'):
            continue

        item = {
            'name': entry,
            'path': entry,
        }

        # 读取文件夹图标（如果有 .zsnote.json）
        meta_path = os.path.join(entry_path, '.zsnote.json')
        if os.path.isfile(meta_path):
            try:
                with open(meta_path, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                if 'icon' in meta:
                    item['icon'] = meta['icon']
            except (json.JSONDecodeError, OSError):
                pass

        # 统计该目录下 md 文件数
        try:
            note_count = sum(
                1 for e in os.listdir(entry_path)
                if e.endswith('.md') and e.lower() != 'index.md'
                and os.path.isfile(os.path.join(entry_path, e))
            )
            item['note_count'] = note_count
        except (PermissionError, FileNotFoundError):
            item['note_count'] = 0

        folders.append(item)

    return text_content(folders)


def handle_read_note(args: dict) -> dict:
    """文章读写工具（读写 article/*.md），与已删除的「笔记」模块无关。

    按路径读取一篇文章。

    Args:
        args: {path: str (required), full: bool (default false)}

    Returns:
        {title, summary, word_count, updated_at, content?}

    Raises:
        MCPError(-32602): path 缺失或越界
    """
    if 'path' not in args or not args['path']:
        raise MCPError(INVALID_PARAMS, 'path 参数必填')

    full = bool(args.get('full', False))

    # 路径安全校验
    abs_path = resolve_article_path(args['path'])

    if not os.path.isfile(abs_path):
        return error_content(f'文件不存在: {args["path"]}')

    try:
        with open(abs_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except (PermissionError, UnicodeDecodeError) as e:
        return error_content(f'读取失败: {e}')

    # 解析标题：第一行 # xxx
    lines = content.split('\n')
    title = os.path.splitext(os.path.basename(args['path']))[0]
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('# '):
            title = stripped[2:].strip()
            break
        elif stripped and not stripped.startswith('#'):
            break

    word_count = len(content)
    # 摘要：第二段非空文本前 100 字
    summary = ''
    found_first_heading = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith('#'):
            found_first_heading = True
            continue
        if found_first_heading or not title:
            summary = stripped[:100]
            break
    if not summary:
        summary = content[:100]

    stat = os.stat(abs_path)
    updated_at = stat.st_mtime

    data = {
        'title': title,
        'summary': summary,
        'word_count': word_count,
        'updated_at': updated_at,
    }
    if full:
        from .image_extractor import strip_inline_images
        data['content'] = strip_inline_images(content)

    return text_content(data)


# ---------- Wiki 概念页面 ----------

def handle_list_wiki_pages(args: dict) -> dict:
    """列出已审批的 Wiki 概念页面。

    Args:
        args: {limit: int (default 50), offset: int (default 0)}

    Returns:
        [{slug, title, updated_at?, source_count}]
    """
    limit = args.get('limit', 50)
    offset = args.get('offset', 0)
    # 防御性边界
    if not isinstance(limit, int) or limit < 1:
        limit = 50
    if not isinstance(offset, int) or offset < 0:
        offset = 0
    limit = min(limit, 200)  # 硬上限

    from modules.wiki.models import WikiPage

    pages = (
        WikiPage.query
        .filter(WikiPage.review_status.in_(['approved', 'chat']))
        .order_by(WikiPage.updated_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    result = []
    for p in pages:
        import json as _json
        sources = _json.loads(p.sources) if p.sources else []
        result.append({
            'slug': p.slug,
            'title': p.title,
            'updated_at': p.updated_at.isoformat() if p.updated_at else None,
            'source_count': len(sources),
        })

    # DB 空时回退到文件系统（与现有 routes.py 行为一致）
    if not result and offset == 0:
        try:
            from modules.wiki import wiki_service
            file_pages = wiki_service.list_concept_pages()
            for fm in file_pages:
                result.append({
                    'slug': fm.get('slug', ''),
                    'title': fm.get('title', fm.get('slug', '')),
                    'updated_at': None,
                    'source_count': len(fm.get('sources', [])),
                })
        except Exception:
            pass

    return text_content(result)


def handle_read_wiki_page(args: dict) -> dict:
    """读取单个 Wiki 概念页面正文（含来源溯源）。

    Args:
        args: {slug: str (required)}

    Returns:
        {slug, title, content, sources: [{file, lines?}]}

    Raises:
        MCPError(-32602): slug 缺失
    """
    if 'slug' not in args or not args['slug']:
        raise MCPError(INVALID_PARAMS, 'slug 参数必填')

    slug = args['slug']

    from modules.wiki.models import WikiPage
    page = WikiPage.query.filter_by(slug=slug).first()

    # 优先用 DB 的元数据
    if page:
        import json as _json
        sources = _json.loads(page.sources) if page.sources else []
        # body 优先从文件系统读（与 routes.py 一致：DB 存的是生成时的快照）
        content = page.body or ''
        try:
            from modules.wiki import wiki_service
            file_data = wiki_service.read_concept_page(slug)
            if file_data:
                content = file_data['body']
        except Exception:
            pass

        from .image_extractor import strip_inline_images

        return text_content({
            'slug': slug,
            'title': page.title,
            'summary': page.summary or '',
            'content': strip_inline_images(content),
            'sources': sources,
            'updated_at': page.updated_at.isoformat() if page.updated_at else None,
        })

    # DB 没有 → 回退到文件系统
    try:
        from modules.wiki import wiki_service
        file_data = wiki_service.read_concept_page(slug)
    except Exception as e:
        return error_content(f'读取失败: {e}')

    if not file_data:
        return error_content(f'Wiki 页面不存在: {slug}')

    fm = file_data.get('frontmatter', {})
    from .image_extractor import strip_inline_images
    return text_content({
        'slug': slug,
        'title': fm.get('title', slug),
        'summary': fm.get('summary', ''),
        'content': strip_inline_images(file_data.get('body', '')),
        'sources': fm.get('sources', []),
        'updated_at': None,
    })


# ---------- 编译状态 ----------

def handle_get_compile_status(args: dict) -> dict:
    """查询当前 Wiki 编译进度。无成本。

    用于轮询 compile_wiki 的结果，替代 SSE 推送。

    Args:
        args: {}

    Returns:
        {running, progress, total, completed, errors: []}
    """
    from modules.wiki.compiler.pipeline import get_compile_status
    status = get_compile_status()
    return text_content(status)


# ---------- 候选审批 ----------

def handle_list_candidates(args: dict) -> dict:
    """列出待审批的 Wiki 候选页面。无成本。

    Args:
        args: {limit: int (default 20)}

    Returns:
        [{id, slug, title, source_file, preview}]
    """
    limit = args.get('limit', 20)
    if not isinstance(limit, int) or limit < 1:
        limit = 20
    limit = min(limit, 100)

    from modules.wiki.models import WikiPage

    pages = (
        WikiPage.query
        .filter_by(review_status='pending')
        .order_by(WikiPage.created_at.desc())
        .limit(limit)
        .all()
    )

    result = []
    for p in pages:
        import json as _json
        sources = _json.loads(p.sources) if p.sources else []
        source_file = sources[0].get('file', '') if sources else ''
        preview = (p.body or '')[:200]
        result.append({
            'id': p.id,
            'slug': p.slug,
            'title': p.title,
            'source_file': source_file,
            'preview': preview,
        })

    return text_content(result)


# ---------- 知识星链图谱 ----------

# 设计方案 6 Tier1：全图节点硬上限 80
_GRAPH_NODE_HARD_CAP = 80


def handle_get_graph(args: dict) -> dict:
    """获取知识星链图谱数据。

    无 seed 返回全图（硬上限 80 节点）；
    有 seed 返回该概念的局部邻居。

    Args:
        args: {seed?: str, depth: int (default 1, max 2)}

    Returns:
        {nodes: [{id, title, size}], edges: [{source, target}]}
    """
    seed = args.get('seed')
    depth = args.get('depth', 1)
    if not isinstance(depth, int) or depth < 1:
        depth = 1
    depth = min(depth, 2)

    from modules.wiki.models import WikiPage
    from modules.wiki.graph_builder import build_adjacency

    pages = WikiPage.query.filter(
        WikiPage.review_status.in_(['approved', 'chat'])
    ).all()

    if not pages:
        return text_content({'nodes': [], 'edges': []})

    # 构建 slug → 页面 映射 + 邻接表（复用 graph_builder 避免双端点漂移）
    slug_to_page = {p.slug: p for p in pages}
    adjacency, slug_title_map = build_adjacency(pages)

    # 记忆节点（只读合并，计入预算）
    from modules.memory.graph import collect_memory_nodes, build_memory_edges
    mem_nodes = collect_memory_nodes()
    mem_edges = build_memory_edges(mem_nodes, set(slug_to_page.keys()))

    if seed:
        # seed 模式：优先匹配 wiki（原 BFS 行为）
        seed_slug = None
        for s, title in slug_title_map.items():
            if seed in title or title in seed or seed == s:
                seed_slug = s
                break

        if seed_slug:
            visited = {seed_slug}
            frontier = {seed_slug}
            for _ in range(depth):
                next_frontier = set()
                for node in frontier:
                    for neighbor in adjacency.get(node, set()):
                        if neighbor not in visited:
                            visited.add(neighbor)
                            next_frontier.add(neighbor)
                frontier = next_frontier
                if not frontier:
                    break

            nodes = []
            for slug in visited:
                page = slug_to_page.get(slug)
                if page:
                    nodes.append({
                        'id': slug,
                        'title': page.title,
                        'size': len(adjacency.get(slug, set())) + 1,
                    })

            edges = []
            added_edges = set()
            for slug in visited:
                for target in adjacency.get(slug, set()):
                    if target in visited:
                        edge_key = tuple(sorted([slug, target]))
                        if edge_key not in added_edges:
                            added_edges.add(edge_key)
                            edges.append({'source': slug, 'target': target})

            return text_content({'nodes': nodes, 'edges': edges})

        # seed 未命中 wiki → 尝试匹配记忆节点
        matched_mem = None
        for n in mem_nodes:
            if seed == n['id'] or seed == n['title'] or seed in n['title'] or n['title'] in seed:
                matched_mem = n
                break

        if not matched_mem:
            return text_content({'nodes': [], 'edges': []})

        mem_id = matched_mem['id']
        neighbor_ids = set()
        for e in mem_edges:
            if e['source'] == mem_id:
                neighbor_ids.add(e['target'])
            elif e['target'] == mem_id:
                neighbor_ids.add(e['source'])

        nodes = []
        for n in mem_nodes:
            if n['id'] == mem_id or n['id'] in neighbor_ids:
                nodes.append({'id': n['id'], 'title': n['title'], 'size': n['size']})
        for nid in neighbor_ids:
            page = slug_to_page.get(nid)
            if page:
                nodes.append({
                    'id': nid,
                    'title': page.title,
                    'size': len(adjacency.get(nid, set())) + 1,
                })

        edges = [e for e in mem_edges if e['source'] == mem_id or e['target'] == mem_id]

        return text_content({'nodes': nodes, 'edges': edges})

    # 全图模式：按关联数排序后截断 wiki 到硬上限
    sorted_slugs = sorted(
        pages,
        key=lambda p: len(adjacency.get(p.slug, set())),
        reverse=True,
    )
    included_slugs = {p.slug for p in sorted_slugs[:_GRAPH_NODE_HARD_CAP]}

    wiki_nodes = []
    for slug in included_slugs:
        page = slug_to_page.get(slug)
        if page:
            wiki_nodes.append({
                'id': slug,
                'title': page.title,
                'size': len(adjacency.get(slug, set())) + 1,
            })

    wiki_edges = []
    added_edges = set()
    for slug in included_slugs:
        for target in adjacency.get(slug, set()):
            if target in included_slugs:
                edge_key = tuple(sorted([slug, target]))
                if edge_key not in added_edges:
                    added_edges.add(edge_key)
                    wiki_edges.append({'source': slug, 'target': target})

    mem_node_list = [{'id': n['id'], 'title': n['title'], 'size': n['size']} for n in mem_nodes]

    all_nodes = wiki_nodes + mem_node_list
    all_edges = wiki_edges + list(mem_edges)

    # 硬上限 80：超出则裁掉多余记忆节点（保留 wiki 节点）
    if len(all_nodes) > _GRAPH_NODE_HARD_CAP:
        budget = max(0, _GRAPH_NODE_HARD_CAP - len(wiki_nodes))
        all_nodes = wiki_nodes + mem_node_list[:budget]

    kept_ids = {n['id'] for n in all_nodes}
    all_edges = [e for e in all_edges if e['source'] in kept_ids and e['target'] in kept_ids]

    return text_content({'nodes': all_nodes, 'edges': all_edges})
