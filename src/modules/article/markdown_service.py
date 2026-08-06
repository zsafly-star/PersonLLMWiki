import re
import html as html_lib
import markdown as md_lib

MARKDOWN_EXTENSIONS = [
    'markdown.extensions.extra',
    'markdown.extensions.codehilite',
    'markdown.extensions.tables',
]


def render_markdown(content):
    html_content = md_lib.markdown(content, extensions=MARKDOWN_EXTENSIONS)
    html_content = _convert_task_lists(html_content)
    html_content = _convert_wiki_links(html_content)
    html_content = _convert_provenance(html_content)
    return html_content


def _convert_task_lists(html_content):
    """将 <li>[ ] 文本</li> / <li>[x] 文本</li> 转换为禁用复选框。"""
    def replace_li(match):
        prefix = match.group(1)  # <li> 或 <li ...>
        checked = match.group(2).lower() == 'x'
        rest = match.group(3)
        checkbox = '<input type="checkbox" disabled{0} class="task-list-checkbox">'.format(
            ' checked' if checked else ''
        )
        return '{0}{1} {2}</li>'.format(prefix, checkbox, rest)

    # 匹配 <li>[ ] ... 或 <li>[x] ... （兼容 <li> 带属性的情况）
    pattern = re.compile(
        r'(<li[^>]*>)\s*\[([ xX])\]\s*(.*?)</li>',
        re.DOTALL,
    )
    return pattern.sub(replace_li, html_content)


def _convert_wiki_links(html_content):
    """将 [[标题]] 或 [[标题|显示文本]] 转换为站内 wiki 链接。"""
    def replace_link(match):
        target = match.group(1).strip()
        text = match.group(2).strip() if match.group(2) else target
        target_attr = html_lib.escape(target, quote=True)
        text_html = html_lib.escape(text)
        return '<a class="wiki-link" data-target="{0}" title="跳转到：{0}">{1}</a>'.format(
            target_attr, text_html
        )

    pattern = re.compile(r'\[\[([^\]|]+)(?:\|([^\]]+))?\]\]')
    return pattern.sub(replace_link, html_content)


def _convert_provenance(html_content):
    """将 ^[来源文件] 转换为来源标注样式 span。"""
    def replace(match):
        source = html_lib.escape(match.group(1), quote=True)
        return '<span class="wk-provenance" title="来源: {0}">^[{0}]</span>'.format(source)

    pattern = re.compile(r'\^\[([^\]]+)\]')
    return pattern.sub(replace, html_content)


def rewrite_image_links(content, api_prefix):
    # Escape backslashes in api_prefix for regex replacement
    safe_prefix = api_prefix.replace('\\', '\\\\')
    # Pattern 1: relative img/ paths → absolute API paths
    content = re.sub(
        r'(!\[[^\]]*\]\()\s*\.?/?img/',
        r'\1' + safe_prefix,
        content
    )
    # Pattern 2: bare relative image paths (not http://, https://, or /api/)
    content = re.sub(
        r'(!\[[^\]]*\]\()\s*(?!(?:https?://|/api/))([^\s\)]+\.(?:png|jpe?g|gif|bmp|webp|svg))',
        r'\1' + safe_prefix + r'\2',
        content
    )
    # Pattern 3: already-rewritten /api/article/image URLs with outdated image_path
    content = re.sub(
        r'(!\[[^\]]*\]\()/api/article/image\?image_path=[^&]+&img=([^\s\)]+)',
        r'\1' + safe_prefix + r'\2',
        content
    )
    return content


def build_image_api_prefix(image_path):
    return '/api/article/image?image_path=' + image_path + '&img='
