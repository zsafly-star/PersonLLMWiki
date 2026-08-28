"""记忆节点入图：把 decision 或带关联实体的记忆作为第二类节点并入知识星链图谱。"""


def _norm(s):
    return s.lower().replace(' ', '_').replace('/', '_')


def collect_memory_nodes():
    """扫 list_memories()，纳入 status != revoked 且 (kind=='decision' 或 related_entities 非空) 的记忆。"""
    from modules.memory.storage import list_memories

    nodes = []
    for m in list_memories():
        if m.get('status') == 'revoked':
            continue
        related = m.get('related_entities') or []
        if m.get('kind') != 'decision' and not related:
            continue
        slug = m.get('slug', '')
        nodes.append({
            'id': 'mem:' + slug,
            'title': slug,
            'kind': 'memory',
            'size': len(related) + 1,
            'related': [_norm(e) for e in related],
        })
    return nodes


def build_memory_edges(memory_nodes, wiki_slug_set):
    """对每个记忆节点的每个 related 实体归一后匹配 wiki slug 或另一记忆节点，生成去重、无自环的边。"""
    normalized_wiki = {}
    for s in wiki_slug_set:
        normalized_wiki[_norm(s)] = s

    mem_by_norm = {}
    for mn in memory_nodes:
        mem_by_norm[_norm(mn['title'])] = mn['id']

    edges = []
    seen = set()
    for mn in memory_nodes:
        mem_id = mn['id']
        for e in mn.get('related', []):
            e_norm = _norm(e)
            if e_norm in normalized_wiki:
                target = normalized_wiki[e_norm]
            elif e_norm in mem_by_norm:
                target = mem_by_norm[e_norm]
            else:
                continue
            if target == mem_id:
                continue
            edge_key = tuple(sorted([mem_id, target]))
            if edge_key in seen:
                continue
            seen.add(edge_key)
            edges.append({'source': mem_id, 'target': target})
    return edges
