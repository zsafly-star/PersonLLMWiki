"""ZSSNote MCP 模块。

手写 JSON-RPC 2.0 Handler，通过 /mcp 端点把 ZSSNote 知识库
暴露给 WorkBuddy 等 MCP 客户端。零新增依赖。
"""
# 导入 routes 会顺带触发 tools_registration 注册所有工具
from . import tools_registration  # noqa: F401
from .routes import mcp_bp

__all__ = ['mcp_bp']
