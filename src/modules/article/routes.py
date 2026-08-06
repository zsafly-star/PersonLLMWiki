import json
import os
import re
import urllib.parse

from flask import Blueprint, request, send_from_directory, render_template, send_file
from config import Config
from common.response import success_response, error_response
from . import file_service, markdown_service
from .services import ArticleService

article_bp = Blueprint('article', __name__, template_folder='templates')

STATIC_EMOJI_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'static', 'emoji'
)


@article_bp.route('/article')
def article_page():
    return render_template('article.html', active_view='article')


@article_bp.route('/api/articles', methods=['GET'])
def get_articles():
    articles = ArticleService.get_all()
    return success_response(articles)


@article_bp.route('/api/articles/<int:article_id>', methods=['GET'])
def get_article(article_id):
    article = ArticleService.get_by_id(article_id)
    if article:
        return success_response(article)
    return error_response('文章不存在', 404)


@article_bp.route('/api/articles', methods=['POST'])
def create_article():
    data = request.get_json()
    if not data or 'title' not in data:
        return error_response('缺少标题')
    article = ArticleService.create(data)
    return success_response(article, '创建成功')


@article_bp.route('/api/articles/<int:article_id>', methods=['PUT'])
def update_article(article_id):
    data = request.get_json()
    article = ArticleService.update(article_id, data)
    if article:
        return success_response(article, '更新成功')
    return error_response('文章不存在', 404)


@article_bp.route('/api/articles/<int:article_id>', methods=['DELETE'])
def delete_article(article_id):
    success = ArticleService.delete(article_id)
    if success:
        return success_response(None, '删除成功')
    return error_response('文章不存在', 404)


@article_bp.route('/api/article/tree', methods=['GET'])
def get_article_tree():
    path = request.args.get('path', Config.ARTICLE_PATH)

    if not os.path.exists(path):
        return error_response(f'路径不存在: {path}', 404)

    if not os.access(path, os.R_OK):
        return error_response('没有访问权限', 403)

    tree = file_service.build_file_tree(path)
    return success_response(tree)


@article_bp.route('/api/article/content', methods=['GET'])
def get_article_content():
    file_path = request.args.get('path', '')
    image_path = request.args.get('image_path', '')

    if not file_path:
        return error_response('缺少文件路径')

    if os.path.isdir(file_path):
        icon = ''
        folder_name = os.path.basename(file_path)
        description = ''
        meta_path = os.path.join(file_path, '.zsnote.json')
        if os.path.isfile(meta_path):
            try:
                with open(meta_path, 'r', encoding='utf-8') as mf:
                    meta = json.load(mf)
                    icon = meta.get('icon', '')
                    if meta.get('name'):
                        folder_name = meta.get('name')
                    description = meta.get('description', '')
            except Exception:
                pass

        html_content = markdown_service.render_markdown(description) if description else ''

        return success_response({
            'title': folder_name,
            'content': html_content,
            'description': description,
            'path': file_path,
            'icon': icon,
            'children': file_service.list_folder_children(file_path)
        })

    content = file_service.read_file_content(file_path)
    if content is None:
        return error_response('无效的文件路径')

    if not image_path:
        image_path = Config.IMAGE_PATH
    api_prefix = markdown_service.build_image_api_prefix(image_path)
    content = markdown_service.rewrite_image_links(content, api_prefix)

    html_content = markdown_service.render_markdown(content)
    title = os.path.splitext(os.path.basename(file_path))[0]
    modified = os.path.getmtime(file_path) if os.path.exists(file_path) else None

    return success_response({
        'title': title,
        'content': html_content,
        'raw': content,
        'path': file_path,
        'modified': modified
    })


@article_bp.route('/api/article/content', methods=['POST'])
def save_article_content():
    data = request.get_json()
    file_path = data.get('path', '')
    content = data.get('content', '')

    if not file_path:
        return error_response('缺少文件路径')

    if file_service.write_file_content(file_path, content):
        return success_response(None, '保存成功')
    return error_response('无效的文件路径')


@article_bp.route('/api/article/preview', methods=['POST'])
def preview_article():
    data = request.get_json()
    content = data.get('content', '')

    image_path = data.get('image_path', '') or Config.IMAGE_PATH
    api_prefix = markdown_service.build_image_api_prefix(image_path)
    content = markdown_service.rewrite_image_links(content, api_prefix)
    html_content = markdown_service.render_markdown(content)
    return success_response({'content': html_content})


@article_bp.route('/api/article/folder', methods=['POST'])
def create_folder():
    data = request.get_json()
    parent_path = data.get('parent_path', '')
    name = (data.get('name') or '').strip()
    icon = data.get('icon', 'open_file_folder')
    description = (data.get('description') or '').strip()

    if not parent_path:
        return error_response('缺少父目录路径')
    if not name:
        return error_response('请输入文件夹名称')
    
    # 将相对路径转换为绝对路径
    if parent_path.startswith('/'):
        parent_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), parent_path.lstrip('/'))
    
    if not os.path.isdir(parent_path):
        return error_response('父目录不存在', 404)

    result = file_service.create_folder(parent_path, name, icon, description)
    if result is None:
        return error_response('文件夹已存在')
    return success_response(result, '创建成功')


@article_bp.route('/api/article/document', methods=['POST'])
def create_document():
    data = request.get_json()
    folder_path = data.get('folder_path', '')

    if not folder_path:
        return error_response('缺少目标文件夹路径')
    if not os.path.isdir(folder_path):
        return error_response('目标文件夹不存在', 404)

    result = file_service.create_document(folder_path)
    return success_response(result, '创建成功')


@article_bp.route('/api/article/rename', methods=['POST'])
def rename_document():
    data = request.get_json()
    file_path = data.get('file_path', '')
    new_name = (data.get('new_name') or '').strip()

    if not file_path:
        return error_response('缺少文件路径')
    if not new_name:
        return error_response('缺少新名称')

    try:
        result = file_service.rename_document(file_path, new_name)
    except Exception as e:
        return error_response(f'重命名失败: {str(e)}', 500)
    if result is None:
        return error_response('重命名失败（文件不存在或目标名已存在）', 400)
    return success_response(result, '重命名成功')


@article_bp.route('/api/article/move', methods=['POST'])
def move_document():
    data = request.get_json()
    src_path = data.get('src_path', '')
    target_folder = data.get('target_folder', '') or Config.ARTICLE_PATH

    if not src_path:
        return error_response('缺少路径参数')

    result = file_service.move_document(src_path, target_folder)
    if result is None:
        return error_response('移动失败（源文件不存在或目标路径无效）', 400)
    return success_response(result, '移动成功')


@article_bp.route('/api/article/sort-order', methods=['POST'])
def save_sort_order():
    data = request.get_json()
    folder_path = data.get('folder_path', '') or Config.ARTICLE_PATH
    sort_order = data.get('sort_order', [])

    result = file_service.save_sort_order(folder_path, sort_order)
    if result is None:
        return error_response('保存排序失败', 400)
    return success_response(result, '保存成功')


@article_bp.route('/api/article/document', methods=['DELETE'])
def delete_document():
    file_path = request.args.get('path', '')

    if not file_path:
        return error_response('缺少文件路径')

    if file_service.delete_document(file_path):
        return success_response(None, '删除成功')
    return error_response('文件不存在', 404)


@article_bp.route('/api/article/init-paths', methods=['POST'])
def init_paths():
    file_service.ensure_resource_dirs()
    return success_response({
        'article_path': Config.ARTICLE_PATH,
        'img_path': Config.IMAGE_PATH
    })


@article_bp.route('/api/article/upload-attachment', methods=['POST'])
def upload_attachment():
    files = request.files.getlist('files')
    uploaded = file_service.save_uploaded_attachments(files)
    return success_response({
        'uploaded': uploaded,
        'attachments_path': Config.ATTACHMENT_PATH
    })


@article_bp.route('/api/article/attachments', methods=['GET'])
def get_attachments():
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 20))
    result = file_service.list_attachments(page, page_size)
    return success_response(result)


@article_bp.route('/api/article/attachment', methods=['GET'])
def get_attachment():
    file_name = request.args.get('file', '')
    if not file_name:
        raw_query = request.query_string.decode('utf-8')
        query = raw_query.replace('%26amp%3B', '&').replace('&amp;', '&')
        params = {}
        for pair in query.split('&'):
            if '=' in pair:
                key, value = pair.split('=', 1)
                params[urllib.parse.unquote(key)] = urllib.parse.unquote(value)
        file_name = params.get('file', '')

    if not file_name:
        return error_response('缺少文件名')

    attachment_path = file_service.get_attachment_path(file_name)
    if attachment_path is None:
        return error_response(f'文件不存在: {file_name}', 404)

    return send_file(attachment_path, as_attachment=True, download_name=file_name)


@article_bp.route('/api/article/attachment', methods=['DELETE'])
def delete_attachment():
    data = request.get_json()
    file_name = data.get('file', '')
    
    if not file_name:
        return error_response('缺少文件名')
    
    attachment_path = file_service.get_attachment_path(file_name)
    if attachment_path is None:
        return error_response(f'文件不存在: {file_name}', 404)
    
    try:
        os.remove(attachment_path)
        return success_response('删除成功')
    except Exception as e:
        return error_response(f'删除失败: {str(e)}', 500)


@article_bp.route('/api/article/image/', methods=['GET'])
def get_article_image():
    image_path = request.args.get('image_path', '')
    img = request.args.get('img', '')

    if not image_path or not img:
        return error_response('缺少参数')

    full_path = file_service.resolve_image_path(image_path, img)
    if full_path is None:
        return error_response('无效的图片路径或访问被拒绝')

    ext = os.path.splitext(full_path)[1].lower()
    content_types = {
        '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
        '.png': 'image/png', '.gif': 'image/gif',
        '.bmp': 'image/bmp', '.webp': 'image/webp',
        '.svg': 'image/svg+xml'
    }
    return send_from_directory(
        os.path.dirname(full_path),
        os.path.basename(full_path),
        mimetype=content_types.get(ext, 'application/octet-stream')
    )


@article_bp.route('/api/article/folder-meta', methods=['GET'])
def get_folder_meta():
    folder_path = request.args.get('path', '')
    if not folder_path:
        return error_response('缺少文件夹路径')

    meta = file_service.get_folder_meta(folder_path)
    if meta is None:
        return error_response('文件夹不存在', 404)
    return success_response(meta)


@article_bp.route('/api/article/folder-meta', methods=['POST'])
def save_folder_meta():
    data = request.get_json()
    folder_path = data.get('path', '')

    if not folder_path:
        return error_response('缺少文件夹路径')

    if file_service.save_folder_meta(folder_path, data):
        return success_response(None, '保存成功')
    return error_response('文件夹不存在', 404)


@article_bp.route('/api/article/emoji/<name>', methods=['GET'])
def get_emoji(name):
    if not name or '..' in name or '/' in name or '\\' in name:
        return error_response('无效的图标名称')

    safe_name = re.sub(r'[^\w\s]', '_', name)
    filename = safe_name + '_3d.png'
    filepath = os.path.join(STATIC_EMOJI_DIR, filename)

    if os.path.isfile(filepath):
        return send_from_directory(STATIC_EMOJI_DIR, filename, mimetype='image/png')

    return error_response('图标文件不存在', 404)
