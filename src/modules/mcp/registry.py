"""MCP 工具注册表。

每个工具用 dataclass 描述元信息（name/description/input_schema/cost），
handler 是一个 Callable[[dict], dict]，接收参数返回 MCP 响应内容。

tools/list 直接序列化 TOOL_REGISTRY（去掉 handler 字段）。
tools/call 按 name 查找后调用 handler。
"""
from dataclasses import dataclass, field, asdict
from typing import Callable, Dict, List, Optional


ToolHandler = Callable[[Dict], Dict]


@dataclass
class Tool:
    name: str
    description: str           # 给 LLM 看的，< 100 字，说明意图/成本/安全
    input_schema: Dict         # JSON Schema 描述入参
    handler: ToolHandler       # params → {content: [...]} 或 {isError: True}
    cost: str = 'none'         # "none" | "openai-embedding" | "openai-llm"

    def to_public_dict(self) -> Dict:
        """tools/list 响应用的字典（去掉 handler）。"""
        return {
            'name': self.name,
            'description': self.description,
            'inputSchema': self.input_schema,
            'cost': self.cost,
        }


# 全局工具注册表（在 tools_*.py 模块导入时填充）
TOOL_REGISTRY: List[Tool] = []
_TOOL_INDEX: Dict[str, Tool] = {}


def register_tool(tool: Tool) -> None:
    """注册一个工具。重复 name 抛 ValueError。"""
    if tool.name in _TOOL_INDEX:
        raise ValueError(f'工具已注册: {tool.name}')
    TOOL_REGISTRY.append(tool)
    _TOOL_INDEX[tool.name] = tool


def get_tool(name: str) -> Optional[Tool]:
    """按 name 查找工具。"""
    return _TOOL_INDEX.get(name)


def list_tools() -> List[Tool]:
    """返回所有已注册工具。"""
    return list(TOOL_REGISTRY)


def clear_registry() -> None:
    """清空注册表（测试用）。"""
    TOOL_REGISTRY.clear()
    _TOOL_INDEX.clear()
