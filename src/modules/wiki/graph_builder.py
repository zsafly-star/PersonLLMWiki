"""知识星链图谱邻接构建 — 消除 MCP tools_read 与 wiki routes 之间的双端点漂移。

提供：
- normalize_link(link_str, slug_set, slug_title_map) → 命中返回 slug，否则 None（3 级匹配）；
- build_adjacency(pages) → (adjacency: dict[slug -> set[slug]], slug_title_map: dict)，
  从 WikiPage.links 双向建邻接。
"""
import json


def normalize_link(link_str, slug_set, slug_title_map):
    """把一条 WikiPage.links 里的链接字符串规范化为 slug（3 级匹配）。

    1. 精确：lower + 空格/斜杠 → _ 后命中 slug_set；
    2. 标题包含：link_str 与标题互相包含；
    3. slug 包含：规范化的 target 与 slug 互相包含。

    命中返回 slug，否则 None。
    """
    target = link_str.lower().replace(' ', '_').replace('/', '_')
    if target in slug_set:
        return target

    for s in slug_set:
        title = slug_title_map.get(s, '')
        if link_str in title or title in link_str:
            return s

    for s in slug_set:
        if target in s or s in target:
            return s

    return None


def build_adjacency(pages):
    """从 WikiPage.links 双向构建邻接表。

    Args:
        pages: WikiPage ORM 对象序列（有 .slug/.title/.links 属性）

    Returns:
        (adjacency, slug_title_map)
    """
    slug_set = {p.slug for p in pages}
    slug_title_map = {p.slug: p.title for p in pages}

    adjacency = {p.slug: set() for p in pages}
    for p in pages:
        links = json.loads(p.links) if p.links else []
        for link in links:
            target_slug = normalize_link(link, slug_set, slug_title_map)
            if target_slug and target_slug != p.slug:
                adjacency[p.slug].add(target_slug)
                if target_slug in adjacency:
                    adjacency[target_slug].add(p.slug)

    return adjacency, slug_title_map
