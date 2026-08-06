"""MCP 工具 handler 测试：list_folders / read_note / write_note。

验证：
- 入参校验（required 字段、类型）
- 返回格式（content 数组、text 字段、JSON 结构）
- 路径安全（越界路径被拒绝）
- 真实文件系统行为（不 mock service，测试真实读写）
"""
import json
import os

import pytest


def call_tool(client, name, arguments):
    """通过 /mcp 调用工具，返回 result dict。"""
    body = {
        'jsonrpc': '2.0',
        'id': 1,
        'method': 'tools/call',
        'params': {'name': name, 'arguments': arguments},
    }
    resp = client.post('/mcp', data=json.dumps(body),
                       headers={'Content-Type': 'application/json'})
    payload = resp.get_json()
    assert payload is not None, f'响应非 JSON: {resp.data!r}'
    return resp, payload


def parse_content_text(payload):
    """从 tools/call 响应里提取第一个 text content 并解析为 JSON。"""
    result = payload.get('result', {})
    assert 'content' in result, f'result 缺 content: {result}'
    text = result['content'][0]['text']
    return json.loads(text)


# ---------- list_folders ----------

class TestListFolders:

    def test_returns_top_level_folders_with_metadata(self, app, client):
        # 准备：在 article/ 下建几个文件夹
        article_root = app.config['ARTICLE_PATH']
        os.makedirs(os.path.join(article_root, '工作'))
        os.makedirs(os.path.join(article_root, '学习'))

        with app.test_request_context():
            from modules.mcp.tools_read import handle_list_folders
            result = handle_list_folders({})

        assert 'content' in result
        data = json.loads(result['content'][0]['text'])
        assert isinstance(data, list)
        names = [item['name'] for item in data]
        assert '工作' in names
        assert '学习' in names

    def test_each_folder_has_required_fields(self, app, client):
        article_root = app.config['ARTICLE_PATH']
        os.makedirs(os.path.join(article_root, '项目'))

        with app.test_request_context():
            from modules.mcp.tools_read import handle_list_folders
            result = handle_list_folders({})

        data = json.loads(result['content'][0]['text'])
        folder = next(f for f in data if f['name'] == '项目')
        assert 'name' in folder
        assert 'path' in folder

    def test_empty_article_root_returns_empty_list(self, app, client):
        with app.test_request_context():
            from modules.mcp.tools_read import handle_list_folders
            result = handle_list_folders({})
        data = json.loads(result['content'][0]['text'])
        assert data == []

    def test_ignores_files_only_returns_folders(self, app, client):
        article_root = app.config['ARTICLE_PATH']
        os.makedirs(os.path.join(article_root, '子目录'))
        # 放一个 md 文件在顶层
        with open(os.path.join(article_root, '散落笔记.md'), 'w', encoding='utf-8') as f:
            f.write('# 散落')

        with app.test_request_context():
            from modules.mcp.tools_read import handle_list_folders
            result = handle_list_folders({})
        data = json.loads(result['content'][0]['text'])
        names = [f['name'] for f in data]
        assert '子目录' in names
        # 散落的文件不应出现在 folders 列表里
        assert '散落笔记' not in names


# ---------- read_note ----------

class TestReadNote:

    def test_read_existing_note_returns_title_and_summary(self, app, client):
        article_root = app.config['ARTICLE_PATH']
        note_path = os.path.join(article_root, '测试.md')
        with open(note_path, 'w', encoding='utf-8') as f:
            f.write('# 测试标题\n\n这是正文内容。\n')

        with app.test_request_context():
            from modules.mcp.tools_read import handle_read_note
            result = handle_read_note({'path': '测试.md'})

        data = json.loads(result['content'][0]['text'])
        assert '测试标题' in data.get('title', '')
        # full 默认 false，只返回 summary
        assert '正文内容' in data.get('summary', '')
        # full=false 不应返回完整 content
        assert 'content' not in data

    def test_read_full_true_returns_complete_markdown(self, app, client):
        article_root = app.config['ARTICLE_PATH']
        os.makedirs(os.path.join(article_root, '笔记'), exist_ok=True)
        with open(os.path.join(article_root, '笔记', '完整.md'), 'w', encoding='utf-8') as f:
            f.write('# 完整文章\n\n## 章节\n\n详细内容。\n')

        with app.test_request_context():
            from modules.mcp.tools_read import handle_read_note
            result = handle_read_note({'path': '笔记/完整.md', 'full': True})

        data = json.loads(result['content'][0]['text'])
        assert '# 完整文章' in data['content']

    def test_read_nonexistent_note_returns_isError(self, app, client):
        with app.test_request_context():
            from modules.mcp.tools_read import handle_read_note
            result = handle_read_note({'path': '不存在.md'})

        assert result.get('isError') is True

    def test_read_missing_path_arg_raises_mcperror(self, app, client):
        from modules.mcp.errors import MCPError
        with app.test_request_context():
            from modules.mcp.tools_read import handle_read_note
            with pytest.raises(MCPError) as exc:
                handle_read_note({})
            assert exc.value.code == -32602

    def test_read_path_traversal_raises_mcperror(self, app, client):
        from modules.mcp.errors import MCPError
        with app.test_request_context():
            from modules.mcp.tools_read import handle_read_note
            with pytest.raises(MCPError) as exc:
                handle_read_note({'path': '../../../etc/passwd'})
            assert exc.value.code == -32602


# ---------- write_note ----------

class TestWriteNote:

    def test_create_new_note_writes_file_and_returns_path(self, app, client):
        with app.test_request_context():
            from modules.mcp.tools_write import handle_write_note
            result = handle_write_note({
                'path': '新笔记.md',
                'content': '# 新笔记\n\n内容。',
            })

        data = json.loads(result['content'][0]['text'])
        assert data['created'] is True
        assert 'path' in data

        article_root = app.config['ARTICLE_PATH']
        assert os.path.isfile(os.path.join(article_root, '新笔记.md'))

    def test_overwrite_existing_returns_created_false(self, app, client):
        article_root = app.config['ARTICLE_PATH']
        with open(os.path.join(article_root, '已存在.md'), 'w', encoding='utf-8') as f:
            f.write('# 原内容\n')

        with app.test_request_context():
            from modules.mcp.tools_write import handle_write_note
            result = handle_write_note({
                'path': '已存在.md',
                'content': '# 新内容\n',
            })

        data = json.loads(result['content'][0]['text'])
        assert data['created'] is False

        # 文件应被覆盖
        with open(os.path.join(article_root, '已存在.md'), 'r', encoding='utf-8') as f:
            assert '新内容' in f.read()

    def test_create_folders_true_creates_parent_dirs(self, app, client):
        with app.test_request_context():
            from modules.mcp.tools_write import handle_write_note
            result = handle_write_note({
                'path': '深/层/目录/笔记.md',
                'content': '# 深\n',
                'create_folders': True,
            })

        data = json.loads(result['content'][0]['text'])
        assert data['created'] is True

        article_root = app.config['ARTICLE_PATH']
        assert os.path.isfile(os.path.join(article_root, '深', '层', '目录', '笔记.md'))

    def test_create_folders_false_missing_parent_raises(self, app, client):
        from modules.mcp.errors import MCPError
        with app.test_request_context():
            from modules.mcp.tools_write import handle_write_note
            with pytest.raises(MCPError):
                handle_write_note({
                    'path': '不存在/目录/笔记.md',
                    'content': '# x\n',
                    'create_folders': False,
                })

    def test_write_path_traversal_raises(self, app, client):
        from modules.mcp.errors import MCPError
        with app.test_request_context():
            from modules.mcp.tools_write import handle_write_note
            with pytest.raises(MCPError) as exc:
                handle_write_note({
                    'path': '../../../etc/evil.md',
                    'content': 'bad',
                })
            assert exc.value.code == -32602

    def test_write_non_md_extension_raises(self, app, client):
        from modules.mcp.errors import MCPError
        with app.test_request_context():
            from modules.mcp.tools_write import handle_write_note
            with pytest.raises(MCPError) as exc:
                handle_write_note({
                    'path': 'evil.py',
                    'content': 'import os',
                })
            assert exc.value.code == -32602

    def test_write_missing_required_args_raises(self, app, client):
        from modules.mcp.errors import MCPError
        with app.test_request_context():
            from modules.mcp.tools_write import handle_write_note
            with pytest.raises(MCPError):
                handle_write_note({'path': 'x.md'})  # 缺 content
            with pytest.raises(MCPError):
                handle_write_note({'content': 'x'})  # 缺 path

    def test_write_returns_word_count(self, app, client):
        with app.test_request_context():
            from modules.mcp.tools_write import handle_write_note
            result = handle_write_note({
                'path': '字数.md',
                'content': '一二三四五',
            })
        data = json.loads(result['content'][0]['text'])
        assert 'word_count' in data
        assert data['word_count'] > 0


# ---------- write_note: 内联图片提取 ----------

class TestWriteNoteInlineImages:
    """验证 write_note 自动提取 data URI 图片到 resource/img/<文件名>/。"""

    def _make_data_uri(self, mime: str, raw: bytes):
        import base64
        b64 = base64.b64encode(raw).decode('ascii')
        return f'data:{mime};base64,{b64}'

    def test_inline_image_extracted_to_img_dir(self, app, client):
        article_root = app.config['ARTICLE_PATH']
        img_root = app.config['IMAGE_PATH']

        raw = b'\x89PNG\r\n\x1a\n' + b'\x00' * 16
        data_uri = self._make_data_uri('image/png', raw)
        content = f'# 带\n\n![图]({data_uri})\n\n正文\n'

        with app.test_request_context():
            from modules.mcp.tools_write import handle_write_note
            result = handle_write_note({
                'path': '图片笔记.md',
                'content': content,
            })

        data = json.loads(result['content'][0]['text'])
        # 返回值应包含图片信息
        assert data['images_extracted'] == 1
        assert len(data['image_paths']) == 1

        # 图片应被保存到 resource/img/图片笔记/ 下
        saved = os.path.join(img_root, '图片笔记',
                              os.path.basename(data['image_paths'][0]))
        assert os.path.isfile(saved), f'图片未保存: {saved}'

        # .md 文件里的 data URI 应被替换为相对路径
        md_path = os.path.join(article_root, '图片笔记.md')
        with open(md_path, 'r', encoding='utf-8') as f:
            saved_md = f.read()
        assert 'base64' not in saved_md
        assert os.path.basename(data['image_paths'][0]) in saved_md

    def test_image_dir_named_after_md_filename(self, app, client):
        """目录名取自 .md 文件名（不含路径、不含扩展名）。"""
        img_root = app.config['IMAGE_PATH']

        raw = b'\x89PNG' + b'\x00' * 8
        content = f'![]({self._make_data_uri("image/png", raw)})\n'

        with app.test_request_context():
            from modules.mcp.tools_write import handle_write_note
            result = handle_write_note({
                'path': '工作/子目录/报告.md',
                'content': content,
                'create_folders': True,
            })

        data = json.loads(result['content'][0]['text'])
        # 目录名应是 "报告"，不是完整路径
        img_path = data['image_paths'][0]
        assert '报告' in img_path
        assert '子目录' not in img_path
        # 实际目录存在
        assert os.path.isdir(os.path.join(img_root, '报告'))

    def test_multiple_images_all_extracted(self, app, client):
        img_root = app.config['IMAGE_PATH']

        raw1 = b'\x89PNG' + b'\x01' * 8
        raw2 = b'\x89PNG' + b'\x02' * 8
        content = (
            f'![]({self._make_data_uri("image/png", raw1)})\n'
            f'![]({self._make_data_uri("image/png", raw2)})\n'
        )

        with app.test_request_context():
            from modules.mcp.tools_write import handle_write_note
            result = handle_write_note({
                'path': '多图.md', 'content': content,
            })

        data = json.loads(result['content'][0]['text'])
        assert data['images_extracted'] == 2
        # 两个不同的文件
        names = [os.path.basename(p) for p in data['image_paths']]
        assert len(set(names)) == 2

    def test_no_images_returns_empty_list(self, app, client):
        with app.test_request_context():
            from modules.mcp.tools_write import handle_write_note
            result = handle_write_note({
                'path': '无图.md',
                'content': '# 纯文本\n\n![](img/existing.png)\n',
            })

        data = json.loads(result['content'][0]['text'])
        assert data['images_extracted'] == 0
        assert data['image_paths'] == []

    def test_http_urls_not_extracted(self, app, client):
        """http(s) URL 不应被当作内联图片提取。"""
        content = '![外链](https://example.com/a.png)\n'
        with app.test_request_context():
            from modules.mcp.tools_write import handle_write_note
            result = handle_write_note({
                'path': '外链.md', 'content': content,
            })

        data = json.loads(result['content'][0]['text'])
        assert data['images_extracted'] == 0

    def test_markdown_uses_relative_img_path(self, app, client):
        """保存后的 .md 中图片路径应是 img/<文件名>/xxx.png 形式。"""
        article_root = app.config['ARTICLE_PATH']

        raw = b'\x89PNG' + b'\x00' * 8
        content = f'![示意图]({self._make_data_uri("image/png", raw)})\n'

        with app.test_request_context():
            from modules.mcp.tools_write import handle_write_note
            handle_write_note({'path': '检查.md', 'content': content})

        with open(os.path.join(article_root, '检查.md'), 'r', encoding='utf-8') as f:
            saved = f.read()

        # 应是 img/检查/xxx.png 格式
        assert '![示意图](img/检查/' in saved
        assert '.png)' in saved
