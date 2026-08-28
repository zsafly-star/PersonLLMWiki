import json
import os
import threading
import logging
from datetime import datetime, timezone

from config import Config
from modules.memory.storage import ensure_memory_dirs

_logger = logging.getLogger(__name__)

# 模块级锁，保护 JSONL 文件追加（Flask 请求线程与 agent 线程可能并发写）
_write_lock = threading.Lock()


def _ts():
    return datetime.now(timezone.utc).isoformat()


def _write_line(session_id, obj):
    """追加一行 JSONL；失败静默（trace 不影响主对话）。"""
    try:
        ensure_memory_dirs()
        path = os.path.join(Config.MEMORIES_RAW_DIR, str(session_id) + '.jsonl')
        line = json.dumps(obj, ensure_ascii=False) + '\n'
        with _write_lock:
            with open(path, 'a', encoding='utf-8') as f:
                f.write(line)
    except Exception:
        _logger.exception('记录 trace 失败（session_id=%s）', session_id)


def record_user_message(session_id, content):
    # {"ts": iso, "type": "user_message", "session_id": sid, "content": ...}
    _write_line(session_id, {
        'ts': _ts(),
        'type': 'user_message',
        'session_id': session_id,
        'content': content,
    })


def record_tool_start(session_id, round, name, arguments):
    # {"ts": iso, "type": "tool_start", "session_id": sid, "round": n, "name": ..., "arguments": ...}
    _write_line(session_id, {
        'ts': _ts(),
        'type': 'tool_start',
        'session_id': session_id,
        'round': round,
        'name': name,
        'arguments': arguments,
    })


def record_tool_result(session_id, round, name, result):
    # {"ts": iso, "type": "tool_result", "session_id": sid, "round": n, "name": ..., "result": <截断≤500字>}
    if result is None:
        result = ''
    if not isinstance(result, str):
        result = str(result)
    if len(result) > 500:
        result = result[:500]
    _write_line(session_id, {
        'ts': _ts(),
        'type': 'tool_result',
        'session_id': session_id,
        'round': round,
        'name': name,
        'result': result,
    })


def record_session_boundary(session_id, event):
    # {"ts": iso, "type": "session_boundary", "session_id": sid, "event": "session_start"|"session_end"}
    _write_line(session_id, {
        'ts': _ts(),
        'type': 'session_boundary',
        'session_id': session_id,
        'event': event,
    })
