import os
import json
import shutil

from flask import Blueprint, request, send_from_directory, render_template
from werkzeug.utils import secure_filename
from config import Config
from common.response import success_response, error_response

picture_bp = Blueprint('picture', __name__, template_folder='templates')

ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg'}


@picture_bp.route('/picture')
def picture_page():
    return render_template('picture.html', active_view='picture')


@picture_bp.route('/api/picture/tree', methods=['GET'])
def get_picture_tree():
    image_path = _resolve_image_path(request.args.get('image_path', ''))

    if not os.path.isdir(image_path):
        return error_response('路径不存在或不是目录', 404)

    tree = _build_image_tree(image_path)
    return success_response(tree)


@picture_bp.route('/api/picture/images', methods=['GET'])
def get_picture_images():
    requested_path = request.args.get('image_path', '')
    image_path = _resolve_image_path(requested_path)

    if not os.path.isdir(image_path):
        return error_response('路径不存在或不是目录', 404)

    images = []
    for root, dirs, files in os.walk(image_path):
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in ALLOWED_IMAGE_EXTENSIONS:
                full_path = os.path.join(root, file)
                # 始终使用相对于 Config.IMAGE_PATH 的路径，确保前端请求图片时能正确找到
                relative_path = os.path.relpath(full_path, Config.IMAGE_PATH)
                # 将路径统一转换为正斜杠格式，便于前端处理
                relative_path = relative_path.replace('\\', '/')
                images.append({
                    'name': file,
                    'path': relative_path,
                    'full_path': full_path,
                    'size': os.path.getsize(full_path),
                    'modified': os.path.getmtime(full_path),
                    'folder': os.path.dirname(relative_path) if os.path.dirname(relative_path) != '.' else ''
                })

    images.sort(key=lambda x: (x['folder'], x['name']))
    return success_response(images)


@picture_bp.route('/api/picture/image', methods=['GET'])
def get_picture_image():
    image_path = _resolve_image_path(request.args.get('image_path', ''))
    img = request.args.get('img', '')

    if not img:
        return error_response('缺少参数')

    if '..' in img:
        return error_response('无效的图片路径')

    # 同时处理正斜杠和反斜杠路径
    img_path_parts = img.replace('\\', '/').split('/')
    full_path = os.path.join(image_path, *img_path_parts)

    full_path_norm = os.path.normpath(os.path.abspath(full_path))
    image_path_norm = os.path.normpath(os.path.abspath(image_path))

    if not (full_path_norm.startswith(image_path_norm + os.sep) or full_path_norm == image_path_norm):
        return error_response('访问被拒绝')

    ext = os.path.splitext(full_path)[1].lower()
    content_types = {
        '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
        '.png': 'image/png', '.gif': 'image/gif',
        '.bmp': 'image/bmp', '.webp': 'image/webp',
        '.svg': 'image/svg+xml'
    }
    content_type = content_types.get(ext, 'application/octet-stream')

    try:
        return send_from_directory(os.path.dirname(full_path), os.path.basename(full_path), mimetype=content_type)
    except FileNotFoundError:
        return error_response('图片不存在', 404)


@picture_bp.route('/api/picture/folder', methods=['POST'])
def create_picture_folder():
    data = request.get_json()
    parent_path = _resolve_image_path(data.get('parent_path', ''))
    name = (data.get('name') or '').strip()
    icon = data.get('icon', 'Open file folder')

    if not parent_path or not name:
        return error_response('缺少参数')

    full_path_norm = os.path.normpath(os.path.abspath(parent_path))
    if not os.path.isdir(full_path_norm):
        return error_response('父目录不存在', 404)

    folder_path = os.path.join(parent_path, name)
    folder_norm = os.path.normpath(os.path.abspath(folder_path))
    if not folder_norm.startswith(full_path_norm + os.sep):
        return error_response('无效的路径')

    if os.path.exists(folder_path):
        return error_response('文件夹已存在')

    os.makedirs(folder_path)
    meta_file = os.path.join(folder_path, '.zsnote.json')
    with open(meta_file, 'w', encoding='utf-8') as f:
        json.dump({'icon': icon, 'name': name}, f, ensure_ascii=False, indent=2)
    return success_response({'path': folder_path, 'name': name}, '创建成功')


@picture_bp.route('/api/picture/folder-icon', methods=['POST'])
def update_picture_folder_icon():
    data = request.get_json()
    folder_path = data.get('path', '')
    icon = (data.get('icon') or '').strip()

    if not folder_path or not icon:
        return error_response('缺少参数')

    folder_norm = os.path.normpath(os.path.abspath(folder_path))
    if not os.path.isdir(folder_norm):
        return error_response('文件夹不存在', 404)

    meta_file = os.path.join(folder_path, '.zsnote.json')
    meta = {}
    if os.path.isfile(meta_file):
        with open(meta_file, 'r', encoding='utf-8') as f:
            meta = json.load(f)
    meta['icon'] = icon
    with open(meta_file, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return success_response({'icon': icon}, '更新成功')


@picture_bp.route('/api/picture/folder', methods=['DELETE'])
def delete_picture_folder():
    data = request.get_json(silent=True) or {}
    folder_path = data.get('path', '')

    if not folder_path:
        return error_response('缺少文件夹路径')

    folder_norm = os.path.normpath(os.path.abspath(folder_path))
    if not os.path.isdir(folder_norm):
        return error_response('文件夹不存在', 404)

    img_base_norm = os.path.normpath(os.path.abspath(Config.IMAGE_PATH))
    if not folder_norm.startswith(img_base_norm + os.sep) and folder_norm != img_base_norm:
        return error_response('无权删除该目录')

    shutil.rmtree(folder_path)
    return success_response(None, '删除成功')


@picture_bp.route('/api/picture/upload', methods=['POST'])
def upload_images():
    target_folder = request.form.get('target_folder', Config.IMAGE_PATH)

    if not _target_path_safe(target_folder):
        return error_response('无效的目标路径')

    os.makedirs(target_folder, exist_ok=True)

    files = request.files.getlist('files')
    uploaded = []
    for f in files:
        if not f or not f.filename:
            continue
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in ALLOWED_IMAGE_EXTENSIONS:
            continue
        filename = secure_filename(f.filename)
        if not filename or filename == ext.lstrip('.'):
            safe = f.filename.replace('/', '_').replace('\\', '_').replace('..', '_')
            filename = safe if safe else ext
        save_path = os.path.join(target_folder, filename)
        f.save(save_path)
        uploaded.append(filename)

    return success_response({'count': len(uploaded)}, f'上传成功 {len(uploaded)} 张图片')


@picture_bp.route('/api/picture/delete-images', methods=['POST'])
def delete_images():
    data = request.get_json()
    paths = data.get('paths', [])

    if not paths:
        return error_response('缺少参数')

    img_base_norm = os.path.normpath(os.path.abspath(Config.IMAGE_PATH))
    deleted = 0
    for rel_path in paths:
        full_path = os.path.join(Config.IMAGE_PATH, *rel_path.replace('\\', '/').split('/'))
        full_norm = os.path.normpath(os.path.abspath(full_path))
        if not full_norm.startswith(img_base_norm + os.sep):
            continue
        if os.path.isfile(full_norm):
            os.remove(full_norm)
            deleted += 1

    return success_response({'deleted': deleted}, f'删除成功 {deleted} 张图片')


def _resolve_image_path(requested_path):
    if requested_path:
        return requested_path
    return Config.IMAGE_PATH


def _target_path_safe(target_path):
    if not target_path or '..' in target_path:
        return False
    target_norm = os.path.normpath(os.path.abspath(target_path))
    base_norm = os.path.normpath(os.path.abspath(Config.IMAGE_PATH))
    return target_norm.startswith(base_norm + os.sep) or target_norm == base_norm


def _build_image_tree(root_path):
    result = []
    try:
        entries = os.listdir(root_path)
        entries.sort(key=lambda x: (
            os.path.isfile(os.path.join(root_path, x)),
            -os.path.getmtime(os.path.join(root_path, x)) if os.path.isdir(os.path.join(root_path, x)) else x.lower()
        ))
        for entry in entries:
            entry_path = os.path.join(root_path, entry)
            if os.path.isdir(entry_path):
                children = _build_image_tree(entry_path)
                icon = ''
                meta_path = os.path.join(entry_path, '.zsnote.json')
                if os.path.isfile(meta_path):
                    try:
                        with open(meta_path, 'r', encoding='utf-8') as mf:
                            meta = json.load(mf)
                            icon = meta.get('icon', '')
                    except Exception:
                        pass
                result.append({'name': entry, 'path': entry_path, 'type': 'folder', 'children': children, 'icon': icon})
            else:
                ext = os.path.splitext(entry)[1].lower()
                if ext in ALLOWED_IMAGE_EXTENSIONS:
                    result.append({
                        'name': entry, 'path': entry_path, 'type': 'file',
                        'size': os.path.getsize(entry_path), 'modified': os.path.getmtime(entry_path)
                    })
    except PermissionError:
        pass
    return result
