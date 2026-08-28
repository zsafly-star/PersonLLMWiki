"""分层上下文组装：摘要层 → 片段层 → 原文层（按需拉取）。

纯函数，不碰 DB/网络，方便单测与复用。
"""


def _est_tokens(text):
    return len(text) // 4


def assemble_layered(query, hits, budget_tokens=1500):
    """按 token 预算把命中结果组装成三层文本块。

    hits: [{slug, title, summary, snippet, source}]
    """
    if not budget_tokens or budget_tokens <= 0:
        budget_tokens = 1500

    summary_budget = int(budget_tokens * 0.10)
    snippet_budget = int(budget_tokens * 0.60)

    # --- 摘要层 ---
    summary_lines = []
    used = 0
    for h in hits:
        title = h.get('title') or h.get('slug') or ''
        summary = (h.get('summary') or '').strip()
        if not summary:
            summary = (h.get('snippet') or '')[:100]
        line = '- [' + title + '] ' + summary
        cost = _est_tokens(line)
        if used + cost > summary_budget:
            break
        summary_lines.append(line)
        used += cost

    # --- 片段层 ---
    snippet_lines = []
    used = 0
    for h in hits:
        title = h.get('title') or h.get('slug') or ''
        snippet = (h.get('snippet') or '').strip()
        source = h.get('source') or ''
        line = '- [' + title + '] ' + snippet
        if source:
            line += '（来源: ' + source + '）'
        cost = _est_tokens(line)
        if used + cost > snippet_budget:
            remaining_tokens = snippet_budget - used
            if remaining_tokens <= 0:
                break
            # 超出预算：按命中顺序截断当前片段
            snippet_lines.append(line[:remaining_tokens * 4])
            break
        snippet_lines.append(line)
        used += cost

    parts = []
    if summary_lines:
        parts.append('--- 摘要层 ---\n' + '\n'.join(summary_lines))
    if snippet_lines:
        parts.append('--- 片段层 ---\n' + '\n'.join(snippet_lines))
    parts.append('--- 原文层（按需拉取） ---\n'
                 '以上仅含摘要与片段，完整原文请按需调用 read_wiki_page / read_note 拉取。')

    return '\n\n'.join(parts)
