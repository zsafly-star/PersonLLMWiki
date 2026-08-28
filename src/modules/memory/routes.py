"""记忆管理路由（页面 + REST）。

页面：/memory（记忆管理页）
REST：
  GET  /api/memory/list?kind=&status=&limit=&offset=
  POST /api/memory/forget   {slug}          → 软删除（status=revoked）
  POST /api/memory/promote  {slug}          → 转正为文章源并异步编译 Wiki
  POST /api/memory/remember {body, kind}    → 保存 + 更新向量（可选）
"""
import os
import time

from flask import Blueprint, render_template, request

from common.response import success_response, error_response
from modules.memory import storage

memory_bp = Blueprint('memory', __name__, template_folder='templates')


@memory_bp.route('/memory')
def memory_page():
    return render_template('memory.html', active_view='memory')


@memory_bp.route('/api/memory/list', methods=['GET'])
def api_memory_list():
    kind = request.args.get('kind') or None
    status = request.args.get('status') or None

    limit = request.args.get('limit', type=int) or 200
    offset = request.args.get('offset', type=int) or 0
    if limit < 1:
        limit = 200
    if offset < 0:
        offset = 0

    memories = storage.list_memories(kind=kind, status=status, include_body=True)
    total = len(memories)
    items = memories[offset:offset + limit]

    return success_response({
        'items': items,
        'total': total,
        'kind': kind,
        'status': status,
    })


@memory_bp.route('/api/memory/forget', methods=['POST'])
def api_memory_forget():
    data = request.get_json(silent=True) or {}
    slug = data.get('slug')
    if not slug:
        return error_response('slug 必填', 400)

    ok = storage.update_memory_status(slug, 'revoked')
    if not ok:
        return error_response('记忆不存在', 404)

    return success_response(
        {'slug': storage._safe_slug(slug), 'status': 'revoked'},
        '已撤回',
    )


@memory_bp.route('/api/memory/promote', methods=['POST'])
def api_memory_promote():
    data = request.get_json(silent=True) or {}
    slug = data.get('slug')
    if not slug:
        return error_response('slug 必填', 400)

    mem = storage.read_memory(slug)
    if not mem:
        return error_response('记忆不存在', 404)

    if mem.get('frontmatter', {}).get('status') == 'promoted':
        return error_response('已转正，请勿重复操作', 400)

    safe_slug = storage._safe_slug(slug)
    body = mem.get('body', '') or ''

    from modules.mcp.security import resolve_article_path
    rel_path = os.path.join('_promoted', safe_slug + '.md')
    try:
        article_path = resolve_article_path(rel_path)
    except Exception as e:
        return error_response(f'路径校验失败: {e}', 400)

    os.makedirs(os.path.dirname(article_path), exist_ok=True)
    with open(article_path, 'w', encoding='utf-8') as f:
        f.write(body)

    storage.update_memory_status(slug, 'promoted')

    # 异步编译 Wiki（后台线程），产出待审批候选
    compile_status = 'started'
    try:
        from modules.wiki.compiler.pipeline import compile_wiki
        from app import app
        compile_wiki(app, incremental=True)
    except Exception:
        compile_status = 'failed'

    return success_response(
        {
            'status': 'promoted',
            'article_path': article_path,
            'compile': compile_status,
        },
        '已转正，编译产出待审批',
    )


@memory_bp.route('/api/memory/remember', methods=['POST'])
def api_memory_remember():
    data = request.get_json(silent=True) or {}
    body = data.get('body')
    if not body:
        return error_response('body 必填', 400)

    kind = data.get('kind') or 'other'
    slug = data.get('slug')

    path = storage.save_memory(slug or ('manual_' + str(int(time.time()))),
                               body, kind=kind, status='auto')

    safe_slug = storage._safe_slug(slug) if slug else os.path.splitext(os.path.basename(path))[0]

    try:
        from modules.memory.retrieval import update_memory_embedding
        update_memory_embedding(safe_slug)
    except Exception:
        pass

    return success_response(
        {'slug': safe_slug, 'path': path, 'kind': kind, 'status': 'auto'},
        '已记住',
    )
