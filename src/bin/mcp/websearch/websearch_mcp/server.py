"""websearch MCP Server。

使用 DuckDuckGo Lite 联网搜索，免费无需 API Key。
基于 FastMCP 框架，通过 streamable-http 传输协议提供 MCP 工具。

自包含：无第三方依赖（仅使用标准库 urllib + fastmcp）。
"""
import json
import re
import urllib.parse
import urllib.request
from html import unescape
from typing import Any

from fastmcp import FastMCP

from . import __version__

# DuckDuckGo Lite 搜索 URL
_DDGLITE_URL = 'https://lite.duckduckgo.com/lite/'
_REQUEST_TIMEOUT = 10
_USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'

mcp = FastMCP(
    name="websearch",
    version=__version__,
    instructions=(
        "联网搜索工具，通过 DuckDuckGo 获取最新网络资料。"
        "当知识库中没有相关信息或需要最新数据时使用。"
    ),
)


def _ddg_lite_search(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """通过 DuckDuckGo Lite 搜索，返回 [{title, url, snippet}]。"""
    data = urllib.parse.urlencode({
        'q': query,
        'kl': 'cn-zh',
    }).encode('utf-8')
    req = urllib.request.Request(
        _DDGLITE_URL,
        data=data,
        headers={
            'User-Agent': _USER_AGENT,
            'Content-Type': 'application/x-www-form-urlencoded',
        },
    )
    resp = urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT)
    html = resp.read().decode('utf-8', errors='replace')

    results: list[dict[str, str]] = []
    rows = re.findall(
        r'<a\s+rel="nofollow"\s+href="([^"]+)"[^>]*>(.*?)</a>'
        r'.*?<td\s+class="result-snippet"[^>]*>(.*?)</td>',
        html, re.DOTALL,
    )
    for url, title_html, snippet_html in rows[:max_results]:
        title = unescape(re.sub(r'<[^>]+>', '', title_html)).strip()
        snippet = unescape(re.sub(r'<[^>]+>', '', snippet_html)).strip()
        if url.startswith('http') and 'duckduckgo.com' not in url:
            results.append({'title': title, 'url': url, 'snippet': snippet})

    return results


@mcp.tool(
    description=(
        "联网搜索（DuckDuckGo）。当知识库中没有相关信息、或用户明确要求查询最新资料时使用。"
        "返回搜索结果的标题、链接和摘要。每次调用会访问互联网。"
    )
)
def web_search(query: str, max_results: int = 5) -> dict[str, Any]:
    """联网搜索最新资料。

    Args:
        query: 搜索关键词
        max_results: 最大结果数（默认5，最大10）

    Returns:
        包含搜索结果列表的字典，或错误信息
    """
    query = query.strip()
    if not query:
        return {"error": "query 不能为空"}

    max_results = min(max(max_results, 1), 10)

    try:
        results = _ddg_lite_search(query, max_results)
    except Exception as e:
        return {"error": f"联网搜索失败: {e}"}

    if not results:
        return {"results": [], "message": f'未找到与"{query}"相关的搜索结果。'}

    return {"results": results, "count": len(results)}
