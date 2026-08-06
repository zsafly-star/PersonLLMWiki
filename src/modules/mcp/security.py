"""MCP 路径安全工具函数。

实现设计方案 7.1 / 7.2：
- resolve_article_path: 路径规范化 + commonpath 越界检测
- validate_markdown_extension: 扩展名白名单（仅 .md）

所有写工具的 path 入参必须先经过这两个函数校验。
"""
import os

from flask import current_app

from .errors import INVALID_PARAMS, MCPError


# 写入允许的扩展名白名单
_ALLOWED_EXTENSIONS = {'.md'}


def _get_article_root() -> str:
    """获取 article 根目录的绝对路径。

    优先从 Flask config 读，兼容直接 import config 的场景。
    """
    try:
        root = current_app.config.get('ARTICLE_PATH')
    except RuntimeError:
        # 无 app context 时回退到 Config
        from config import Config
        root = Config.ARTICLE_PATH
    return os.path.abspath(root)


def resolve_article_path(rel_path: str) -> str:
    """把相对路径解析为 article 根目录内的绝对路径。

    校验：
    1. 非空
    2. 规范化后必须仍在 article 根目录内（commonpath 校验）

    Args:
        rel_path: 相对于 article 根目录的路径，例如 '工作/会议.md'

    Returns:
        解析后的绝对路径

    Raises:
        MCPError(-32602): 路径越界或非法
    """
    if not rel_path or not isinstance(rel_path, str):
        raise MCPError(INVALID_PARAMS, 'path 不能为空')

    article_root = _get_article_root()

    # 把 Windows/Unix 分隔符都规范化
    # 先把反斜杠转成正斜杠再 normpath，避免路径注入
    normalized_rel = rel_path.replace('\\', os.sep).replace('/', os.sep)
    candidate = os.path.normpath(os.path.join(article_root, normalized_rel))
    candidate_abs = os.path.abspath(candidate)

    # commonpath 校验：解析后的路径必须仍在 article_root 内
    try:
        common = os.path.commonpath([article_root, candidate_abs])
    except ValueError:
        # 跨盘符（Windows）或不同根（Unix）→ commonpath 抛 ValueError
        raise MCPError(INVALID_PARAMS, '路径越界')

    if common != article_root:
        raise MCPError(INVALID_PARAMS, '路径越界')

    return candidate_abs


def validate_markdown_extension(filename: str) -> None:
    """校验文件名扩展名必须在白名单内（.md）。

    Args:
        filename: 文件名（或带路径的字符串，取 basename 后校验）

    Raises:
        MCPError(-32602): 扩展名不在白名单
    """
    if not filename:
        raise MCPError(INVALID_PARAMS, '文件名不能为空')

    basename = os.path.basename(filename)
    _, ext = os.path.splitext(basename)
    if ext.lower() not in _ALLOWED_EXTENSIONS:
        raise MCPError(
            INVALID_PARAMS,
            f'不允许的扩展名: {ext or "(无)"}，只允许 .md',
        )
