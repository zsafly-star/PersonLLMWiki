import os
import json

from flask import Blueprint, request, render_template, current_app, redirect
from config import Config
from common.response import success_response, error_response
from extensions import db
from .models import WikiPage
from .graph_builder import normalize_link
from . import wiki_service
from .compiler import pipeline as wiki_compiler

wiki_bp = Blueprint('wiki', __name__, template_folder='templates')


@wiki_bp.route('/wiki')
def wiki_page():
    return render_template('wiki.html', active_view='wiki')


@wiki_bp.route('/graph')
def graph_page():
    """重定向到 Wiki 页（星链已合并入 Wiki 的「星链」tab）。"""
    return redirect('/wiki', code=301)


@wiki_bp.route('/api/wiki/sources', methods=['GET'])
def get_sources():
    files = wiki_service.scan_article_files()
    compiled_hashes = wiki_service.load_source_hashes()

    for f in files:
        f['status'] = 'compiled' if f['title'] in compiled_hashes and compiled_hashes[f['title']] == f['hash'] else 'pending'
        del f['content']

    return success_response(files)


@wiki_bp.route('/api/wiki/compile', methods=['POST'])
def api_compile_wiki():
    from flask import current_app
    app = current_app._get_current_object()
    data = request.get_json() or {}
    incremental = data.get('incremental', True)
    init = data.get('init', False)
    result = wiki_compiler.compile_wiki(app, incremental=incremental, init=init)
    return success_response(result)


@wiki_bp.route('/api/wiki/status', methods=['GET'])
def get_compile_status():
    status = wiki_compiler.get_compile_status()
    return success_response(status)


@wiki_bp.route('/api/wiki/embeddings/status', methods=['GET'])
def get_embeddings_status():
    """获取向量索引状态"""
    import os
    from .compiler.retrieval import _embeddings_path, _load_embeddings
    from common.embedding_config import EmbeddingConfigService

    path = _embeddings_path()
    embeddings = _load_embeddings()
    emb_config = EmbeddingConfigService.get_dict()

    return success_response({
        'indexed_count': len(embeddings),
        'index_exists': os.path.isfile(path),
        'configured': emb_config is not None and (emb_config.get('is_active') if emb_config else False),
        'model': emb_config.get('model') if emb_config else None,
        'engine': 'api' if (emb_config and emb_config.get('is_active')) else 'none',
    })


@wiki_bp.route('/api/wiki/embeddings/build', methods=['POST'])
def build_embeddings():
    """手动触发向量索引构建（后台异步执行）"""
    import threading
    from flask import current_app
    from .compiler.retrieval import update_page_embeddings

    app = current_app._get_current_object()

    def _build_task(flask_app):
        with flask_app.app_context():
            try:
                total, stale = update_page_embeddings()
                print(f'[embedding] 索引构建完成: {total} 页面, {stale} 已清理')
            except Exception as e:
                print(f'[embedding] 索引构建失败: {e}')

    thread = threading.Thread(target=_build_task, args=(app,), daemon=True)
    thread.start()

    return success_response({'message': '向量索引构建已启动（后台执行）'})


@wiki_bp.route('/api/wiki/pages', methods=['GET'])
def get_pages():
    pages = WikiPage.query.filter(
        WikiPage.review_status.in_(['approved', 'chat'])
    ).order_by(WikiPage.updated_at.desc()).all()
    result = []

    if pages:
        for p in pages:
            d = p.to_dict()
            d['source'] = 'local'
            result.append(d)
    else:
        file_pages = wiki_service.list_concept_pages()
        for fm in file_pages:
            result.append({
                'id': 0,
                'title': fm.get('title', fm.get('slug', '')),
                'slug': fm.get('slug', ''),
                'kind': fm.get('kind', 'concept'),
                'summary': fm.get('summary', ''),
                'body': '',
                'sources': fm.get('sources', []),
                'confidence': fm.get('confidence', 0.0),
                'links': [],
                'created_at': None,
                'updated_at': None,
                'source': 'local',
            })

    # 合并公共库页面（只读）
    if Config.INSTANCE_MODE == 'personal' and Config.COMMON_RESOURCE_PATH:
        common_pages = wiki_service.list_common_concept_pages()
        local_slugs = {p['slug'] for p in result}
        for fm in common_pages:
            if fm.get('slug', '') not in local_slugs:
                result.append({
                    'id': 0,
                    'title': fm.get('title', fm.get('slug', '')),
                    'slug': fm.get('slug', ''),
                    'kind': fm.get('kind', 'concept'),
                    'summary': fm.get('summary', ''),
                    'body': '',
                    'sources': fm.get('sources', []),
                    'confidence': fm.get('confidence', 0.0),
                    'links': [],
                    'created_at': None,
                    'updated_at': None,
                    'source': 'common',
                })

    return success_response(result)


@wiki_bp.route('/api/wiki/pages/<slug>', methods=['GET'])
def get_page(slug):
    page = WikiPage.query.filter_by(slug=slug).first()
    page_dict = None

    if page:
        page_dict = page.to_dict()

    file_data = wiki_service.read_concept_page(slug)
    if file_data:
        if page_dict is None:
            fm = file_data['frontmatter']
            page_dict = {
                'id': 0,
                'title': fm.get('title', slug),
                'slug': slug,
                'kind': fm.get('kind', 'concept'),
                'summary': fm.get('summary', ''),
                'body': file_data['body'],
                'sources': fm.get('sources', []),
                'confidence': fm.get('confidence', 0.0),
                'links': [],
                'created_at': None,
                'updated_at': None,
            }
        else:
            page_dict['body'] = file_data['body']
    elif page_dict is None:
        return error_response('页面不存在', 404)

    return success_response(page_dict)


@wiki_bp.route('/api/wiki/pages/<slug>', methods=['DELETE'])
def delete_page(slug):
    page = WikiPage.query.filter_by(slug=slug).first()
    if not page:
        return error_response('页面不存在', 404)

    wiki_service.delete_concept_page(slug)
    db.session.delete(page)
    db.session.commit()
    return success_response(None, '删除成功')


@wiki_bp.route('/api/wiki/index', methods=['GET'])
def get_index():
    index_path = os.path.join(wiki_service.get_wiki_root(), 'index.md')
    if not os.path.isfile(index_path):
        wiki_service.generate_index()

    if os.path.isfile(index_path):
        with open(index_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return success_response({'content': content})

    return success_response({'content': ''})


@wiki_bp.route('/api/wiki/query', methods=['POST'])
def query_wiki():
    data = request.get_json()
    question = data.get('question', '').strip()
    save = data.get('save', False)

    if not question:
        return error_response('请输入问题')

    try:
        result = wiki_compiler.query_wiki(question, save=save)
        return success_response(result)
    except RuntimeError as e:
        return error_response(str(e))
    except Exception as e:
        return error_response(f'查询失败: {str(e)}')


@wiki_bp.route('/api/wiki/queries', methods=['GET'])
def get_queries():
    queries = wiki_service.list_query_pages()
    return success_response(queries)


@wiki_bp.route('/api/wiki/analyze', methods=['POST'])
def analyze_concept():
    """概念卡「用智能体深入分析」：经 dsh_bridge 调 DSH headless。

    Body: {slug: str}
    结果展示在 PersonLLMWiki 侧（详情弹层），需继续交互时再切到 DSH 模式。
    """
    data = request.get_json(silent=True) or {}
    slug = (data.get('slug') or '').strip()
    if not slug:
        return error_response('slug 必填', 400)

    # 解析概念标题（优先 DB，回退概念页 frontmatter）
    title = slug
    page = WikiPage.query.filter_by(slug=slug).first()
    if page:
        title = page.title
    else:
        fd = wiki_service.read_concept_page(slug)
        if fd:
            title = fd['frontmatter'].get('title', slug)

    from common import dsh_bridge
    result = dsh_bridge.run_headless(f'分析概念 {title}')
    if not result.get('success'):
        return error_response(result.get('error') or 'DSH 深入分析失败', 502)

    return success_response({'title': title, 'output': result.get('output', '')}, '深入分析完成')


@wiki_bp.route('/api/wiki/graph', methods=['GET'])
def get_graph():
    def _merge_memory(nodes, edges, slug_set):
        from modules.memory.graph import collect_memory_nodes, build_memory_edges
        mem_nodes = collect_memory_nodes()
        for n in mem_nodes:
            nodes.append({'id': n['id'], 'label': n['title'], 'kind': 'memory', 'size': n['size'], 'source': 'local'})
        edges.extend(build_memory_edges(mem_nodes, slug_set))

    pages = WikiPage.query.filter(
        WikiPage.review_status.in_(['approved', 'chat'])
    ).all()

    if not pages:
        file_pages = wiki_service.list_concept_pages()
        nodes = []
        edges = []
        slug_set = set()
        slug_title_map = {}

        for fm in file_pages:
            slug = fm.get('slug', '')
            title = fm.get('title', slug)
            slug_set.add(slug)
            slug_title_map[slug] = title
            nodes.append({
                'id': slug,
                'label': title,
                'kind': fm.get('kind', 'concept'),
                'size': 1,
                'source': 'local',
            })

        # 合并公共库节点（只读，source='common'）
        if Config.INSTANCE_MODE == 'personal' and Config.COMMON_RESOURCE_PATH:
            common_pages = wiki_service.list_common_concept_pages()
            for fm in common_pages:
                slug = fm.get('slug', '')
                if slug in slug_set:
                    continue
                title = fm.get('title', slug)
                slug_set.add(slug)
                slug_title_map[slug] = title
                nodes.append({
                    'id': slug,
                    'label': title,
                    'kind': fm.get('kind', 'concept'),
                    'size': 1,
                    'source': 'common',
                })

        _merge_memory(nodes, edges, slug_set)
        return success_response({'nodes': nodes, 'edges': edges})

    nodes = []
    edges = []
    slug_set = set()
    slug_title_map = {}

    for p in pages:
        pd = p.to_dict()
        slug_set.add(pd['slug'])
        slug_title_map[pd['slug']] = pd['title']
        nodes.append({
            'id': pd['slug'],
            'label': pd['title'],
            'kind': pd.get('kind', 'concept'),
            'size': len(pd.get('links', [])) + 1,
            'source': 'local',
        })

    added_edges = set()
    for p in pages:
        pd = p.to_dict()
        for link in pd.get('links', []):
            matched_slug = normalize_link(link, slug_set, slug_title_map)

            if matched_slug:
                edge_key = f"{pd['slug']}->{matched_slug}"
                if edge_key not in added_edges:
                    added_edges.add(edge_key)
                    edges.append({
                        'source': pd['slug'],
                        'target': matched_slug,
                    })

    _merge_memory(nodes, edges, slug_set)
    return success_response({'nodes': nodes, 'edges': edges})


@wiki_bp.route('/api/wiki/candidates', methods=['GET'])
def get_candidates():
    candidates = WikiPage.query.filter_by(review_status='pending').order_by(WikiPage.created_at.desc()).all()
    return success_response([c.to_dict() for c in candidates])


@wiki_bp.route('/api/wiki/candidates/<int:page_id>/approve', methods=['POST'])
def approve_candidate(page_id):
    page = WikiPage.query.get(page_id)
    if not page or page.review_status != 'pending':
        return error_response('候选页面不存在', 404)

    page.review_status = 'approved'
    db.session.commit()
    wiki_service.generate_index()

    import threading
    app_ref = current_app._get_current_object()
    def _bg():
        with app_ref.app_context():
            try:
                from .compiler.retrieval import update_page_embeddings
                update_page_embeddings()
            except Exception:
                pass
    t = threading.Thread(target=_bg, daemon=True)
    t.start()

    return success_response(page.to_dict(), '审批通过')


@wiki_bp.route('/api/wiki/candidates/<int:page_id>/reject', methods=['DELETE'])
def reject_candidate(page_id):
    page = WikiPage.query.get(page_id)
    if not page or page.review_status != 'pending':
        return error_response('候选页面不存在', 404)

    slug = page.slug
    wiki_service.delete_concept_page(slug)
    db.session.delete(page)
    db.session.commit()

    return success_response(None, '已拒绝')


# ────────────────── Phase 2: 公共库同步 ──────────────────

@wiki_bp.route('/api/wiki/sync/status', methods=['GET'])
def get_sync_status():
    from common.sync_service import get_sync_status as _get_status, is_common_enabled
    return success_response({
        **_get_status(),
        'enabled': is_common_enabled(),
        'instance_mode': Config.INSTANCE_MODE,
    })


@wiki_bp.route('/api/wiki/sync', methods=['POST'])
def trigger_sync():
    from common.sync_service import sync_common_library_async
    result = sync_common_library_async()
    if result['success']:
        return success_response(result, result['message'])
    return error_response(result['message'], 400)


# ────────────────── Phase 3: 知识贡献 ──────────────────

@wiki_bp.route('/api/wiki/submit', methods=['POST'])
def submit_to_public():
    """个人实例提交知识到公共库。

    前端传入 slug（本地概念页标识），后端读取本地页面，
    通过 HTTP JSON-RPC 调用公共实例的 submit_to_public MCP 工具。
    """
    data = request.get_json(silent=True) or {}
    slug = data.get('slug')
    if not slug:
        return error_response('slug 必填', 400)

    # 读取本地概念页
    page_data = wiki_service.read_concept_page(slug)
    if not page_data:
        return error_response(f'本地概念页不存在: {slug}', 404)

    fm = page_data['frontmatter']
    body = page_data['body']

    # 构造提交参数
    submit_args = {
        'title': fm.get('title', slug),
        'body': body,
        'summary': fm.get('summary', ''),
        'sources': fm.get('sources', []),
        'kind': fm.get('kind', 'concept'),
    }

    # 调用公共实例 MCP
    import requests as req
    public_url = Config.COMMON_GIT_REPO  # 暂用 Git repo URL 做标识，实际需配置公共实例 API 地址
    public_api = os.environ.get('PUBLIC_MCP_URL', '')
    submitter_token = Config.MCP_SUBMITTER_TOKEN

    if not public_api:
        return error_response('未配置 PUBLIC_MCP_URL（公共实例 MCP 端点）', 400)

    headers = {'Content-Type': 'application/json'}
    if submitter_token:
        headers['Authorization'] = f'Bearer {submitter_token}'

    rpc_payload = {
        'jsonrpc': '2.0',
        'method': 'tools/call',
        'params': {
            'name': 'submit_to_public',
            'arguments': submit_args,
        },
        'id': 1,
    }

    try:
        resp = req.post(public_api, json=rpc_payload, headers=headers, timeout=30)
        result = resp.json()

        if 'error' in result:
            return error_response(f'公共实例拒绝: {result["error"].get("message", "")}', 400)

        return success_response(result.get('result'), '已提交到公共库审批队列')

    except req.exceptions.ConnectionError:
        return error_response('无法连接公共实例', 503)
    except Exception as e:
        return error_response(f'提交失败: {str(e)}', 500)


# ────────────────── SAP 物料批量导入 ──────────────────

@wiki_bp.route('/api/wiki/import-sap', methods=['POST'])
def import_sap_materials():
    """从 SAP MCP 的 SQLite 导入物料数据到 Wiki。

    Body:
        {db_path: str, batch: int (optional), dry_run: bool (optional)}
    """
    data = request.get_json(silent=True) or {}
    db_path = data.get('db_path', '')

    # 默认路径：尝试 SAP MCP 的标准位置
    if not db_path:
        import os
        default = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))))), '..', 'MCP', 'sap', 'data', 'materials.db')
        default = os.path.normpath(default)
        if os.path.isfile(default):
            db_path = default

    if not db_path or not os.path.isfile(db_path):
        return error_response('未找到 SAP MCP 数据库，请指定 db_path', 400)

    from common.import_sap_materials import import_materials_from_sap_db
    result = import_materials_from_sap_db(
        db_path,
        batch_size=data.get('batch'),
        dry_run=data.get('dry_run', False),
    )

    if 'error' in result:
        return error_response(result['error'], 400)

    return success_response(result, f"导入完成：{result.get('imported', 0)} 新增，{result.get('skipped', 0)} 跳过")
