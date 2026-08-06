"""MCP 路径安全工具函数测试。

覆盖设计方案 7.1 / 7.2：
- commonpath 越界检测：所有 path 入参必须解析到 article 根目录内
- 扩展名白名单：write_note 只允许 .md
"""
import os
import sys

import pytest

# 确保能 import modules.mcp.security
_SRC_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)


class TestResolveArticlePath:

    def test_relative_path_resolves_under_article_root(self, app):
        from modules.mcp.security import resolve_article_path
        with app.app_context():
            resolved = resolve_article_path('工作/会议.md')
        assert resolved.endswith(os.path.join('article', '工作', '会议.md'))

    def test_parent_traversal_is_rejected(self, app):
        from modules.mcp.security import resolve_article_path
        from modules.mcp.errors import MCPError
        with app.app_context():
            with pytest.raises(MCPError) as exc:
                resolve_article_path('../../../etc/passwd')
            assert exc.value.code == -32602

    def test_absolute_path_outside_root_is_rejected(self, app):
        from modules.mcp.security import resolve_article_path
        from modules.mcp.errors import MCPError
        with app.app_context():
            with pytest.raises(MCPError):
                # 构造一个绝对路径指向根目录之外
                resolve_article_path(os.path.abspath(__file__))

    def test_windows_absolute_path_is_rejected(self, app):
        from modules.mcp.security import resolve_article_path
        from modules.mcp.errors import MCPError
        with app.app_context():
            with pytest.raises(MCPError):
                resolve_article_path('C:\\Windows\\system32\\evil.md')

    def test_unix_absolute_path_is_rejected(self, app):
        from modules.mcp.security import resolve_article_path
        from modules.mcp.errors import MCPError
        with app.app_context():
            with pytest.raises(MCPError):
                resolve_article_path('/etc/passwd')

    def test_empty_path_is_rejected(self, app):
        from modules.mcp.security import resolve_article_path
        from modules.mcp.errors import MCPError
        with app.app_context():
            with pytest.raises(MCPError):
                resolve_article_path('')

    def test_path_with_only_dots_is_rejected(self, app):
        from modules.mcp.security import resolve_article_path
        from modules.mcp.errors import MCPError
        with app.app_context():
            with pytest.raises(MCPError):
                resolve_article_path('..')

    def test_normal_nested_path_passes(self, app):
        from modules.mcp.security import resolve_article_path
        with app.app_context():
            resolved = resolve_article_path('a/b/c/note.md')
        assert resolved.endswith(os.path.join('a', 'b', 'c', 'note.md'))

    def test_backslash_path_is_normalized(self, app):
        """Windows 风格反斜杠路径应能正确规范化。"""
        from modules.mcp.security import resolve_article_path
        with app.app_context():
            resolved = resolve_article_path('工作\\会议.md')
        # 应该能解析到 article 根目录内
        assert 'article' in resolved


class TestValidateMarkdownExtension:

    def test_md_extension_passes(self, app):
        from modules.mcp.security import validate_markdown_extension
        with app.app_context():
            validate_markdown_extension('note.md')

    def test_py_extension_is_rejected(self, app):
        from modules.mcp.security import validate_markdown_extension
        from modules.mcp.errors import MCPError
        with app.app_context():
            with pytest.raises(MCPError):
                validate_markdown_extension('evil.py')

    def test_sh_extension_is_rejected(self, app):
        from modules.mcp.security import validate_markdown_extension
        from modules.mcp.errors import MCPError
        with app.app_context():
            with pytest.raises(MCPError):
                validate_markdown_extension('evil.sh')

    def test_exe_extension_is_rejected(self, app):
        from modules.mcp.security import validate_markdown_extension
        from modules.mcp.errors import MCPError
        with app.app_context():
            with pytest.raises(MCPError):
                validate_markdown_extension('evil.exe')

    def test_no_extension_is_rejected(self, app):
        from modules.mcp.security import validate_markdown_extension
        from modules.mcp.errors import MCPError
        with app.app_context():
            with pytest.raises(MCPError):
                validate_markdown_extension('README')

    def test_uppercase_md_extension_passes(self, app):
        from modules.mcp.security import validate_markdown_extension
        with app.app_context():
            validate_markdown_extension('NOTE.MD')

    def test_double_extension_is_rejected(self, app):
        """md.exe.exe 等不应绕过。"""
        from modules.mcp.security import validate_markdown_extension
        from modules.mcp.errors import MCPError
        with app.app_context():
            with pytest.raises(MCPError):
                validate_markdown_extension('evil.md.exe')
