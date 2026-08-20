"""MCP 只读工具 handlers（Tier 1，无成本）。

list_folders / read_note 直接读文件系统，不消耗任何外部 API。
list_wiki_pages / read_wiki_page 接 WikiPage 模型 + wiki_service 文件系统回退。
"""
import json
import os

from flask import current_app

from .errors import INVALID_PARAMS, MCPError
from .security import resolve_article_path


def _text_content(obj):
    """把 dict/str 包成 MCP content 响应。"""
    if isinstance(obj, str):
        text = obj
    else:
        text = json.dumps(obj, ensure_ascii=False)
    return {'content': [{'type': 'text', 'text': text}]}


def _error_content(message: str):
    """构造 isError=true 的工具错误响应。"""
    return {
        'isError': True,
        'content': [{'type': 'text', 'text': message}],
    }


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
        return _text_content([])

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

    return _text_content(folders)


def handle_read_note(args: dict) -> dict:
    """按路径读取一篇文章。

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
        return _error_content(f'文件不存在: {args["path"]}')

    try:
        with open(abs_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except (PermissionError, UnicodeDecodeError) as e:
        return _error_content(f'读取失败: {e}')

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

    return _text_content(data)


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

    return _text_content(result)


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

        return _text_content({
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
        return _error_content(f'读取失败: {e}')

    if not file_data:
        return _error_content(f'Wiki 页面不存在: {slug}')

    fm = file_data.get('frontmatter', {})
    from .image_extractor import strip_inline_images
    return _text_content({
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
    return _text_content(status)


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

    return _text_content(result)


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

    pages = WikiPage.query.filter(
        WikiPage.review_status.in_(['approved', 'chat'])
    ).all()

    if not pages:
        return _text_content({'nodes': [], 'edges': []})

    import json as _json

    # 构建 slug → 页面 映射
    slug_to_page = {p.slug: p for p in pages}
    slug_title_map = {p.slug: p.title for p in pages}

    # 收集所有 links（规范化为 slug）
    def normalize_link(link_str):
        target = link_str.lower().replace(' ', '_').replace('/', '_')
        if target in slug_to_page:
            return target
        # 模糊匹配：标题包含 / slug 包含
        for s, title in slug_title_map.items():
            if link_str in title or title in link_str:
                return s
        for s in slug_to_page:
            if target in s or s in target:
                return s
        return None

    # 构建邻接表
    adjacency = {p.slug: set() for p in pages}
    for p in pages:
        links = _json.loads(p.links) if p.links else []
        for link in links:
            target_slug = normalize_link(link)
            if target_slug and target_slug != p.slug:
                adjacency[p.slug].add(target_slug)
                # 双向
                if target_slug in adjacency:
                    adjacency[target_slug].add(p.slug)

    if seed:
        # seed 模式：BFS 收集邻居
        seed_slug = None
        for s, title in slug_title_map.items():
            if seed in title or title in seed or seed == s:
                seed_slug = s
                break
        if not seed_slug:
            return _text_content({'nodes': [], 'edges': []})

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

        included_slugs = visited
    else:
        # 全图模式：按关联数排序后截断到硬上限
        sorted_slugs = sorted(
            pages,
            key=lambda p: len(adjacency.get(p.slug, set())),
            reverse=True,
        )
        included_slugs = {p.slug for p in sorted_slugs[:_GRAPH_NODE_HARD_CAP]}

    # 构建节点和边
    nodes = []
    for slug in included_slugs:
        page = slug_to_page.get(slug)
        if page:
            nodes.append({
                'id': slug,
                'title': page.title,
                'size': len(adjacency.get(slug, set())) + 1,
            })

    edges = []
    added_edges = set()
    for slug in included_slugs:
        for target in adjacency.get(slug, set()):
            if target in included_slugs:
                edge_key = tuple(sorted([slug, target]))
                if edge_key not in added_edges:
                    added_edges.add(edge_key)
                    edges.append({'source': slug, 'target': target})

    return _text_content({'nodes': nodes, 'edges': edges})
