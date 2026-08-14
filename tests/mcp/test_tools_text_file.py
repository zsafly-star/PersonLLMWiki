"""MCP save_text_file 工具测试。

覆盖设计方案 MCP_通用文本写入工具设计方案.md：
- overwrite 模式：原子写入，覆盖已有文件
- append 模式：追加到文件末尾
- 路径越界检测（默认锚定 ARTICLE_PATH，与 write_note 同根）
- root 参数：article（默认）/ resource
- 参数校验（path/content 缺省、mode 非法值）
- 支持非 .md 扩展名（.json / .csv / .txt，需 root="resource"）
"""
import os
import sys

import pytest

_SRC_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)


def _call(app, args):
    """Helper: 在 app context 中调用 handle_save_text_file。"""
    from modules.mcp.tools_write import handle_save_text_file
    with app.app_context():
        return handle_save_text_file(args)


def _text(result):
    """提取响应中的 text 内容。"""
    return result['content'][0]['text']


class TestSaveTextFileOverwrite:

    def test_overwrite_creates_file(self, app):
        """默认 root="article"，写入 ARTICLE_PATH 下。"""
        result = _call(app, {
            'path': 'notes/draft.md',
            'content': '# Hello World\n',
        })
        assert 'isError' not in result
        assert 'created' in _text(result)

        article_path = app.config['ARTICLE_PATH']
        file_path = os.path.join(article_path, 'notes', 'draft.md')
        assert os.path.isfile(file_path)
        with open(file_path, 'r', encoding='utf-8') as f:
            assert f.read() == '# Hello World\n'

    def test_overwrite_overwrites_existing(self, app):
        article_path = app.config['ARTICLE_PATH']
        os.makedirs(os.path.join(article_path, 'notes'), exist_ok=True)
        file_path = os.path.join(article_path, 'notes', 'exist.md')
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write('old content')

        result = _call(app, {
            'path': 'notes/exist.md',
            'content': 'new content',
        })
        assert 'isError' not in result

        with open(file_path, 'r', encoding='utf-8') as f:
            assert f.read() == 'new content'

    def test_overwrite_atomic_does_not_corrupt_on_error(self, app, monkeypatch):
        """覆盖写入中途异常时原文件不受影响。"""
        article_path = app.config['ARTICLE_PATH']
        file_path = os.path.join(article_path, 'atomic.md')
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write('original')

        monkeypatch.setattr(os, 'replace', lambda src, dst: (_ for _ in ()).throw(OSError('simulated')))

        with pytest.raises(Exception):
            _call(app, {
                'path': 'atomic.md',
                'content': 'corrupted',
            })

        with open(file_path, 'r', encoding='utf-8') as f:
            assert f.read() == 'original'

    def test_overwrite_auto_creates_parent_dir(self, app):
        result = _call(app, {
            'path': 'deep/nested/folder/file.md',
            'content': 'deep',
        })
        assert 'isError' not in result

        article_path = app.config['ARTICLE_PATH']
        file_path = os.path.join(article_path, 'deep', 'nested', 'folder', 'file.md')
        assert os.path.isfile(file_path)

    def test_overwrite_without_create_folders_fails(self, app):
        from modules.mcp.errors import MCPError
        with pytest.raises(MCPError) as exc:
            _call(app, {
                'path': 'nonexistent/dir/file.md',
                'content': 'content',
                'create_folders': False,
            })
        assert exc.value.code == -32602
        assert '父目录不存在' in str(exc.value)

    def test_overwrite_with_resource_root(self, app):
        """root="resource" 锚定 RESOURCE_BASE_PATH。"""
        result = _call(app, {
            'path': 'data/export.md',
            'content': '# resource root',
            'root': 'resource',
        })
        assert 'isError' not in result

        resource_path = app.config['RESOURCE_BASE_PATH']
        file_path = os.path.join(resource_path, 'data', 'export.md')
        assert os.path.isfile(file_path)


class TestSaveTextFileAppend:

    def test_append_to_existing(self, app):
        """默认 root="article"，向已有文章追加内容。"""
        article_path = app.config['ARTICLE_PATH']
        file_path = os.path.join(article_path, 'append.md')
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write('line1\n')

        result = _call(app, {
            'path': 'append.md',
            'content': 'line2\n',
            'mode': 'append',
        })
        assert 'isError' not in result

        with open(file_path, 'r', encoding='utf-8') as f:
            assert f.read() == 'line1\nline2\n'

    def test_append_creates_if_not_exists(self, app):
        result = _call(app, {
            'path': 'new_append.md',
            'content': 'first chunk\n',
            'mode': 'append',
        })
        assert 'isError' not in result

        article_path = app.config['ARTICLE_PATH']
        file_path = os.path.join(article_path, 'new_append.md')
        assert os.path.isfile(file_path)
        with open(file_path, 'r', encoding='utf-8') as f:
            assert f.read() == 'first chunk\n'

    def test_append_multiple_chunks(self, app):
        """模拟超长文档分块追加到知识库文章场景。"""
        article_path = app.config['ARTICLE_PATH']
        file_path = os.path.join(article_path, 'long.md')

        # 首次覆盖创建（模拟 write_note 先写入前几章）
        _call(app, {
            'path': 'long.md',
            'content': '# Title\n\n',
            'mode': 'overwrite',
        })

        # 分块追加后续章节
        _call(app, {'path': 'long.md', 'content': '## Section 1\n\n', 'mode': 'append'})
        _call(app, {'path': 'long.md', 'content': 'content 1\n\n', 'mode': 'append'})
        _call(app, {'path': 'long.md', 'content': '## Section 2\n\n', 'mode': 'append'})
        _call(app, {'path': 'long.md', 'content': 'content 2\n', 'mode': 'append'})

        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert content == '# Title\n\n## Section 1\n\ncontent 1\n\n## Section 2\n\ncontent 2\n'

    def test_append_same_root_as_write_note(self, app):
        """验证 save_text_file append 写入与 write_note 同物理文件。"""
        from modules.mcp.tools_write import handle_write_note

        with app.app_context():
            # write_note 创建文章
            handle_write_note({
                'path': 'shared/article.md',
                'content': 'Chapter 1 content.\n',
            })

            # save_text_file 追加
            handle_save_text_file = _import_handler()
            handle_save_text_file({
                'path': 'shared/article.md',
                'content': 'Chapter 2 content.\n',
                'mode': 'append',
            })

        # 验证两个工具写入同一文件
        article_path = app.config['ARTICLE_PATH']
        file_path = os.path.join(article_path, 'shared', 'article.md')
        with open(file_path, 'r', encoding='utf-8') as f:
            assert f.read() == 'Chapter 1 content.\nChapter 2 content.\n'


def _import_handler():
    from modules.mcp.tools_write import handle_save_text_file
    return handle_save_text_file


class TestSaveTextFilePathSecurity:

    def test_path_traversal_rejected(self, app):
        from modules.mcp.errors import MCPError
        with pytest.raises(MCPError) as exc:
            _call(app, {
                'path': '../../../etc/passwd',
                'content': 'evil',
            })
        assert exc.value.code == -32602

    def test_windows_absolute_path_rejected(self, app):
        from modules.mcp.errors import MCPError
        with pytest.raises(MCPError):
            _call(app, {
                'path': 'C:\\Windows\\system32\\evil.txt',
                'content': 'evil',
            })

    def test_empty_path_rejected(self, app):
        from modules.mcp.errors import MCPError
        with pytest.raises(MCPError) as exc:
            _call(app, {
                'path': '',
                'content': 'content',
            })
        assert exc.value.code == -32602


class TestSaveTextFileParamValidation:

    def test_missing_path(self, app):
        from modules.mcp.errors import MCPError
        with pytest.raises(MCPError) as exc:
            _call(app, {'content': 'hello'})
        assert exc.value.code == -32602

    def test_missing_content(self, app):
        from modules.mcp.errors import MCPError
        with pytest.raises(MCPError) as exc:
            _call(app, {'path': 'test.md'})
        assert exc.value.code == -32602

    def test_content_not_string(self, app):
        from modules.mcp.errors import MCPError
        with pytest.raises(MCPError) as exc:
            _call(app, {'path': 'test.md', 'content': 123})
        assert exc.value.code == -32602

    def test_invalid_mode(self, app):
        from modules.mcp.errors import MCPError
        with pytest.raises(MCPError) as exc:
            _call(app, {'path': 'test.md', 'content': 'x', 'mode': 'superwrite'})
        assert exc.value.code == -32602

    def test_invalid_root(self, app):
        from modules.mcp.errors import MCPError
        with pytest.raises(MCPError) as exc:
            _call(app, {'path': 'test.md', 'content': 'x', 'root': 'invalid'})
        assert exc.value.code == -32602


class TestSaveTextFileNonMd:

    def test_write_json(self, app):
        result = _call(app, {
            'path': 'data/config.json',
            'content': '{"key": "value"}',
            'root': 'resource',
        })
        assert 'isError' not in result

        resource_path = app.config['RESOURCE_BASE_PATH']
        file_path = os.path.join(resource_path, 'data', 'config.json')
        assert os.path.isfile(file_path)
        with open(file_path, 'r', encoding='utf-8') as f:
            assert f.read() == '{"key": "value"}'

    def test_write_csv(self, app):
        result = _call(app, {
            'path': 'export/data.csv',
            'content': 'name,age\nAlice,30\n',
            'root': 'resource',
        })
        assert 'isError' not in result

        resource_path = app.config['RESOURCE_BASE_PATH']
        file_path = os.path.join(resource_path, 'export', 'data.csv')
        assert os.path.isfile(file_path)

    def test_write_txt_resource_root(self, app):
        result = _call(app, {
            'path': 'notes/readme.txt',
            'content': 'Plain text content.',
            'root': 'resource',
        })
        assert 'isError' not in result

        resource_path = app.config['RESOURCE_BASE_PATH']
        file_path = os.path.join(resource_path, 'notes', 'readme.txt')
        assert os.path.isfile(file_path)


class TestSaveTextFileReturn:

    def test_return_contains_expected_fields(self, app):
        result = _call(app, {
            'path': 'meta/check.md',
            'content': 'test content',
        })
        assert 'isError' not in result
        text = result['content'][0]['text']
        assert 'path' in text
        assert 'bytes_written' in text
        assert 'total_bytes' in text
        assert 'mode' in text
        assert 'created' in text
        assert 'overwrite' in text
        assert 'true' in text  # created

    def test_return_indicates_created_false_for_existing(self, app):
        article_path = app.config['ARTICLE_PATH']
        file_path = os.path.join(article_path, 'existing.md')
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write('existing')

        result = _call(app, {
            'path': 'existing.md',
            'content': 'overwritten',
        })
        text = _text(result)
        assert '"created": false' in text
