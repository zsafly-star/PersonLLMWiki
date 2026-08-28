"""MCP 技能候选工具（只写候选，人工审批，LLM 不可自审批）。"""

from .errors import INVALID_PARAMS, MCPError
from .tools_common import text_content, error_content


def handle_suggest_skill(args: dict) -> dict:
    """生成技能候选草案。{name, description, body} 均必填。"""
    name = args.get('name')
    description = args.get('description')
    body = args.get('body')

    if not name or not description or not body:
        raise MCPError(INVALID_PARAMS, 'name、description、body 均为必填')

    if '\n' in description or '\r' in description:
        raise MCPError(INVALID_PARAMS, 'description 必须为单行文本（不能包含换行）')

    from common.skill_loader import save_skill_candidate

    try:
        path = save_skill_candidate(name, description, body)
    except ValueError as e:
        raise MCPError(INVALID_PARAMS, str(e))

    return text_content({'name': name, 'path': path, 'status': 'candidate'})
