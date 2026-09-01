"""记忆「多信号沉降」通道（轨道 B）测试。

覆盖：
1. settle_memories 批量写入（status=auto、带 source）
2. 逐条近似查重（文本兜底 + 语义）
3. 空/非法 kind 跳过（宁缺毋滥）
4. stage_raw_trace → settle_pending_raw 端到端
5. settle_if_idle 空闲阈值判断
"""

import json
import os
import time

import pytest


@pytest.fixture(autouse=True)
def memory_env(monkeypatch, tmp_path):
    """把记忆目录指向临时目录，并禁用 embedding（无 API 环境走文本兜底）。"""
    mem_dir = tmp_path / 'memories'
    raw_dir = mem_dir / '_raw'
    monkeypatch.setattr('config.Config.MEMORIES_DIR', str(mem_dir))
    monkeypatch.setattr('config.Config.MEMORIES_RAW_DIR', str(raw_dir))
    # 无 embedding 环境：语义检索返回空、增量向量更新为空操作，保证测试确定性
    monkeypatch.setattr('modules.memory.retrieval.search_memory', lambda *a, **k: [])
    monkeypatch.setattr('modules.memory.retrieval.update_memory_embedding', lambda *a, **k: None)
    return {'mem_dir': mem_dir, 'raw_dir': raw_dir}


def _read_frontmatter(slug, mem_dir):
    path = mem_dir / (slug + '.md')
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    fm_str = content[4:content.find('\n---\n', 4)]
    return json.loads(fm_str)


def test_settle_writes_auto_with_source(memory_env):
    from modules.memory import settle
    items = [
        {'body': '用户偏好深色主题', 'kind': 'preference', 'source': 'trace'},
        {'body': '用户使用 Windows 系统', 'kind': 'fact', 'source': 'trace'},
    ]
    result = settle.settle_memories(items, source='idle_settle')

    assert len(result['written']) == 2
    assert result['skipped'] == []
    for w in result['written']:
        fm = _read_frontmatter(w['slug'], memory_env['mem_dir'])
        assert fm['status'] == 'auto'
        assert fm['source'] == 'trace'
        assert fm['kind'] == w['kind']


def test_settle_dedup_exact_and_near(memory_env):
    from modules.memory import settle
    items = [
        {'body': '用户偏好使用深色主题显示界面', 'kind': 'preference'},
        {'body': '用户偏好使用深色主题显示界面', 'kind': 'preference'},
        {'body': '用户偏好使用深色主题来显示界面', 'kind': 'preference'},
    ]
    result = settle.settle_memories(items)

    assert len(result['written']) == 1
    reasons = [s['reason'] for s in result['skipped']]
    assert reasons.count('duplicate') == 2


def test_settle_skips_empty_and_invalid_kind(memory_env):
    from modules.memory import settle
    items = [
        {'body': '   ', 'kind': 'preference'},
        {'body': '正文', 'kind': 'bogus'},
    ]
    result = settle.settle_memories(items)

    assert result['written'] == []
    reasons = {s['reason'] for s in result['skipped']}
    assert 'empty' in reasons
    assert 'invalid_kind' in reasons


def test_settle_semantic_dedup(memory_env, monkeypatch):
    from modules.memory import settle
    monkeypatch.setattr(
        'modules.memory.retrieval.search_memory',
        lambda *a, **k: [{'score': 0.95}],
    )
    assert settle._is_duplicate('任意正文', []) is True


def test_stage_and_settle_pending_raw(memory_env):
    from modules.memory import settle
    settle.stage_raw_trace([
        {'body': '用户偏好深色主题', 'kind': 'preference', 'source': 'trace'},
        {'body': '用户使用 Windows 系统', 'kind': 'fact', 'source': 'trace'},
    ])

    staging = memory_env['raw_dir'] / 'pending.jsonl'
    assert staging.exists()

    result = settle.settle_pending_raw()
    assert len(result['written']) == 2
    assert not staging.exists()
    assert len(list(memory_env['mem_dir'].glob('*.md'))) == 2


def test_settle_if_idle_not_idle_returns_none(memory_env):
    from modules.memory import settle
    settle.stage_raw_trace([{'body': '用户偏好深色主题', 'kind': 'preference'}])
    # 刚写入，未超过空闲阈值
    assert settle.settle_if_idle() is None


def test_settle_if_idle_settles_after_timeout(memory_env):
    from modules.memory import settle
    settle.stage_raw_trace([{'body': '用户偏好深色主题', 'kind': 'preference'}])

    staging = memory_env['raw_dir'] / 'pending.jsonl'
    old = time.time() - (settle.MEMORY_IDLE_SETTLE_MINUTES * 60 + 60)
    os.utime(staging, (old, old))

    result = settle.settle_if_idle()
    assert result is not None
    assert len(result['written']) == 1
    assert not staging.exists()


def test_stage_memory_signals_filters(memory_env):
    from modules.memory import settle
    items = [
        {'body': '   ', 'kind': 'preference'},               # empty
        {'body': '正文', 'kind': 'bogus'},                   # invalid kind
        {'body': 'x' * 201, 'kind': 'fact'},                 # too long (>200)
        {'body': '用户偏好深色主题', 'kind': 'preference'},   # valid
    ]
    result = settle.stage_memory_signals(items)

    assert result['staged'] == 1
    assert result['total'] == 4
    reasons = {s['reason'] for s in result['skipped']}
    assert reasons == {'empty', 'invalid_kind', 'too_long'}

    staging = memory_env['raw_dir'] / 'pending.jsonl'
    assert staging.exists()
    lines = staging.read_text(encoding='utf-8').strip().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec['body'] == '用户偏好深色主题'
    assert rec['kind'] == 'preference'
    assert rec['source'] == 'signal'


def test_stage_memory_signals_dedup_batch_and_pending(memory_env):
    from modules.memory import settle
    # 批内重复：只暂存一条
    r1 = settle.stage_memory_signals([
        {'body': '用户偏好深色主题', 'kind': 'preference'},
        {'body': '用户偏好深色主题', 'kind': 'preference'},
    ])
    assert r1['staged'] == 1

    # 暂存内已存在：第二次调用跳过，避免重复喂养沉降通道
    r2 = settle.stage_memory_signals([
        {'body': '用户偏好深色主题', 'kind': 'preference'},
    ])
    assert r2['staged'] == 0
    assert r2['skipped'][0]['reason'] == 'duplicate'


def test_stage_memory_signals_dedup_against_memories(memory_env):
    from modules.memory import settle
    settle.stage_memory_signals([{'body': '用户偏好深色主题', 'kind': 'preference'}])
    settle.settle_pending_raw()

    # 已沉降进 memories，再暂存同一条 → 近似查重命中，跳过
    r = settle.stage_memory_signals([
        {'body': '用户偏好深色主题', 'kind': 'preference'},
    ])
    assert r['staged'] == 0
    assert r['skipped'][0]['reason'] == 'duplicate'


def test_stage_memory_signals_end_to_end_settle(memory_env):
    from modules.memory import settle
    settle.stage_memory_signals([
        {'body': '用户偏好深色主题', 'kind': 'preference', 'source': 'signal'},
        {'body': '用户使用 Windows 系统', 'kind': 'fact', 'source': 'signal'},
    ])

    staging = memory_env['raw_dir'] / 'pending.jsonl'
    old = time.time() - (settle.MEMORY_IDLE_SETTLE_MINUTES * 60 + 60)
    os.utime(staging, (old, old))

    result = settle.settle_if_idle()
    assert result is not None
    assert len(result['written']) == 2
    assert not staging.exists()

    for w in result['written']:
        fm = _read_frontmatter(w['slug'], memory_env['mem_dir'])
        assert fm['status'] == 'auto'
        assert fm['source'] == 'signal'
        assert fm['kind'] == w['kind']
