"""任务中心 + 智能体管理 API。

- 任务中心页：/tasks
- 场景/节点 CRUD：/api/tasks/scenarios、/api/tasks/nodes
- 任务实例：/api/tasks/instances
- 意图路由：/api/tasks/route
"""
import os
import threading

from flask import Blueprint, render_template, request
from extensions import db
from common.response import success_response, error_response

from .models import Scenario, ScenarioNode, TaskState, parse_allowed_tools
from . import orchestrator
from .router import route_intent

tasks_bp = Blueprint('tasks', __name__, template_folder='templates')


@tasks_bp.route('/tasks')
def tasks_page():
    return render_template('tasks.html', active_view='tasks')


def _spawn(fn, *args):
    """在后台线程执行（复用 app.app_context 模式，避免阻塞请求）。"""
    def _bg():
        try:
            from app import app
            with app.app_context():
                fn(*args)
        except Exception as e:
            print(f'[tasks] 后台执行异常: {e}')

    threading.Thread(target=_bg, daemon=True).start()


# ────────────────── 场景 CRUD ──────────────────

@tasks_bp.route('/api/tasks/scenarios', methods=['GET'])
def list_scenarios():
    scenarios = Scenario.query.order_by(Scenario.id).all()
    return success_response([s.to_dict(include_nodes=True) for s in scenarios])


@tasks_bp.route('/api/tasks/scenarios', methods=['POST'])
def create_scenario():
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    label = (data.get('label') or '').strip()
    if not name:
        return error_response('场景标识（name）不能为空')
    if not label:
        return error_response('场景名称（label）不能为空')
    if Scenario.query.filter_by(name=name).first():
        return error_response('场景标识已存在')

    scenario = Scenario(
        name=name,
        label=label,
        description=data.get('description', ''),
        is_builtin=False,
        is_active=data.get('is_active', True),
    )
    db.session.add(scenario)
    db.session.commit()
    return success_response(scenario.to_dict(include_nodes=True), '创建成功')


@tasks_bp.route('/api/tasks/scenarios/<int:scenario_id>', methods=['PUT'])
def update_scenario(scenario_id):
    scenario = Scenario.query.get_or_404(scenario_id)
    data = request.get_json(silent=True) or {}
    if 'label' in data:
        scenario.label = data['label']
    if 'description' in data:
        scenario.description = data['description'] or ''
    if 'is_active' in data:
        scenario.is_active = bool(data['is_active'])
    db.session.commit()
    return success_response(scenario.to_dict(include_nodes=True), '更新成功')


@tasks_bp.route('/api/tasks/scenarios/<int:scenario_id>', methods=['DELETE'])
def delete_scenario(scenario_id):
    scenario = Scenario.query.get_or_404(scenario_id)
    db.session.delete(scenario)
    db.session.commit()
    return success_response(None, '已删除')


# ────────────────── 节点 CRUD ──────────────────

@tasks_bp.route('/api/tasks/scenarios/<int:scenario_id>/nodes', methods=['GET'])
def list_nodes(scenario_id):
    scenario = Scenario.query.get_or_404(scenario_id)
    nodes = sorted(scenario.nodes, key=lambda n: n.sort_order)
    return success_response([n.to_dict() for n in nodes])


@tasks_bp.route('/api/tasks/scenarios/<int:scenario_id>/nodes', methods=['POST'])
def create_node(scenario_id):
    scenario = Scenario.query.get_or_404(scenario_id)
    data = request.get_json(silent=True) or {}
    key = (data.get('key') or '').strip()
    name = (data.get('name') or '').strip()
    if not key or not name:
        return error_response('节点 key 和名称不能为空')

    max_order = max((n.sort_order for n in scenario.nodes), default=-1)
    node = ScenarioNode(
        scenario_id=scenario_id,
        key=key,
        name=name,
        role_prompt=data.get('role_prompt', ''),
        gate=data.get('gate', True),
        allowed_tools=_dump_list(data.get('allowed_tools')),
        skills=_dump_list(data.get('skills')),
        sort_order=max_order + 1,
    )
    db.session.add(node)
    db.session.commit()
    return success_response(node.to_dict(), '添加成功')


@tasks_bp.route('/api/tasks/nodes/<int:node_id>', methods=['PUT'])
def update_node(node_id):
    node = ScenarioNode.query.get_or_404(node_id)
    data = request.get_json(silent=True) or {}
    if 'key' in data:
        node.key = data['key']
    if 'name' in data:
        node.name = data['name']
    if 'role_prompt' in data:
        node.role_prompt = data['role_prompt'] or ''
    if 'gate' in data:
        node.gate = bool(data['gate'])
    if 'allowed_tools' in data:
        node.allowed_tools = _dump_list(data['allowed_tools'])
    if 'skills' in data:
        node.skills = _dump_list(data['skills'])
    db.session.commit()
    return success_response(node.to_dict(), '更新成功')


@tasks_bp.route('/api/tasks/nodes/<int:node_id>', methods=['DELETE'])
def delete_node(node_id):
    node = ScenarioNode.query.get_or_404(node_id)
    db.session.delete(node)
    db.session.commit()
    return success_response(None, '已删除')


@tasks_bp.route('/api/tasks/nodes/reorder', methods=['POST'])
def reorder_nodes():
    data = request.get_json(silent=True) or {}
    ordered_ids = data.get('ids') or []
    for i, node_id in enumerate(ordered_ids):
        node = ScenarioNode.query.get(node_id)
        if node:
            node.sort_order = i
    db.session.commit()
    return success_response(None, '已排序')


def _dump_list(value):
    """把前端传来的 JSON 数组字段（allowed_tools / skills）序列化为 JSON 字符串。"""
    import json
    if value is None:
        return '[]'
    if isinstance(value, str):
        # 已是 JSON 字符串则原样保留，否则按单项处理
        value = value.strip()
        if value.startswith('['):
            return value
        return json.dumps([value], ensure_ascii=False)
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False)
    return '[]'


# ────────────────── 任务实例 ──────────────────

@tasks_bp.route('/api/tasks/instances', methods=['GET'])
def list_instances():
    tasks = TaskState.query.order_by(TaskState.created_at.desc()).all()
    return success_response([t.to_dict() for t in tasks])


@tasks_bp.route('/api/tasks/instances', methods=['POST'])
def create_instance():
    data = request.get_json(silent=True) or {}
    scene = (data.get('scene') or '').strip()
    title = (data.get('title') or '').strip()
    goal = (data.get('goal') or '').strip()
    workspace = (data.get('workspace') or '').strip()
    if not scene:
        return error_response('请选择场景')
    if not goal:
        return error_response('请填写任务目标')

    task = orchestrator.create_task(scene, title, goal, workspace=workspace or None)
    if not task:
        return error_response('场景不存在或未启用')

    _spawn(orchestrator.run_task, task.task_id)
    return success_response(task.to_dict(), '任务已启动')


@tasks_bp.route('/api/tasks/instances/<task_id>', methods=['GET'])
def get_instance(task_id):
    task = TaskState.query.filter_by(task_id=task_id).first_or_404()
    return success_response(task.to_dict())


def _ws_abs(task, rel):
    """把相对路径解析到任务工作空间内，返回 (abs_path, err_msg)。"""
    ws = (task.workspace or '').strip()
    if not ws:
        return None, '任务未设置工作空间'
    base = os.path.abspath(ws)
    rel = (rel or '').replace('\\', os.sep).replace('/', os.sep)
    cand = os.path.abspath(os.path.normpath(os.path.join(base, rel)))
    try:
        common = os.path.commonpath([base, cand])
    except ValueError:
        return None, '路径越界'
    if common != base:
        return None, '路径越界'
    return cand, None


@tasks_bp.route('/api/tasks/instances/<task_id>/workspace', methods=['GET'])
def workspace_list(task_id):
    task = TaskState.query.filter_by(task_id=task_id).first_or_404()
    sub = request.args.get('path', '')
    abs_dir, err = _ws_abs(task, sub)
    if err:
        return error_response(err)
    if not os.path.isdir(abs_dir):
        return error_response(f'目录不存在: {sub or "."}')

    dirs, files = [], []
    try:
        names = sorted(os.listdir(abs_dir), key=lambda n: n.lower())
    except PermissionError:
        return error_response('无权限读取目录')

    for name in names:
        if name.startswith('.'):
            continue
        full = os.path.join(abs_dir, name)
        rel = (sub + '/' + name).lstrip('/') if sub else name
        if os.path.isdir(full):
            dirs.append({'name': name, 'type': 'dir', 'path': rel})
        else:
            size = 0
            try:
                size = os.path.getsize(full)
            except OSError:
                pass
            files.append({'name': name, 'type': 'file', 'path': rel, 'size': size})

    return success_response({
        'workspace': task.workspace,
        'path': sub or '',
        'entries': dirs + files,
    })


@tasks_bp.route('/api/tasks/instances/<task_id>/workspace/file', methods=['GET'])
def workspace_read_file(task_id):
    task = TaskState.query.filter_by(task_id=task_id).first_or_404()
    rel = request.args.get('path', '')
    abs_path, err = _ws_abs(task, rel)
    if err:
        return error_response(err)
    if not os.path.isfile(abs_path):
        return error_response(f'文件不存在: {rel}')

    try:
        with open(abs_path, 'r', encoding='utf-8') as f:
            content = f.read(256 * 1024)
    except UnicodeDecodeError:
        return error_response('不是文本文件，无法预览')
    except (PermissionError, OSError) as e:
        return error_response(f'读取失败: {e}')

    return success_response({'path': rel, 'content': content})


@tasks_bp.route('/api/tasks/workspace/browse', methods=['GET'])
def workspace_browse():
    """通用文件夹浏览：供前端「+」弹窗选择工作空间目录。"""
    path = (request.args.get('path') or '').strip()
    if not path:
        path = os.path.expanduser('~')
    path = os.path.abspath(path)
    if not os.path.isdir(path):
        return error_response('目录不存在')

    parent = os.path.dirname(path)
    if parent == path:
        parent = None  # 已到文件系统根

    dirs = []
    try:
        for name in sorted(os.listdir(path), key=lambda n: n.lower()):
            if name.startswith('.'):
                continue
            full = os.path.join(path, name)
            if os.path.isdir(full):
                dirs.append({'name': name, 'path': full})
    except PermissionError:
        return error_response('无权限读取该目录')

    # Windows 下到盘符根时，展示所有可用盘符便于切换
    if parent is None and os.name == 'nt':
        import string
        drives = []
        for letter in string.ascii_uppercase:
            d = f'{letter}:\\'
            if os.path.exists(d):
                drives.append({'name': d, 'path': d})
        dirs = drives

    return success_response({'path': path, 'parent': parent, 'dirs': dirs})


@tasks_bp.route('/api/tasks/workspace/mkdir', methods=['POST'])
def workspace_mkdir():
    """在指定父目录下新建文件夹，供前端「+」弹窗创建空工作空间。"""
    data = request.get_json(silent=True) or {}
    parent = (data.get('parent') or '').strip()
    name = (data.get('name') or '').strip()
    if not parent or not name:
        return error_response('参数不完整')
    if name.startswith('.') or '/' in name or '\\' in name:
        return error_response('文件夹名不合法')

    parent = os.path.abspath(parent)
    if not os.path.isdir(parent):
        return error_response('父目录不存在')

    target = os.path.join(parent, name)
    if os.path.exists(target):
        return error_response('该文件夹已存在')
    try:
        os.makedirs(target)
    except OSError as e:
        return error_response(f'创建失败: {e}')
    return success_response({'path': target}, '创建成功')


@tasks_bp.route('/api/tasks/instances/<task_id>/approve', methods=['POST'])
def approve_instance(task_id):
    data = request.get_json(silent=True) or {}
    approved = bool(data.get('approved', True))
    if not orchestrator.approve_node(task_id, approved):
        return error_response('当前不在待确认状态')
    _spawn(orchestrator.run_task, task_id)
    return success_response(None, '已处理')


@tasks_bp.route('/api/tasks/instances/<task_id>/pause', methods=['POST'])
def pause_instance(task_id):
    task = TaskState.query.filter_by(task_id=task_id).first_or_404()
    if task.state not in ('running', 'awaiting_user'):
        return error_response('当前状态无法暂停')
    task.state = 'paused'
    db.session.commit()
    return success_response(task.to_dict(), '已暂停')


@tasks_bp.route('/api/tasks/instances/<task_id>/resume', methods=['POST'])
def resume_instance(task_id):
    task = TaskState.query.filter_by(task_id=task_id).first_or_404()
    if task.state != 'paused':
        return error_response('当前状态无法继续')
    task.state = 'running'
    db.session.commit()
    _spawn(orchestrator.run_task, task_id)
    return success_response(task.to_dict(), '已继续')


@tasks_bp.route('/api/tasks/instances/<task_id>', methods=['DELETE'])
def delete_instance(task_id):
    task = TaskState.query.filter_by(task_id=task_id).first_or_404()
    db.session.delete(task)
    db.session.commit()
    return success_response(None, '已删除')


# ────────────────── 意图路由 ──────────────────

@tasks_bp.route('/api/tasks/route', methods=['POST'])
def route():
    data = request.get_json(silent=True) or {}
    text = (data.get('text') or '').strip()
    if not text:
        return error_response('请输入内容')
    scene = route_intent(text)
    return success_response({'scene': scene})
