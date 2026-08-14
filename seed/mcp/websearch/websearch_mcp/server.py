"""websearch MCP Server。

使用 Bing RSS 联网搜索，免费无需 API Key。
基于 FastMCP 框架，通过 streamable-http 传输协议提供 MCP 工具。

自包含：无第三方依赖（仅使用标准库 urllib + xml + fastmcp）。
"""
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html import unescape
from typing import Any

from fastmcp import FastMCP

from . import __version__

# Bing RSS 搜索 URL
_BING_RSS_URL = 'https://www.bing.com/search?format=rss'
_REQUEST_TIMEOUT = 10
_USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'

mcp = FastMCP(
    name="websearch",
    version=__version__,
    instructions=(
        "联网搜索工具，通过 Bing 获取最新网络资料。"
        "当知识库中没有相关信息或需要最新数据时使用。"
    ),
)


def _bing_rss_search(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """通过 Bing RSS 搜索，返回 [{title, url, snippet}]。"""
    params = urllib.parse.urlencode({
        'q': query,
        'setlang': 'zh-cn',
    })
    url = f'{_BING_RSS_URL}&{params}'
    req = urllib.request.Request(
        url,
        headers={'User-Agent': _USER_AGENT},
    )
    resp = urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT)
    xml = resp.read().decode('utf-8', errors='replace')

    # 清理非法 XML 字符
    xml_clean = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', xml)
    root = ET.fromstring(xml_clean)

    results: list[dict[str, str]] = []
    for item in root.findall('.//item')[:max_results]:
        title_el = item.find('title')
        link_el = item.find('link')
        desc_el = item.find('description')
        title = unescape(title_el.text or '').strip() if title_el is not None else ''
        link = link_el.text.strip() if link_el is not None and link_el.text else ''
        snippet = unescape(desc_el.text or '').strip() if desc_el is not None else ''
        if link.startswith('http') and 'bing.com' not in link:
            results.append({'title': title, 'url': link, 'snippet': snippet})

    return results


@mcp.tool(
    description=(
        "联网搜索（Bing）。当知识库中没有相关信息、或用户明确要求查询最新资料时使用。"
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
        results = _bing_rss_search(query, max_results)
    except Exception as e:
        return {"error": f"联网搜索失败: {e}"}

    if not results:
        return {"results": [], "message": f'未找到与"{query}"相关的搜索结果。'}

    return {"results": results, "count": len(results)}
