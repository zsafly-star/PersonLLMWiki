"""记忆注入：对话开场把相关记忆拼成 system 上下文。"""


def inject_memory_context(user_message, top_k=3):
    """调 search_memory → 无结果返回 ''；否则拼成记忆块文本返回。"""
    from modules.memory.retrieval import search_memory

    results = search_memory(user_message, top_k=top_k)
    if not results:
        return ''

    lines = ['【记忆】以下是与你相关的过往记忆，请参考：']
    for r in results:
        body = (r.get('body', '') or '')[:200]
        lines.append('- [' + str(r.get('kind', 'other')) + '] ' + body)
    return '\n'.join(lines)
