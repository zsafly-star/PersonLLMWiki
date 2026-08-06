"""自动化任务路由。"""
import threading
from datetime import datetime, date
from flask import Blueprint, render_template, request
from extensions import db
from common.response import success_response, error_response
from .models import AutomationTask, TaskRun

automation_bp = Blueprint('automation', __name__, template_folder='templates')


@automation_bp.route('/automation')
def automation():
    return render_template('automation.html', active_view='automation')


def _parse_date(value):
    """解析 ISO 日期字符串 'YYYY-MM-DD'，返回 date 或 None。"""
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None


def _refresh_scheduler():
    """刷新调度器（CRUD 操作后调用）。失败不影响主流程。"""
    try:
        from common.scheduler import reload_automation_jobs
        reload_automation_jobs()
    except Exception as e:
        print(f'[automation] 刷新调度器失败: {e}')


# ────────────────── API ──────────────────

@automation_bp.route('/api/automation/tasks', methods=['GET'])
def list_tasks():
    """列出所有自动化任务。"""
    tasks = AutomationTask.query.order_by(AutomationTask.created_at.desc()).all()
    return success_response([t.to_dict() for t in tasks])


@automation_bp.route('/api/automation/tasks', methods=['POST'])
def create_task():
    """创建自动化任务。"""
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    prompt = (data.get('prompt') or '').strip()
    if not name:
        return error_response('任务名称不能为空')
    if not prompt:
        return error_response('任务提示词不能为空')

    task = AutomationTask(
        name=name,
        prompt=prompt,
        mcp_servers=data.get('mcp_servers', ''),
        cron_expression=data.get('cron_expression') or '0 9 * * *',
        schedule_config=data.get('schedule_config') or '',
        start_date=_parse_date(data.get('start_date')),
        end_date=_parse_date(data.get('end_date')),
        is_active=data.get('is_active', True),
    )
    db.session.add(task)
    db.session.commit()

    _refresh_scheduler()
    return success_response(task.to_dict(), '创建成功')


@automation_bp.route('/api/automation/tasks/<int:task_id>', methods=['PUT'])
def update_task(task_id):
    """更新自动化任务。"""
    task = AutomationTask.query.get_or_404(task_id)
    data = request.get_json(silent=True) or {}

    if 'name' in data:
        task.name = data['name']
    if 'prompt' in data:
        task.prompt = data['prompt']
    if 'mcp_servers' in data:
        task.mcp_servers = data['mcp_servers'] or ''
    if 'cron_expression' in data:
        task.cron_expression = data['cron_expression'] or '0 9 * * *'
    if 'schedule_config' in data:
        task.schedule_config = data['schedule_config'] or ''
    if 'start_date' in data:
        task.start_date = _parse_date(data.get('start_date'))
    if 'end_date' in data:
        task.end_date = _parse_date(data.get('end_date'))
    if 'is_active' in data:
        task.is_active = bool(data['is_active'])

    db.session.commit()

    _refresh_scheduler()
    return success_response(task.to_dict(), '更新成功')


@automation_bp.route('/api/automation/tasks/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    """删除自动化任务。"""
    task = AutomationTask.query.get_or_404(task_id)
    db.session.delete(task)
    db.session.commit()

    _refresh_scheduler()
    return success_response(None, '已删除')


@automation_bp.route('/api/automation/tasks/<int:task_id>/run', methods=['POST'])
def run_task_manual(task_id):
    """手动触发任务（异步执行，立即返回）。"""
    task = AutomationTask.query.get_or_404(task_id)

    # 检查是否有正在运行的记录
    running = TaskRun.query.filter_by(task_id=task_id, status='running').first()
    if running:
        return error_response('任务正在执行中')

    def _bg_run():
        try:
            from app import app
            with app.app_context():
                from common.automation_runner import run_task
                run_task(task_id, trigger='manual')
        except Exception as e:
            print(f'[automation] 手动执行 #{task_id} 异常: {e}')

    thread = threading.Thread(target=_bg_run, daemon=True)
    thread.start()

    return success_response({'task_id': task_id, 'status': 'running'}, '任务已触发')



@automation_bp.route('/api/automation/tasks/<int:task_id>/runs', methods=['GET'])
def list_task_runs(task_id):
    """获取任务的运行记录。"""
    task = AutomationTask.query.get_or_404(task_id)
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    pagination = task.runs.paginate(page=page, per_page=per_page, error_out=False)
    return success_response({
        'items': [r.to_dict() for r in pagination.items],
        'total': pagination.total,
        'page': page,
        'pages': pagination.pages,
    })


@automation_bp.route('/api/automation/tasks/<int:task_id>/runs/<int:run_id>', methods=['GET'])
def get_task_run(task_id, run_id):
    """获取单条运行记录详情。"""
    run = TaskRun.query.filter_by(id=run_id, task_id=task_id).first_or_404()
    d = run.to_dict()
    # 返回完整的 result（不限长度）
    d['result'] = run.result or ''
    return success_response(d)


@automation_bp.route('/api/automation/tasks/<int:task_id>/runs', methods=['DELETE'])
def clear_task_runs(task_id):
    """清空任务的运行记录。"""
    task = AutomationTask.query.get_or_404(task_id)
    TaskRun.query.filter_by(task_id=task_id).delete()
    db.session.commit()
    return success_response(None, '已清空运行记录')


@automation_bp.route('/api/automation/tasks/<int:task_id>/toggle', methods=['POST'])
def toggle_task(task_id):
    """切换任务的启用/停用状态。"""
    task = AutomationTask.query.get_or_404(task_id)
    task.is_active = not task.is_active
    db.session.commit()

    _refresh_scheduler()
    return success_response(task.to_dict(), '已切换状态')
