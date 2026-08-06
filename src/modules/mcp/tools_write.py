"""MCP 写入工具 handlers（Tier 3，变更需谨慎）。

write_note 直接写文件系统，即时生效。路径必须在 article 根目录内。
"""
import json
import os

from flask import current_app

from .errors import INVALID_PARAMS, MCPError
from .security import resolve_article_path, validate_markdown_extension


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


def handle_write_note(args: dict) -> dict:
    """创建或覆盖一篇文章（Markdown）。

    自动提取 Markdown 中的内联 data URI 图片，保存到 resource/img/<文件名>/
    目录下，并将 Markdown 中的引用替换为 ZSSNote 标准相对路径
    img/<文件名>/xxx.png，兼容现有图片查看器和渲染管线。

    Args:
        args: {
            path: str (required),
            content: str (required),
            create_folders: bool (default true),
        }

    Returns:
        {
            path: str,
            word_count: int,
            created: bool,
            images_extracted: int,
            image_paths: list[str],  # 形如 ['img/笔记/xxx.png', ...]
        }

    Raises:
        MCPError(-32602): 参数缺失 / 路径越界 / 扩展名非 .md
    """
    if 'path' not in args or not args['path']:
        raise MCPError(INVALID_PARAMS, 'path 参数必填')
    if 'content' not in args or not isinstance(args['content'], str):
        raise MCPError(INVALID_PARAMS, 'content 参数必填且必须是字符串')

    raw_path = args['path']
    content = args['content']
    create_folders = bool(args.get('create_folders', True))

    # 扩展名白名单校验（先于路径解析）
    validate_markdown_extension(raw_path)

    # 路径安全校验
    abs_path = resolve_article_path(raw_path)

    # 判断是创建还是覆盖
    created = not os.path.exists(abs_path)

    # 父目录处理
    parent_dir = os.path.dirname(abs_path)
    if not os.path.isdir(parent_dir):
        if create_folders:
            os.makedirs(parent_dir, exist_ok=True)
        else:
            raise MCPError(INVALID_PARAMS, f'父目录不存在: {parent_dir}')

    # 提取内联图片（若有）
    md_stem = os.path.splitext(os.path.basename(raw_path))[0]
    img_root = current_app.config['IMAGE_PATH']
    img_dir = os.path.join(img_root, md_stem)

    from .image_extractor import extract_inline_images
    # Markdown 引用路径前缀：img/<文件名>/（ZSSNote 标准）
    md_prefix = f'img/{md_stem}/'
    new_content, saved_paths = extract_inline_images(content, img_dir, md_prefix)

    # 构造 ZSSNote 标准相对路径（img/<文件名>/xxx.png）
    rel_image_paths = []
    for abs_img_path in saved_paths:
        # 取相对于 IMAGE_PATH 的相对路径，再转为正斜杠形式
        rel = os.path.relpath(abs_img_path, img_root)
        rel_image_paths.append(rel.replace('\\', '/'))

    try:
        with open(abs_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
    except (PermissionError, OSError) as e:
        raise MCPError(INVALID_PARAMS, f'写入失败: {e}')

    return _text_content({
        'path': raw_path,
        'word_count': len(new_content),
        'created': created,
        'images_extracted': len(rel_image_paths),
        'image_paths': rel_image_paths,
    })


# ---------- Wiki 编译 ----------

def handle_compile_wiki(args: dict) -> dict:
    """触发 Wiki 知识编译（概念提取→页面生成）。

    消耗 OpenAI LLM 配额。编译产出进入待审批状态，不会自动入库。
    用 get_compile_status 轮询进度。

    Args:
        args: {incremental: bool (default true), init: bool (default false)}

    Returns:
        {started: bool, message: str}
    """
    from flask import current_app

    incremental = bool(args.get('incremental', True))
    init = bool(args.get('init', False))

    app_ref = current_app._get_current_object()

    try:
        from modules.wiki.compiler.pipeline import compile_wiki
        result = compile_wiki(app_ref, incremental=incremental, init=init)
    except Exception as e:
        return {
            'isError': True,
            'content': [{
                'type': 'text',
                'text': f'编译启动失败: {e}（注意：本次可能已消耗部分 OpenAI LLM 配额）',
            }],
        }

    status = result.get('status', '')
    if status == 'already_running':
        return _text_content({
            'started': False,
            'message': '编译已在进行中，用 get_compile_status 查询进度',
        })

    return _text_content({
        'started': True,
        'message': '编译已启动，用 get_compile_status 查询进度',
    })


# ---------- 候选审批 ----------

def handle_approve_candidate(args: dict) -> dict:
    """通过一个候选 Wiki 页面，使其正式入库并加入索引/图谱。

    安全约束：应仅在用户明确要求时调用。LLM 不应自动批量审批。

    Args:
        args: {id: int (required)}

    Returns:
        {id, slug, approved: true}

    Raises:
        MCPError(-32602): id 缺失
    """
    if 'id' not in args:
        raise MCPError(INVALID_PARAMS, 'id 参数必填')

    page_id = args['id']
    if not isinstance(page_id, int) or page_id < 1:
        raise MCPError(INVALID_PARAMS, 'id 必须是正整数')

    from extensions import db
    from modules.wiki.models import WikiPage
    from modules.wiki import wiki_service

    page = db.session.get(WikiPage, page_id)
    if not page or page.review_status != 'pending':
        return _error_content(f'候选页面不存在或已处理: id={page_id}')

    try:
        page.review_status = 'approved'
        db.session.commit()
        wiki_service.generate_index()
    except Exception as e:
        db.session.rollback()
        return _error_content(f'审批失败: {e}')

    # 异步更新向量索引（非阻塞，失败不影响审批）
    try:
        import threading
        from flask import current_app
        app_ref = current_app._get_current_object()

        def _bg_update():
            with app_ref.app_context():
                try:
                    from modules.wiki.compiler.retrieval import update_page_embeddings
                    update_page_embeddings()
                except Exception:
                    pass

        t = threading.Thread(target=_bg_update, daemon=True)
        t.start()
    except Exception:
        pass

    return _text_content({
        'id': page_id,
        'slug': page.slug,
        'approved': True,
    })


def handle_reject_candidate(args: dict) -> dict:
    """拒绝并删除一个候选页面。

    只删未入库的候选（review_status=pending），不影响已审批页面。

    Args:
        args: {id: int (required)}

    Returns:
        {id, rejected: true}

    Raises:
        MCPError(-32602): id 缺失
    """
    if 'id' not in args:
        raise MCPError(INVALID_PARAMS, 'id 参数必填')

    page_id = args['id']
    if not isinstance(page_id, int) or page_id < 1:
        raise MCPError(INVALID_PARAMS, 'id 必须是正整数')

    from extensions import db
    from modules.wiki.models import WikiPage
    from modules.wiki import wiki_service

    page = db.session.get(WikiPage, page_id)
    if not page or page.review_status != 'pending':
        return _error_content(f'候选页面不存在或已处理: id={page_id}')

    slug = page.slug
    try:
        wiki_service.delete_concept_page(slug)
        db.session.delete(page)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return _error_content(f'拒绝失败: {e}')

    return _text_content({
        'id': page_id,
        'rejected': True,
    })


# ---------- 文件夹 ----------

def handle_create_folder(args: dict) -> dict:
    """在文章知识库创建文件夹，可设 Fluent Emoji 图标。

    Args:
        args: {path: str (required), icon: str (optional)}

    Returns:
        {path, created: bool}

    Raises:
        MCPError(-32602): path 缺失或越界
    """
    if 'path' not in args or not args['path']:
        raise MCPError(INVALID_PARAMS, 'path 参数必填')

    raw_path = args['path']
    icon = args.get('icon', 'open_file_folder')

    # 路径安全校验：直接在 article root 下拼接并 commonpath 校验
    from flask import current_app
    article_root = current_app.config['ARTICLE_PATH']
    import os as _os
    normalized = raw_path.replace('\\', _os.sep).replace('/', _os.sep)
    folder_abs = _os.path.abspath(_os.path.normpath(
        _os.path.join(article_root, normalized)
    ))

    # 越界检测
    try:
        common = _os.path.commonpath([article_root, folder_abs])
    except ValueError:
        raise MCPError(INVALID_PARAMS, '路径越界')
    if common != article_root:
        raise MCPError(INVALID_PARAMS, '路径越界')

    created = not _os.path.exists(folder_abs)

    if created:
        _os.makedirs(folder_abs, exist_ok=True)

    # 写/更新 .zsnote.json（无论新建还是已存在都更新 icon）
    meta_path = _os.path.join(folder_abs, '.zsnote.json')
    meta = {}
    if _os.path.isfile(meta_path):
        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    meta['icon'] = icon
    meta.setdefault('name', _os.path.basename(folder_abs))
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    return _text_content({
        'path': raw_path,
        'created': created,
    })


# ---------- Phase 3: 知识贡献 ----------

def handle_submit_to_public(args: dict) -> dict:
    """提交知识到公共库（进入 pending 审批队列）。

    Args:
        args: {
            title: str (required),
            body: str (required),
            summary: str (optional),
            sources: list (optional),
            kind: str (optional, default 'concept'),
            author: str (optional, 从 Config.AUTHOR_NAME 取)
        }

    Returns:
        {id, slug, review_status: 'pending', message}
    """
    if 'title' not in args or not args['title']:
        return _error_content('title 参数必填')
    if 'body' not in args or not args['body']:
        return _error_content('body 参数必填')

    from config import Config
    from extensions import db
    from modules.wiki.models import WikiPage
    from modules.wiki import wiki_service

    title = args['title']
    body = args['body']
    summary = args.get('summary', '')
    sources = args.get('sources', [])
    kind = args.get('kind', 'concept')
    author = args.get('author', Config.AUTHOR_NAME)

    import re
    slug = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fff]+', '_', title).strip('_').lower()
    if not slug:
        slug = f'concept_{WikiPage.query.count() + 1}'

    # 如果 slug 已存在，追加后缀
    base_slug = slug
    suffix = 1
    while WikiPage.query.filter_by(slug=slug).first():
        slug = f'{base_slug}_{suffix}'
        suffix += 1

    # 提取溯源引用
    provenance = re.findall(r'\^\[([^\]]+)\]', body)

    page = WikiPage(
        title=title,
        slug=slug,
        kind=kind,
        summary=summary,
        body=body,
        sources=json.dumps(sources, ensure_ascii=False),
        provenance_refs=json.dumps(provenance, ensure_ascii=False),
        review_status='pending',
        author=author,
    )
    db.session.add(page)
    db.session.commit()

    # 写入 concept 文件
    wiki_service.save_concept_page(slug, title, body, summary, sources, kind)

    return _text_content({
        'id': page.id,
        'slug': slug,
        'review_status': 'pending',
        'message': f'已提交到审批队列（提交者：{author or "匿名"}）',
    })


def handle_create_todo(args: dict) -> dict:
    """Phase 7: MCP 工具创建待办事项。"""
    title = args.get('title', '').strip()
    if not title:
        raise INVALID_PARAMS.with_message('title 不能为空')

    from modules.todo.models import TodoItem
    from extensions import db

    item = TodoItem(
        title=title,
        priority=args.get('priority', 'normal'),
        related_slug=args.get('related_slug'),
        source='agent',
    )
    db.session.add(item)
    db.session.commit()

    return _text_content({
        'id': item.id,
        'title': item.title,
        'message': f'已创建待办：{title}',
    })
