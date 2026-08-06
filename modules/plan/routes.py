"""Plan 路由 — 已合并到 Todo 模块，仅保留重定向兼容。"""
from flask import Blueprint, redirect, url_for

plan_bp = Blueprint('plan', __name__, template_folder='templates')


@plan_bp.route('/plan')
def plan():
    return redirect(url_for('todo.todo'))
