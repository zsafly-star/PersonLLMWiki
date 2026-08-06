"""任务路由（合并 Todo + Plan）。"""
from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from extensions import db
from datetime import datetime
from .models import TodoItem

todo_bp = Blueprint('todo', __name__, template_folder='templates')


@todo_bp.route('/todo')
def todo():
    return render_template('todo.html', active_view='todo')


@todo_bp.route('/plan')
def plan_redirect():
    """旧 /plan 路径重定向到 /todo。"""
    return redirect(url_for('todo.todo'))


# ────────────────── API ──────────────────

@todo_bp.route('/api/todos', methods=['GET'])
def list_todos():
    items = TodoItem.query.order_by(
        TodoItem.done.asc(),
        TodoItem.created_at.desc(),
    ).all()
    return jsonify({'code': 200, 'data': [i.to_dict() for i in items]})


@todo_bp.route('/api/todos', methods=['POST'])
def create_todo():
    data = request.get_json(silent=True) or {}
    title = data.get('title', '').strip()
    if not title:
        return jsonify({'code': 400, 'message': '标题不能为空'})

    item = TodoItem(
        title=title,
        priority=data.get('priority', 'normal'),
        related_slug=data.get('related_slug'),
        source=data.get('source', 'manual'),
        status=data.get('status', 'inbox'),
    )
    db.session.add(item)
    db.session.commit()
    return jsonify({'code': 200, 'data': item.to_dict()})


@todo_bp.route('/api/todos/<int:item_id>', methods=['PUT'])
def update_todo(item_id):
    item = TodoItem.query.get_or_404(item_id)
    data = request.get_json(silent=True) or {}

    if 'title' in data:
        item.title = data['title']
    if 'done' in data:
        item.done = data['done']
        # 同步 status
        if data['done']:
            item.status = 'done'
        elif item.status == 'done':
            item.status = 'todo'
    if 'priority' in data:
        item.priority = data['priority']
    if 'related_slug' in data:
        item.related_slug = data['related_slug']
    if 'status' in data:
        item.status = data['status']
        # 同步 done
        item.done = (data['status'] == 'done')

    item.updated_at = datetime.now().isoformat()
    db.session.commit()
    return jsonify({'code': 200, 'data': item.to_dict()})


@todo_bp.route('/api/todos/<int:item_id>', methods=['DELETE'])
def delete_todo(item_id):
    item = TodoItem.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    return jsonify({'code': 200, 'message': '已删除'})


@todo_bp.route('/api/todos/clear-done', methods=['POST'])
def clear_done():
    """清除已完成和已取消的任务。"""
    TodoItem.query.filter(TodoItem.status.in_(['done', 'cancelled'])).delete()
    db.session.commit()
    return jsonify({'code': 200, 'message': '已清除'})


# ────────────────── 兼容旧 Plan API ──────────────────

@todo_bp.route('/api/plans', methods=['GET'])
def list_plans_compat():
    """兼容旧 /api/plans，返回 todo_item 中所有项。"""
    items = TodoItem.query.order_by(TodoItem.created_at.desc()).all()
    return jsonify({'code': 200, 'data': [i.to_dict() for i in items]})


@todo_bp.route('/api/plans', methods=['POST'])
def create_plan_compat():
    """兼容旧 /api/plans 创建。"""
    data = request.get_json(silent=True) or {}
    title = data.get('title', '').strip()
    if not title:
        return jsonify({'code': 400, 'message': '标题不能为空'})
    item = TodoItem(title=title, status=data.get('status', 'inbox'))
    db.session.add(item)
    db.session.commit()
    return jsonify({'code': 200, 'data': item.to_dict()})


@todo_bp.route('/api/plans/<int:item_id>', methods=['PUT'])
def update_plan_compat(item_id):
    """兼容旧 /api/plans 更新。"""
    item = TodoItem.query.get_or_404(item_id)
    data = request.get_json(silent=True) or {}
    if 'title' in data:
        item.title = data['title']
    if 'status' in data:
        item.status = data['status']
        item.done = (data['status'] == 'done')
    item.updated_at = datetime.now().isoformat()
    db.session.commit()
    return jsonify({'code': 200, 'data': item.to_dict()})


@todo_bp.route('/api/plans/<int:item_id>', methods=['DELETE'])
def delete_plan_compat(item_id):
    """兼容旧 /api/plans 删除。"""
    item = TodoItem.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    return jsonify({'code': 200, 'message': '已删除'})
