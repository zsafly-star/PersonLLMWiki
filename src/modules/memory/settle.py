"""记忆「多信号沉降」通道（轨道 B）。

不依赖 agent 自觉 remember，提供自动化沉降兜底：
- stage_raw_trace()：进程级 hook 采集的原始 trace 先入 _raw/ 暂存（JSONL）；
- settle_pending_raw() / settle_if_idle()：会话空闲超时后把暂存批量沉降进 memories；
- settle_memories()：批量沉降核心，逐条近似查重（embedding + 文本兜底），
  只走自动记忆轨（status=auto、带 source），绝不自动 forget。

双轨制：沉降产物只写 memories/*.md（status=auto），不进知识库审批轨；
撤回权完全归用户（forget_memory 软删除，本模块从不调用）。
"""
import difflib
import json
import os
import re
import threading
import time
import uuid

from modules.memory.storage import (
    ensure_memory_dirs,
    get_memories_raw_dir,
    list_memories,
    save_memory,
)

_VALID_KINDS = ('preference', 'fact', 'decision', 'other')

# 语义查重阈值（search_memory 加权得分）
_DUP_SEMANTIC_THRESHOLD = 0.9
# 无 embedding 时的文本相似兜底阈值（difflib.SequenceMatcher.ratio）
_DUP_TEXT_THRESHOLD = 0.85
# 单条记忆信号正文长度上限（超长跳过，避免噪声进入沉降通道）
_MAX_BODY_LEN = 200

# 暂存文件名与空闲阈值（分钟）
_RAW_PENDING_FILENAME = 'pending.jsonl'
MEMORY_IDLE_SETTLE_MINUTES = 5

_staging_lock = threading.Lock()


def _staging_path():
    return os.path.join(get_memories_raw_dir(), _RAW_PENDING_FILENAME)


def _normalize(text):
    return re.sub(r'\s+', ' ', (text or '').strip().lower())


def _text_similarity(a, b):
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def _gen_slug(kind):
    return f"auto_{kind}_{uuid.uuid4().hex[:12]}"


def _is_duplicate(body, existing_bodies):
    """逐条近似查重：先 embedding 语义，再文本相似兜底。

    existing_bodies: 归一化后的既有记忆正文列表（含本批已写入项）。
    """
    # 1) 语义检索（embedding 未配置时安全返回空）
    try:
        from modules.memory.retrieval import search_memory
        hits = search_memory(body, top_k=3)
    except Exception:
        hits = []
    for h in hits:
        if (h.get('score') or 0) >= _DUP_SEMANTIC_THRESHOLD:
            return True

    # 2) 文本相似兜底
    norm = _normalize(body)
    if not norm:
        return True
    for mb in existing_bodies:
        if _text_similarity(norm, mb) >= _DUP_TEXT_THRESHOLD:
            return True
    return False


def _load_existing_bodies():
    """返回既有记忆的归一化正文（排除 revoked），用于近似查重。"""
    bodies = []
    for m in list_memories(include_body=True):
        if m.get('status') == 'revoked':
            continue
        b = _normalize(m.get('body') or '')
        if b:
            bodies.append(b)
    return bodies


def _read_pending_bodies():
    """读取 _raw/pending.jsonl 中暂存项的归一化正文（防重复喂养）。"""
    staging = _staging_path()
    bodies = []
    if not os.path.isfile(staging):
        return bodies
    try:
        with open(staging, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                b = _normalize(obj.get('body') or '')
                if b:
                    bodies.append(b)
    except IOError:
        pass
    return bodies


def settle_memories(items, source='idle_settle'):
    """批量沉降记忆，逐条查重后写入（status=auto、带 source）。

    返回 {'written': [...], 'skipped': [...], 'total': n}。绝不自动 forget。
    """
    ensure_memory_dirs()

    existing_bodies = _load_existing_bodies()

    written = []
    skipped = []
    if not isinstance(items, list):
        items = []

    for it in items:
        if not isinstance(it, dict):
            skipped.append({'reason': 'invalid_item', 'item': it})
            continue

        body = (it.get('body') or '').strip()
        kind = it.get('kind') or 'other'
        if kind not in _VALID_KINDS:
            skipped.append({'reason': 'invalid_kind', 'kind': kind, 'body': body[:80]})
            continue
        if not body:
            skipped.append({'reason': 'empty', 'kind': kind})
            continue

        if _is_duplicate(body, existing_bodies):
            skipped.append({'reason': 'duplicate', 'kind': kind, 'body': body[:80]})
            continue

        slug = _gen_slug(kind)
        item_source = it.get('source') or source
        try:
            save_memory(slug, body, kind=kind, status='auto', source=item_source)
        except Exception as e:
            skipped.append({'reason': 'save_error', 'kind': kind, 'error': str(e), 'body': body[:80]})
            continue

        # 增量更新向量（失败不阻断，embedding 未配置时自动降级）
        try:
            from modules.memory.retrieval import update_memory_embedding
            update_memory_embedding(slug)
        except Exception:
            pass

        existing_bodies.append(_normalize(body))
        written.append({'slug': slug, 'kind': kind, 'source': item_source})

    return {'written': written, 'skipped': skipped, 'total': len(items)}


def stage_raw_trace(items, source='trace'):
    """把原始 trace 追加到 _raw/ 暂存（JSONL），返回写入条数。"""
    ensure_memory_dirs()
    if not isinstance(items, list):
        items = []

    lines = []
    for it in items:
        if not isinstance(it, dict):
            continue
        body = (it.get('body') or '').strip()
        if not body:
            continue
        kind = it.get('kind') or 'other'
        if kind not in _VALID_KINDS:
            kind = 'other'
        lines.append(json.dumps({
            'body': body,
            'kind': kind,
            'source': it.get('source') or source,
            'ts': time.time(),
        }, ensure_ascii=False))

    if not lines:
        return 0

    with _staging_lock:
        with open(_staging_path(), 'a', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
    return len(lines)


def stage_memory_signals(items, source='signal'):
    """记忆信号的暂存入口（stage_raw_trace 的增强包装，带卫生过滤）。

    过滤规则：
    - body 去空格后非空；kind ∈ {preference,fact,decision,other}（非法跳过）；
    - body 长度 ≤ _MAX_BODY_LEN（超长跳过）；
    - 与「已有 memories + 暂存内已存在项 + 本批已暂存项」近似查重，命中跳过。

    语义「是否成型/值得记」不在此做脆弱启发式判断，交给沉降查重 + 用户一键撤回兜底。
    返回 {'staged': n, 'skipped': [...], 'total': n}。
    """
    ensure_memory_dirs()
    if not isinstance(items, list):
        items = []

    existing_bodies = _load_existing_bodies()
    with _staging_lock:
        for b in _read_pending_bodies():
            if b not in existing_bodies:
                existing_bodies.append(b)

    accepted = []
    skipped = []
    for it in items:
        if not isinstance(it, dict):
            skipped.append({'reason': 'invalid_item', 'item': it})
            continue

        body = (it.get('body') or '').strip()
        kind = it.get('kind') or 'other'
        if not body:
            skipped.append({'reason': 'empty', 'kind': kind})
            continue
        if kind not in _VALID_KINDS:
            skipped.append({'reason': 'invalid_kind', 'kind': kind, 'body': body[:80]})
            continue
        if len(body) > _MAX_BODY_LEN:
            skipped.append({'reason': 'too_long', 'kind': kind, 'body': body[:80]})
            continue
        if _is_duplicate(body, existing_bodies):
            skipped.append({'reason': 'duplicate', 'kind': kind, 'body': body[:80]})
            continue

        rec = {
            'body': body,
            'kind': kind,
            'source': it.get('source') or source,
        }
        accepted.append(rec)
        existing_bodies.append(_normalize(body))

    if accepted:
        stage_raw_trace(accepted, source=source)

    return {'staged': len(accepted), 'skipped': skipped, 'total': len(items)}


def settle_pending_raw(source='idle_settle'):
    """把 _raw/ 暂存全部沉降进 memories，成功后清空暂存。"""
    staging = _staging_path()
    with _staging_lock:
        if not os.path.isfile(staging):
            return {'written': [], 'skipped': [], 'total': 0, 'settled': 0}

        items = []
        try:
            with open(staging, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        items.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except IOError:
            return {'written': [], 'skipped': [], 'total': 0, 'settled': 0}

        result = settle_memories(items, source=source)
        result['settled'] = len(items)

        # 沉降后清空暂存（settle_memories 设计为不抛异常）
        try:
            os.remove(staging)
        except OSError:
            pass
        return result


def settle_if_idle(now=None):
    """若 _raw 暂存空闲超过阈值则沉降；否则返回 None（未到阈值或无暂存）。"""
    staging = _staging_path()
    if not os.path.isfile(staging):
        return None

    if now is None:
        now = time.time()

    idle_minutes = (now - os.path.getmtime(staging)) / 60.0
    if idle_minutes < MEMORY_IDLE_SETTLE_MINUTES:
        return None

    return settle_pending_raw()
