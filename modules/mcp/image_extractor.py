"""MCP 内联图片提取器。

从 Markdown 内容中提取 ![alt](data:image/xxx;base64,...) 形式的内联图片，
解码后保存到指定目录，返回新的内容（data URI 被替换为相对路径）。

设计：
- 文件名：YYYYMMDD_HHMMSS_NNN.<ext>（避免重名覆盖）
- SVG 过滤 <script> 标签（防 XSS）
- 无 data URI 时原样返回
- 非法 base64 抛 ValueError
"""
import base64
import os
import re
from datetime import datetime

# 匹配 ![alt](data:image/xxx;base64,...)
# alt 可以为空，mime 类型支持 image/png、image/svg+xml 等
_DATA_URI_PATTERN = re.compile(
    r'(!\[[^\]]*\]\()'                   # ![alt](
    r'(data:image/(png|jpe?g|gif|bmp|webp|svg\+xml);base64,)'  # data:image/xxx;base64,
    r'([A-Za-z0-9+/=\s]+)'               # base64 数据
    r'(\))'                               # )
)

# MIME → 扩展名映射
_MIME_TO_EXT = {
    'png': 'png',
    'jpg': 'jpg',
    'jpeg': 'jpg',
    'gif': 'gif',
    'bmp': 'bmp',
    'webp': 'webp',
    'svg+xml': 'svg',
}

# SVG 安全过滤：<script>...</script>
_SVG_SCRIPT_PATTERN = re.compile(
    rb'<script[\s\S]*?</script>',
    re.IGNORECASE,
)


def _sanitize_svg(raw: bytes) -> bytes:
    """过滤 SVG 中的 <script> 标签，并确保有正确的命名空间。"""
    # 移除 script 标签
    raw = _SVG_SCRIPT_PATTERN.sub(b'', raw)
    
    # 确保 SVG 有正确的命名空间
    raw_str = raw.decode('utf-8', errors='replace')
    if '<svg ' in raw_str and 'xmlns=' not in raw_str:
        # 在 <svg 标签中添加命名空间
        raw_str = raw_str.replace('<svg ', '<svg xmlns="http://www.w3.org/2000/svg" ')
    return raw_str.encode('utf-8')


def extract_inline_images(content: str, image_dir: str, markdown_prefix: str = ''):
    """提取 Markdown 中的内联 data URI 图片，保存到 image_dir。

    Args:
        content: Markdown 源文本
        image_dir: 图片保存目录（不存在则创建）
        markdown_prefix: 写入 Markdown 的路径前缀。
            如 'img/笔记/' 会把图片引用替换为 ![alt](img/笔记/xxx.png)。
            空字符串（默认）则只写文件名 ![alt](xxx.png)。

    Returns:
        tuple (new_content, image_paths):
            new_content: 替换 data URI 为相对路径后的 Markdown
            image_paths: 保存的图片绝对路径列表

    Raises:
        ValueError: base64 解码失败
    """
    if not os.path.isdir(image_dir):
        os.makedirs(image_dir, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    image_paths = []
    counter = 0

    def _replace(match):
        nonlocal counter
        prefix = match.group(1)          # ![alt](
        data_uri = match.group(2)        # data:image/xxx;base64,
        mime = match.group(3)            # png / jpeg / svg+xml ...
        b64_data = match.group(4)        # base64 字符串
        close = match.group(5)           # )

        # 解码
        try:
            raw = base64.b64decode(b64_data)
        except Exception as e:
            raise ValueError(f'base64 解码失败: {e}') from e

        # SVG 过滤 script
        if mime == 'svg+xml':
            raw = _sanitize_svg(raw)

        # 扩展名
        ext = _MIME_TO_EXT.get(mime.lower(), 'bin')

        # 文件名
        counter += 1
        filename = f'{timestamp}_{counter:03d}.{ext}'
        filepath = os.path.join(image_dir, filename)
        with open(filepath, 'wb') as f:
            f.write(raw)

        image_paths.append(filepath)
        # Markdown 引用路径 = 前缀 + 文件名
        md_path = f'{markdown_prefix}{filename}' if markdown_prefix else filename
        return f'{prefix}{md_path}{close}'

    new_content = _DATA_URI_PATTERN.sub(_replace, content)
    return new_content, image_paths


def strip_inline_images(content: str) -> str:
    """将 Markdown 中的内联 data URI 图片替换为占位符。

    用于读取路径，避免 base64 图片撑爆 LLM 上下文窗口。

    Args:
        content: Markdown 源文本

    Returns:
        替换后的 Markdown（data URI → [图片: MIME, N字符]）
    """
    def _strip_match(match):
        mime = match.group(3)       # png / jpeg / svg+xml ...
        b64_data = match.group(4)   # base64 字符串
        b64_len = len(b64_data)
        return f'[图片: {mime}, {b64_len}字符]'

    return _DATA_URI_PATTERN.sub(_strip_match, content)
