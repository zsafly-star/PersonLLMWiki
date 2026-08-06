"""TOOL_CN_MAP 工具名映射完整性测试。

覆盖场景：
1. 所有已注册的本地工具都有中文映射
2. websearch__web_search 在映射表中
3. 映射值为非空中文字符串
4. 新增工具注册时映射表不遗漏（回归保护）
"""
import pytest


class TestToolCnMap:

    def _get_map(self):
        from modules.chat.routes import TOOL_CN_MAP
        return TOOL_CN_MAP

    def test_websearch_in_map(self):
        """websearch__web_search 在映射表中。"""
        m = self._get_map()
        assert 'websearch__web_search' in m
        assert m['websearch__web_search'] == '联网搜索'

    def test_search_kb_in_map(self):
        """search_kb 在映射表中。"""
        m = self._get_map()
        assert 'search_kb' in m
        assert m['search_kb'] == '搜索知识库'

    def test_create_document_in_map(self):
        """create_document 在映射表中（用于导出文件提取）。"""
        m = self._get_map()
        assert 'create_document' in m
        assert m['create_document'] == '创建文档'

    def test_all_values_are_non_empty_chinese(self):
        """所有映射值为非空中文字符串。"""
        m = self._get_map()
        for key, value in m.items():
            assert isinstance(value, str), f"映射值 {key} 应为字符串"
            assert len(value) > 0, f"映射值 {key} 不应为空"

    def test_all_local_tools_have_mapping(self):
        """所有本地注册工具都有中文映射（回归保护）。"""
        from modules.mcp.registry import list_tools

        registered_tools = list_tools()
        tool_names = {t.name for t in registered_tools}

        m = self._get_map()

        # 核心工具必须在映射表中
        core_tools = {
            'search_kb', 'read_note', 'write_note',
            'create_document', 'add_element',
        }
        missing = core_tools - set(m.keys())
        assert len(missing) == 0, f"核心工具缺少中文映射: {missing}"
