"""L4 状态持久化 + 上下文重建。

断点续跑的核心：不塞回完整对话，只存"精简摘要 + 指针"。
- artifacts 存产物指针（summary + path），不存原文
- resume_context 存摘要（goal + confirmed_artifacts + next_step）
"""
import json

from extensions import db

from .models import TaskState, _loads


def load_task(task_id):
    """按 task_id 加载任务实例。"""
    return TaskState.query.filter_by(task_id=task_id).first()


def load_plan(task):
    """加载任务发起时固化的节点序列快照。"""
    return _loads(task.plan, [])


def save(task):
    """提交任务状态变更。"""
    db.session.commit()


def save_artifact(task, node_key, summary='', path=None):
    """记录某节点的产物（只存摘要 + 指针，不存原文）。"""
    artifacts = _loads(task.artifacts, {})
    artifacts[node_key] = {
        'summary': (summary or '')[:2000],
        'path': path or '',
    }
    task.artifacts = json.dumps(artifacts, ensure_ascii=False)


def append_history(task, entry):
    """追加事件日志。"""
    history = _loads(task.history, [])
    history.append(entry)
    task.history = json.dumps(history, ensure_ascii=False)


def update_resume_context(task, node_key, summary=''):
    """在节点完成后更新断点续跑上下文。

    把当前节点产物摘要并入 confirmed_artifacts，next_step 由编排器随后覆盖。
    """
    rc = _loads(task.resume_context, {})
    rc.setdefault('confirmed_artifacts', [])
    if summary:
        rc['confirmed_artifacts'].append({'node': node_key, 'summary': summary})
    rc['current_node'] = node_key
    task.resume_context = json.dumps(rc, ensure_ascii=False)


def build_node_messages(task, node):
    """为当前节点重建 LLM 消息（不携带历史工具调用细节）。

    返回 user 消息列表，system prompt（role_prompt）由编排器作为 system_prompt 传入。
    """
    rc = _loads(task.resume_context, {})
    goal = rc.get('goal') or task.title or ''

    parts = [f'任务目标：{goal}']

    confirmed = rc.get('confirmed_artifacts', [])
    if confirmed:
        parts.append('已确认的前序产物：')
        for a in confirmed:
            parts.append(f"- [{a.get('node', '')}] {a.get('summary', '')}")

    next_step = rc.get('next_step') or f"请完成「{node.get('name', '')}」这一步骤。"
    parts.append(f'下一步：{next_step}')

    return [{'role': 'user', 'content': '\n'.join(parts)}]
