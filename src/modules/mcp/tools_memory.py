"""MCP 记忆工具 handlers（记忆轨，独立于知识库）。"""
import time

from .errors import INVALID_PARAMS, MCPError
from .tools_common import text_content, error_content


_MEMORY_KINDS = ('preference', 'fact', 'decision', 'other')


def handle_search_memory(args: dict) -> dict:
    """语义检索记忆。{query, top_k=5, kind=None}"""
    if 'query' not in args or not isinstance(args.get('query'), str):
        raise MCPError(INVALID_PARAMS, 'query 参数必填且必须是字符串')

    query = args['query'].strip()
    if not query:
        raise MCPError(INVALID_PARAMS, 'query 不能为空')

    top_k = args.get('top_k', 5)
    if not isinstance(top_k, int) or top_k < 1:
        top_k = 5
    top_k = min(top_k, 10)

    kind = args.get('kind')

    from modules.memory.retrieval import search_memory
    return text_content(search_memory(query, top_k=top_k, kind=kind))


def handle_list_memories(args: dict) -> dict:
    """列出记忆。{kind=None, status=None, limit=50, offset=0}"""
    kind = args.get('kind')
    status = args.get('status')

    limit = args.get('limit', 50)
    offset = args.get('offset', 0)
    if not isinstance(limit, int) or limit < 1:
        limit = 50
    if not isinstance(offset, int) or offset < 0:
        offset = 0
    limit = min(limit, 200)

    from modules.memory.storage import list_memories
    memories = list_memories(kind=kind, status=status)
    return text_content(memories[offset:offset + limit])


def handle_remember(args: dict) -> dict:
    """记住一条记忆。{body, kind, slug=None}"""
    if 'body' not in args or not args['body']:
        raise MCPError(INVALID_PARAMS, 'body 参数必填')

    kind = args.get('kind')
    if kind not in _MEMORY_KINDS:
        raise MCPError(INVALID_PARAMS, 'kind 必须是 preference/fact/decision/other 之一')

    slug = args.get('slug')
    if not slug:
        slug = 'manual_' + str(int(time.time()))

    from modules.memory.storage import save_memory, _safe_slug
    from modules.memory.retrieval import update_memory_embedding

    path = save_memory(slug, args['body'], kind=kind, status='auto')
    safe_slug = _safe_slug(slug)
    update_memory_embedding(safe_slug)

    return text_content({'slug': safe_slug, 'path': path, 'kind': kind, 'status': 'auto'})


def handle_settle_memory(args: dict) -> dict:
    """批量沉降记忆到自动记忆轨。{items: [{body, kind, source?}]}"""
    items = args.get('items')
    if not isinstance(items, list) or not items:
        raise MCPError(INVALID_PARAMS, 'items 必须是包含 {body, kind} 的非空列表')

    from modules.memory.settle import settle_memories
    return text_content(settle_memories(items, source='mcp_settle'))


def handle_stage_memory_signals(args: dict) -> dict:
    """暂存记忆信号（卫生过滤后入 _raw/pending.jsonl）。{items: [{body, kind?, source?}]}"""
    items = args.get('items')
    if not isinstance(items, list) or not items:
        raise MCPError(INVALID_PARAMS, 'items 必须是包含 {body} 的非空列表')

    from modules.memory.settle import stage_memory_signals
    return text_content(stage_memory_signals(items, source='mcp_signal'))


def handle_forget_memory(args: dict) -> dict:
    """撤回一条记忆（软删除，物理保留）。"""
    if 'slug' not in args or not args['slug']:
        raise MCPError(INVALID_PARAMS, 'slug 参数必填')

    from modules.memory.storage import update_memory_status

    ok = update_memory_status(args['slug'], 'revoked')
    if not ok:
        return error_content(f'记忆不存在: {args["slug"]}')

    return text_content({'slug': args['slug'], 'status': 'revoked'})
