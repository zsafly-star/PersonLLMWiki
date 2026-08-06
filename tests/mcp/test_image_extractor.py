"""MCP 内联图片提取单元测试。

验证 extract_inline_images(content, image_dir) 的行为：
- 识别 Markdown 里的 ![alt](data:image/xxx;base64,...)
- 解码 base64 → 保存到指定目录
- 返回新的 content（data URI 被替换为相对路径）
- 支持多格式（png/jpg/svg/webp等）
- SVG 中的 <script> 标签被过滤
- 无图片时不误伤原文
- 多图片按序号命名
"""
import base64
import os

import pytest


def _make_data_uri(mime: str, raw: bytes) -> str:
    b64 = base64.b64encode(raw).decode('ascii')
    return f'data:{mime};base64,{b64}'


class TestExtractInlineImages:

    def test_single_png_extracted_and_path_replaced(self, tmp_path):
        from modules.mcp.image_extractor import extract_inline_images

        raw = b'\x89PNG\r\n\x1a\n' + b'\x00' * 32  # 伪 PNG 头
        data_uri = _make_data_uri('image/png', raw)
        content = f'# 标题\n\n![图片]({data_uri})\n\n正文\n'

        new_content, images = extract_inline_images(content, str(tmp_path))

        # 图片应被保存
        assert len(images) == 1
        img_path = images[0]
        assert img_path.endswith('.png')
        assert os.path.isfile(os.path.join(str(tmp_path), os.path.basename(img_path)))
        # 内容里 data URI 应被替换为相对路径
        assert 'data:image/png;base64,' not in new_content
        assert os.path.basename(img_path) in new_content
        # alt 文本保留
        assert '![图片]' in new_content

    def test_multiple_images_get_sequential_names(self, tmp_path):
        from modules.mcp.image_extractor import extract_inline_images

        raw1 = b'\x89PNG' + b'\x01' * 10
        raw2 = b'\x89PNG' + b'\x02' * 10
        content = (
            f'# 多图\n\n'
            f'![1]({_make_data_uri("image/png", raw1)})\n\n'
            f'中间文字\n\n'
            f'![2]({_make_data_uri("image/png", raw2)})\n'
        )

        new_content, images = extract_inline_images(content, str(tmp_path))

        assert len(images) == 2
        # 两个不同的文件
        assert images[0] != images[1]
        for img in images:
            assert os.path.isfile(os.path.join(str(tmp_path), os.path.basename(img)))
        # data URI 全部被替换
        assert 'base64' not in new_content

    def test_jpeg_and_svg_and_webp_supported(self, tmp_path):
        from modules.mcp.image_extractor import extract_inline_images

        svg_raw = b'<svg xmlns="http://www.w3.org/2000/svg"><circle/></svg>'
        jpg_raw = b'\xff\xd8\xff\xe0' + b'\x00' * 10
        webp_raw = b'RIFF' + b'\x00' * 20 + b'WEBP'
        content = (
            f'![svg]({_make_data_uri("image/svg+xml", svg_raw)})\n'
            f'![jpg]({_make_data_uri("image/jpeg", jpg_raw)})\n'
            f'![webp]({_make_data_uri("image/webp", webp_raw)})\n'
        )

        new_content, images = extract_inline_images(content, str(tmp_path))

        assert len(images) == 3
        exts = [os.path.splitext(i)[1] for i in images]
        assert '.svg' in exts
        assert any(e in ('.jpg', '.jpeg') for e in exts)
        assert '.webp' in exts

    def test_svg_script_tags_filtered(self, tmp_path):
        from modules.mcp.image_extractor import extract_inline_images

        # 带 script 的恶意 SVG
        evil_svg = (
            b'<svg xmlns="http://www.w3.org/2000/svg">'
            b'<script>alert("xss")</script>'
            b'<rect/></svg>'
        )
        content = f'![x]({_make_data_uri("image/svg+xml", evil_svg)})\n'

        _, images = extract_inline_images(content, str(tmp_path))

        saved = os.path.join(str(tmp_path), os.path.basename(images[0]))
        with open(saved, 'rb') as f:
            saved_content = f.read()
        assert b'<script' not in saved_content.lower()
        assert b'<rect' in saved_content  # 其他内容保留

    def test_no_images_returns_content_unchanged(self, tmp_path):
        from modules.mcp.image_extractor import extract_inline_images

        original = '# 纯文本\n\n无图片\n\n![](img/existing.png)\n'
        new_content, images = extract_inline_images(original, str(tmp_path))

        assert new_content == original
        assert images == []

    def test_normal_http_url_not_touched(self, tmp_path):
        from modules.mcp.image_extractor import extract_inline_images

        content = '![外链](https://example.com/x.png)\n![](/api/article/image?img=x.png)\n'
        new_content, images = extract_inline_images(content, str(tmp_path))

        assert new_content == content
        assert images == []

    def test_creates_image_dir_if_missing(self, tmp_path):
        from modules.mcp.image_extractor import extract_inline_images

        target_dir = os.path.join(str(tmp_path), 'new_folder')
        assert not os.path.exists(target_dir)

        raw = b'\x89PNG' + b'\x00' * 8
        content = f'![]({_make_data_uri("image/png", raw)})\n'

        _, images = extract_inline_images(content, target_dir)

        assert os.path.isdir(target_dir)
        assert os.path.isfile(os.path.join(target_dir, os.path.basename(images[0])))

    def test_filename_pattern_is_timestamp_and_index(self, tmp_path):
        """图片文件名格式应为 YYYYMMDD_HHMMSS_NNN.<ext>"""
        from modules.mcp.image_extractor import extract_inline_images
        import re

        raw = b'\x89PNG' + b'\x00' * 8
        content = f'![]({_make_data_uri("image/png", raw)})\n'

        _, images = extract_inline_images(content, str(tmp_path))

        name = os.path.basename(images[0])
        # YYYYMMDD_HHMMSS_NNN.png
        assert re.match(r'\d{8}_\d{6}_\d{3}\.png', name), f'文件名格式不符: {name}'

    def test_markdown_alt_text_preserved_in_replacement(self, tmp_path):
        """替换后的 Markdown 必须保留原始 alt 文本"""
        from modules.mcp.image_extractor import extract_inline_images

        raw = b'\x89PNG' + b'\x00' * 8
        content = f'![我的示意图]({_make_data_uri("image/png", raw)})\n'

        new_content, _ = extract_inline_images(content, str(tmp_path))

        assert '![我的示意图]' in new_content
