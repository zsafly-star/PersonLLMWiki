import os
import json
import re
import shutil

from config import Config


def build_file_tree(root_path):
    result = []
    try:
        entries = os.listdir(root_path)

        meta_path = os.path.join(root_path, '.zsnote.json')
        sort_order = []
        if os.path.isfile(meta_path):
            try:
                with open(meta_path, 'r', encoding='utf-8') as mf:
                    meta = json.load(mf)
                    sort_order = meta.get('sort_order', [])
            except Exception:
                pass

        if sort_order:
            name_order = {n: i for i, n in enumerate(sort_order)}
            entries.sort(key=lambda x: name_order.get(os.path.splitext(x)[0], len(entries)))
        else:
            entries.sort(key=lambda x: (os.path.isfile(os.path.join(root_path, x)), -os.path.getmtime(os.path.join(root_path, x))))

        for entry in entries:
            entry_path = os.path.join(root_path, entry)

            if os.path.isdir(entry_path):
                children = build_file_tree(entry_path)
                icon = ''
                meta_path = os.path.join(entry_path, '.zsnote.json')
                if os.path.isfile(meta_path):
                    try:
                        with open(meta_path, 'r', encoding='utf-8') as mf:
                            meta = json.load(mf)
                            icon = meta.get('icon', '')
                    except Exception:
                        pass
                result.append({
                    'name': entry,
                    'path': entry_path,
                    'type': 'folder',
                    'children': children,
                    'icon': icon
                })
            elif entry.endswith('.md') and entry.lower() != 'index.md':
                result.append({
                    'name': entry,
                    'path': entry_path,
                    'type': 'file'
                })
    except PermissionError:
        pass
    return result


def read_file_content(file_path):
    if '..' in file_path or not os.path.isfile(file_path):
        return None
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()


def write_file_content(file_path, content):
    if '..' in file_path or not os.path.isfile(file_path):
        return False
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    return True


def create_folder(parent_path, name, icon='open_file_folder', description=''):
    folder_path = os.path.join(parent_path, name)
    if os.path.exists(folder_path):
        return None

    os.makedirs(folder_path)

    index_content = f'# {name}\n'
    if description:
        index_content += f'\n> {description}\n'
    index_content += '\n'

    with open(os.path.join(folder_path, 'index.md'), 'w', encoding='utf-8') as f:
        f.write(index_content)

    meta = {'icon': icon, 'name': name}
    with open(os.path.join(folder_path, '.zsnote.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    return {'path': folder_path, 'name': name}


def create_document(folder_path):
    base_name = '无标题文档'
    name = base_name + '.md'
    file_path = os.path.join(folder_path, name)

    counter = 1
    while os.path.exists(file_path):
        name = f'{base_name}{counter}.md'
        file_path = os.path.join(folder_path, name)
        counter += 1

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(f'# {base_name}\n\n')

    _update_index_add_link(folder_path, base_name, name)

    return {'path': file_path, 'name': name}


def rename_document(file_path, new_name):
    if not os.path.isfile(file_path):
        return None

    dir_path = os.path.dirname(file_path)
    old_base = os.path.splitext(os.path.basename(file_path))[0]

    if new_name == old_base:
        return {'path': file_path}

    if not new_name.endswith('.md'):
        new_name += '.md'

    base = new_name[:-3] if new_name.endswith('.md') else new_name
    illegal = r'<>:"/\|?*'
    found = [c for c in illegal if c in base]
    if found:
        raise ValueError(f'标题包含非法字符: {" ".join(found)}')

    new_path = os.path.join(dir_path, new_name)
    if os.path.exists(new_path) and new_path != file_path:
        return None

    os.rename(file_path, new_path)

    _update_index_rename(dir_path, old_base, new_name)

    return {'path': new_path, 'old_path': file_path}


def move_document(src_path, target_folder):
    if not os.path.exists(src_path):
        return None
    if not os.path.isdir(target_folder):
        return None

    base_name = os.path.basename(src_path)
    dest_path = os.path.join(target_folder, base_name)

    if os.path.exists(dest_path):
        return None

    is_file = os.path.isfile(src_path)
    old_dir = os.path.dirname(src_path)

    shutil.move(src_path, dest_path)

    if is_file:
        old_base = os.path.splitext(base_name)[0]
        _update_index_remove_link(old_dir, old_base)
        _update_index_add_link(target_folder, old_base, base_name)

    return {'path': dest_path, 'old_path': src_path}


def list_folder_children(folder_path):
    children = []
    try:
        meta_path = os.path.join(folder_path, '.zsnote.json')
        sort_order = []
        if os.path.isfile(meta_path):
            try:
                with open(meta_path, 'r', encoding='utf-8') as mf:
                    meta = json.load(mf)
                    sort_order = meta.get('sort_order', [])
            except Exception:
                pass

        for entry in os.listdir(folder_path):
            if entry.startswith('.') or entry == 'index.md':
                continue
            entry_path = os.path.join(folder_path, entry)
            if entry.endswith('.md') and os.path.isfile(entry_path):
                name = os.path.splitext(entry)[0]
                children.append({'name': name, 'path': entry_path, 'type': 'file'})

        if sort_order:
            name_order = {n: i for i, n in enumerate(sort_order)}
            children.sort(key=lambda c: name_order.get(c['name'], len(children)))
    except Exception:
        pass
    return children


def save_sort_order(folder_path, sort_order):
    meta_path = os.path.join(folder_path, '.zsnote.json')
    meta = {}
    if os.path.isfile(meta_path):
        try:
            with open(meta_path, 'r', encoding='utf-8') as mf:
                meta = json.load(mf)
        except Exception:
            pass
    meta['sort_order'] = sort_order
    try:
        with open(meta_path, 'w', encoding='utf-8') as mf:
            json.dump(meta, mf, ensure_ascii=False, indent=2)
        return {'sort_order': sort_order}
    except Exception:
        return None


def delete_document(file_path):
    if os.path.isfile(file_path):
        dir_path = os.path.dirname(file_path)
        file_name = os.path.basename(file_path)
        os.remove(file_path)
        _update_index_remove_link(dir_path, file_name)
        # 清理对应的图片目录
        _cleanup_image_dir(file_path)
        return True
    elif os.path.isdir(file_path):
        shutil.rmtree(file_path)
        return True
    return False


def _cleanup_image_dir(md_file_path):
    """删除文章对应的图片目录（如果为空）"""
    if not md_file_path.lower().endswith('.md'):
        return
    md_stem = os.path.splitext(os.path.basename(md_file_path))[0]
    img_dir = os.path.join(Config.IMAGE_PATH, md_stem)
    if os.path.isdir(img_dir) and not os.listdir(img_dir):
        os.rmdir(img_dir)


def get_folder_meta(folder_path):
    if not os.path.isdir(folder_path):
        return None

    meta_file = os.path.join(folder_path, '.zsnote.json')
    meta = {}
    if os.path.exists(meta_file):
        with open(meta_file, 'r', encoding='utf-8') as f:
            meta = json.load(f)

    meta.setdefault('icon', 'open_file_folder')
    meta.setdefault('name', os.path.basename(folder_path))

    index_path = os.path.join(folder_path, 'index.md')
    if os.path.isfile(index_path):
        with open(index_path, 'r', encoding='utf-8') as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith('> '):
                    meta['description'] = stripped[2:].strip()
                    break

    return meta


def save_folder_meta(folder_path, data):
    if not os.path.isdir(folder_path):
        return False

    meta_file = os.path.join(folder_path, '.zsnote.json')
    meta = {}
    if os.path.exists(meta_file):
        with open(meta_file, 'r', encoding='utf-8') as f:
            meta = json.load(f)

    meta['icon'] = data.get('icon', meta.get('icon', 'open_file_folder'))
    meta['name'] = data.get('name', meta.get('name', os.path.basename(folder_path)))
    meta['description'] = data.get('description', meta.get('description', ''))

    with open(meta_file, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    return True


def ensure_resource_dirs():
    for dir_path in [Config.ARTICLE_PATH, Config.IMAGE_PATH, Config.ATTACHMENT_PATH]:
        os.makedirs(dir_path, exist_ok=True)


def resolve_image_path(image_path, img):
    if '..' in img:
        return None

    img = img.replace('/', os.sep).replace('\\', os.sep)
    full_path = os.path.normpath(os.path.join(image_path, img))
    image_path_norm = os.path.normpath(os.path.abspath(image_path))

    if not full_path.startswith(image_path_norm + os.sep) and full_path != image_path_norm:
        return None

    if not os.path.isfile(full_path):
        return None

    return full_path


def list_attachments(page=1, page_size=20):
    attachments_path = Config.ATTACHMENT_PATH
    os.makedirs(attachments_path, exist_ok=True)

    files = []
    for item in os.listdir(attachments_path):
        item_path = os.path.join(attachments_path, item)
        if os.path.isfile(item_path):
            stat = os.stat(item_path)
            files.append({
                'name': item,
                'size': stat.st_size,
                'modified': stat.st_mtime
            })

    files.sort(key=lambda x: x['modified'], reverse=True)

    total = len(files)
    start = (page - 1) * page_size
    end = start + page_size
    return {
        'attachments': files[start:end],
        'total': total,
        'page': page,
        'page_size': page_size
    }


def save_uploaded_attachments(files):
    attachments_path = Config.ATTACHMENT_PATH
    os.makedirs(attachments_path, exist_ok=True)

    uploaded = []
    for f in files:
        if not f or not f.filename:
            continue

        filename = f.filename.replace('/', '_').replace('\\', '_').replace('..', '_')
        if not filename:
            continue

        f.save(os.path.join(attachments_path, filename))
        uploaded.append(filename)

    return uploaded


def get_attachment_path(file_name):
    if not file_name:
        return None
    file_path = os.path.join(Config.ATTACHMENT_PATH, file_name)
    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        return None
    return file_path


def _update_index_add_link(folder_path, doc_title, doc_filename):
    index_path = os.path.join(folder_path, 'index.md')
    if not os.path.isfile(index_path):
        return

    with open(index_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    if not any(doc_filename in line for line in lines):
        if lines and lines[-1].strip() != '':
            lines.append('\n')
        lines.append(f'## [{doc_title}]({doc_filename})\n')
        lines.append('\n')
        with open(index_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)


def _update_index_rename(dir_path, old_base, new_name):
    index_path = os.path.join(dir_path, 'index.md')
    if not os.path.isfile(index_path):
        return

    with open(index_path, 'r', encoding='utf-8') as f:
        index_content = f.read()

    old_file = old_base + '.md'
    new_file = new_name if new_name.endswith('.md') else new_name + '.md'
    new_title = new_name[:-3] if new_name.endswith('.md') else new_name

    index_content = re.sub(
        r'\[' + re.escape(old_base) + r'\]\(' + re.escape(old_file) + r'\)',
        '[' + new_title + '](' + new_file + ')',
        index_content
    )

    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(index_content)


def _update_index_remove_link(dir_path, file_name):
    index_path = os.path.join(dir_path, 'index.md')
    if not os.path.isfile(index_path):
        return

    with open(index_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    new_lines = []
    skip_blank = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('## [') and file_name in stripped:
            skip_blank = True
            continue
        if skip_blank and stripped == '':
            skip_blank = False
            continue
        skip_blank = False
        new_lines.append(line)

    while new_lines and new_lines[-1].strip() == '':
        new_lines.pop()
    if new_lines:
        new_lines.append('\n')

    with open(index_path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
