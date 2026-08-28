import json
import logging
import os
import re
import time

from config import Config
from modules.memory import prompts
from modules.memory.storage import save_memory
from modules.wiki.compiler.extractor import get_llm, is_llm_error

_logger = logging.getLogger(__name__)

_last_extract_time = 0.0   # 模块级，频率限制用


def _build_trace_text(lines):
    """把 trace 行拼成可读文本（用户消息原文 + 工具名/结果摘要）。"""
    parts = []
    for obj in lines:
        t = obj.get('type')
        if t == 'user_message':
            parts.append('用户: ' + str(obj.get('content', '')))
        elif t == 'tool_start':
            args = json.dumps(obj.get('arguments', {}), ensure_ascii=False)
            parts.append('工具调用: ' + str(obj.get('name', '')) + ' ' + args)
        elif t == 'tool_result':
            parts.append('工具结果: ' + str(obj.get('name', '')) + ' ' + str(obj.get('result', '')))
        elif t == 'session_boundary':
            parts.append('会话事件: ' + str(obj.get('event', '')))
    return '\n'.join(parts)


def extract_memories(session_id):
    """读会话 trace → 拼文本 → LLM 提取 → 去重 → 写 memories/*.md（status=auto）。"""
    global _last_extract_time
    try:
        # 1. 频率限制：每分钟最多提炼 1 次
        if time.time() - _last_extract_time < 60:
            return
        _last_extract_time = time.time()

        # 2. 读 trace
        trace_path = os.path.join(Config.MEMORIES_RAW_DIR, str(session_id) + '.jsonl')
        if not os.path.isfile(trace_path):
            return

        lines = []
        tool_count = 0
        user_len = 0
        with open(trace_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                lines.append(obj)
                if obj.get('type') == 'tool_start':
                    tool_count += 1
                elif obj.get('type') == 'user_message':
                    user_len += len(str(obj.get('content', '')))

        # 3. 实质内容判断：工具调用 <1 且用户消息总长 <50 字 → 噪音会话不提炼
        if tool_count < 1 and user_len < 50:
            return

        # 4. 拼文本
        trace_text = _build_trace_text(lines)

        # 5. 调 LLM
        adapter, model = get_llm()
        messages = [{'role': 'user', 'content': prompts.MEMORY_EXTRACT_PROMPT.format(trace_text=trace_text)}]
        response = adapter.chat(messages, model=model)

        if is_llm_error(response):
            _logger.warning('记忆提炼 LLM 返回错误（session_id=%s）: %s', session_id, response)
            return

        json_match = re.search(r'\[.*\]', response, re.DOTALL)
        if not json_match:
            _logger.warning('记忆提炼无法解析 JSON 数组（session_id=%s）', session_id)
            return
        items = json.loads(json_match.group())
        if not isinstance(items, list):
            return

        # 6. 去重（同 slug 保留首条）
        seen = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            kind = item.get('kind')
            slug = item.get('slug')
            content = item.get('content', '')
            if not kind or not slug or not content:
                continue
            if slug in seen:
                continue
            seen.add(slug)

            summary = item.get('summary', '') or content[:100]
            if kind == 'decision':
                save_memory(slug, content, kind=kind, status='auto',
                            source_chat_id=session_id, summary=summary,
                            basis=item.get('basis', ''),
                            source_refs=item.get('source_refs', []),
                            related_entities=item.get('related_entities', []))
            else:
                save_memory(slug, content, kind=kind, status='auto',
                            source_chat_id=session_id, summary=summary)

            try:
                from modules.memory.retrieval import update_memory_embedding
                update_memory_embedding(slug)
            except Exception:
                pass
    except Exception:
        _logger.exception('记忆提炼失败（session_id=%s）', session_id)
