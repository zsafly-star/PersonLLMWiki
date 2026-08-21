"""L2 编排器：单 agent 分阶段执行 + 闸门 + 断点续跑。

核心：for node in plan: run_agent_loop(system_prompt=node.role_prompt, tools=filtered)。
同一 react loop，每个节点换角色提示词 + 工具白名单。
"""
import json
import os
import time
import uuid
from datetime import datetime

from config import Config
from extensions import db
from common.agent_core import run_agent_loop, filter_tools_by_scope
from common.workspace_ctx import set_workspace, clear_workspace

from .models import Scenario, TaskState, parse_allowed_tools, _loads
from . import state_store
from .security import is_dangerous_tool

MAX_ROUNDS = 30


def create_task(scene_name, title, goal='', workspace=None):
    """发起一个任务实例：从场景定义固化节点序列，初始化断点续跑上下文。

    Args:
        scene_name: 场景标识
        title: 任务标题
        goal: 任务目标
        workspace: 工作空间文件夹路径（可选）。留空时自动在用户数据目录下创建
                   workspaces/<task_id> 作为默认工作空间。
    """
    scenario = Scenario.query.filter_by(name=scene_name, is_active=True).first()
    if not scenario:
        return None

    nodes = sorted(scenario.nodes, key=lambda n: n.sort_order)
    plan = [
        {
            'key': n.key,
            'name': n.name,
            'role_prompt': n.role_prompt or '',
            'gate': bool(n.gate),
            'allowed_tools': parse_allowed_tools(n.allowed_tools),
            'skills': parse_allowed_tools(n.skills),
        }
        for n in nodes
    ]

    task_id = f"T-{int(time.time())}-{uuid.uuid4().hex[:4]}"

    # 工作空间：用户显式指定 → 直接用；否则默认自动创建
    ws = (workspace or '').strip()
    if not ws:
        ws = os.path.join(Config.USER_DATA_DIR, 'workspaces', task_id)
    ws = os.path.abspath(ws)
    os.makedirs(ws, exist_ok=True)

    task = TaskState(
        task_id=task_id,
        scene=scenario.name,
        title=title or scenario.label,
        state='running',
        plan=json.dumps(plan, ensure_ascii=False),
        artifacts=json.dumps({}, ensure_ascii=False),
        pending_approval=json.dumps({}, ensure_ascii=False),
        traceability=json.dumps([], ensure_ascii=False),
        history=json.dumps([], ensure_ascii=False),
        workspace=ws,
        resume_context=json.dumps({
            'goal': goal or title or scenario.label,
            'confirmed_artifacts': [],
            'next_step': '',
        }, ensure_ascii=False),
    )
    db.session.add(task)
    db.session.commit()
    return task


def run_task(task_id):
    """执行 / 恢复一个任务（同步，需在 app.app_context() 内调用）。"""
    task = state_store.load_task(task_id)
    if not task:
        return

    if task.state == 'paused':
        return

    nodes = state_store.load_plan(task)
    if not nodes:
        task.state = 'done'
        state_store.append_history(task, {'at': _now(), 'event': '空流程，直接结束'})
        state_store.save(task)
        return

    rc = _loads(task.resume_context, {})
    completed = {a.get('node') for a in rc.get('confirmed_artifacts', []) if a.get('node')}

    task.state = 'running'
    state_store.save(task)

    for node in nodes:
        if task.state == 'paused':
            return

        node_key = node.get('key')
        if node_key in completed:
            continue

        task.current_node = node_key
        state_store.append_history(task, {
            'at': _now(), 'event': f"开始节点「{node.get('name', node_key)}」",
        })
        state_store.save(task)

        allowed = parse_allowed_tools(node.get('allowed_tools', []))
        tools = filter_tools_by_scope(allowed)

        try:
            set_workspace(task.workspace)
            messages = state_store.build_node_messages(task, node)
            result = run_agent_loop(
                messages,
                system_prompt=_build_node_system_prompt(node, task),
                tools=tools,
                max_rounds=MAX_ROUNDS,
            )
            response = (result or {}).get('response', '') or ''
        except Exception as e:
            task.state = 'failed'
            state_store.append_history(task, {
                'at': _now(), 'event': f"节点「{node.get('name')}」执行异常: {e}",
            })
            state_store.save(task)
            return
        finally:
            clear_workspace()

        state_store.save_artifact(task, node_key, summary=response)
        state_store.update_resume_context(task, node_key, summary=response[:500])
        state_store.append_history(task, {
            'at': _now(), 'event': f"节点「{node.get('name', node_key)}」完成",
        })

        if node.get('gate'):
            task.state = 'awaiting_user'
            task.pending_approval = json.dumps({
                'node': node_key,
                'question': f"请确认「{node.get('name', node_key)}」的产出是否通过",
                'dangerous': any(is_dangerous_tool(t) for t in allowed),
            }, ensure_ascii=False)
            state_store.save(task)
            return

    task.state = 'done'
    task.current_node = None
    state_store.append_history(task, {'at': _now(), 'event': '任务完成'})
    state_store.save(task)


def approve_node(task_id, approved=True):
    """处理人工闸门：approved=True 继续；False 拒绝并要求重做当前节点。"""
    task = state_store.load_task(task_id)
    if not task or task.state != 'awaiting_user':
        return False

    pending = _loads(task.pending_approval, {})
    node_key = pending.get('node')

    rc = _loads(task.resume_context, {})
    confirmed = rc.get('confirmed_artifacts', [])

    if approved:
        # 保持当前节点在 confirmed_artifacts 中（跳过），继续下一节点
        pass
    else:
        # 拒绝：从 confirmed_artifacts 移除该节点，使其重新执行
        rc['confirmed_artifacts'] = [a for a in confirmed if a.get('node') != node_key]

    task.resume_context = json.dumps(rc, ensure_ascii=False)
    task.pending_approval = json.dumps({}, ensure_ascii=False)
    task.state = 'running'
    state_store.append_history(task, {
        'at': _now(),
        'event': f"节点「{node_key}」{'通过' if approved else '被驳回，重新执行'}",
    })
    state_store.save(task)
    return True


def _build_node_system_prompt(node, task=None):
    """组合节点 system prompt：角色提示词 + Skills 全文 + 工作空间说明。"""
    prompt = (node.get('role_prompt') or '').strip()
    skills = node.get('skills') or []

    chunks = [prompt] if prompt else []

    if skills:
        from common import skill_loader
        names = [s for s in skills if s != '*']
        if '*' in skills:
            names = [s['name'] for s in skill_loader.list_skills()]
        for name in names:
            skill = skill_loader.load_skill(name)
            if skill and skill.get('body'):
                chunks.append(f"\n## 技能：{skill['name']}\n{skill['body']}")

    if task and getattr(task, 'workspace', None):
        chunks.append(
            "\n## 工作空间\n"
            f"当前任务的工作空间（电脑文件夹）绝对路径：{task.workspace}\n"
            "- 读写该文件夹内的文本/代码文件，用 list_workspace / read_workspace_file / write_workspace_file，"
            "path 参数填相对于工作空间根目录的相对路径。\n"
            "- 只能在该工作空间内读写，不要越界访问其他目录。"
        )

    return '\n'.join(chunks) or None


def _now():
    return datetime.utcnow().isoformat()
