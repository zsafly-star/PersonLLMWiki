"""任务流水线安全策略（简化版）。

核心：
1. 节点工具白名单 —— 编排器通过 filter_tools_by_scope 只递送最小工具集。
2. 越权直接拦截 —— 白名单外的工具不会进入 LLM 可选集（function calling 天然约束）。
3. 写/导出二次确认 —— 由节点闸门（gate）承载：危险节点产出后强制人工确认。
4. 敏感数据只留指针 —— 产物落库仅存 summary/path，不存原文（见 state_store）。

这里只保留危险工具识别等被编排器实际使用的轻量工具函数。
"""

# 写 / 导出 / 删除类工具前缀（用于在闸门确认时给用户风险提示）
DANGEROUS_PREFIXES = (
    'create_', 'write_', 'save_', 'export_', 'add_', 'update_',
    'delete_', 'remove_', 'append_', 'generate_doc',
)


def is_dangerous_tool(tool_name):
    """判断工具是否属于写/导出/删除类（需要用户额外留意）。"""
    if not tool_name:
        return False
    return tool_name.startswith(DANGEROUS_PREFIXES)


def check_tool_allowed(tool_name, allowed_tools):
    """白名单校验：allowed_tools 为 None 或含 '*' 表示全部放行。

    Args:
        tool_name: 工具名
        allowed_tools: 工具名列表

    Returns:
        bool
    """
    if allowed_tools is None or '*' in allowed_tools:
        return True
    return tool_name in allowed_tools
