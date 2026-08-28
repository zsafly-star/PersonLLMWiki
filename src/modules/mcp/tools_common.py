"""MCP 工具共享 helper。

text_content / error_content 供各 tools_*.py 复用，消除重复实现。
"""
import json


def text_content(obj):
    """把 dict/str 包成 MCP content 响应。"""
    if isinstance(obj, str):
        text = obj
    else:
        text = json.dumps(obj, ensure_ascii=False)
    return {'content': [{'type': 'text', 'text': text}]}


def error_content(message: str):
    """构造 isError=true 的工具错误响应。"""
    return {
        'isError': True,
        'content': [{'type': 'text', 'text': message}],
    }
