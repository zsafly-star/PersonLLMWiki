"""自动化任务执行引擎。

统一经 dsh_bridge 走 DSH headless 执行（DSH 有自己的 LLM 配置，与 PersonLLMWiki 独立）：
- 接受任务描述 prompt
- 执行结果写入 AutomationTask.last_result
"""

import json
import logging
from datetime import datetime

from extensions import db
from common import dsh_bridge

logger = logging.getLogger(__name__)


def run_task(task_id, trigger='scheduled'):
    """执行一个自动化任务（同步），将结果写入 TaskRun 记录。

    Args:
        task_id: 任务 ID
        trigger: 'manual' | 'scheduled'
    """
    from modules.automation.models import AutomationTask, TaskRun

    task = AutomationTask.query.get(task_id)
    if not task:
        return None

    logger.info(f'[Automation] 开始执行任务 #{task_id}: {task.name}')

    # 创建运行记录
    run = TaskRun(task_id=task.id, trigger=trigger, status='running')
    db.session.add(run)
    db.session.flush()  # 获取 run.id

    # 统一经 dsh_bridge 走 DSH headless 执行，不再回退本地 react loop。
    try:
        if not dsh_bridge.is_installed():
            _finish_run(run, status='error', error='DSH 未安装，无法执行自动化任务')
            _update_task_last(task, status='error')
            return run.id

        _hr = dsh_bridge.run_headless(task.prompt)
        if _hr.get('success'):
            _finish_run(run, status='ok', response=_hr.get('output', ''))
            _update_task_last(task, status='ok')
            return run.id

        _finish_run(run, status='error', error=_hr.get('error') or 'DSH headless 执行失败')
        _update_task_last(task, status='error')
        return run.id
    except Exception as e:
        logger.error(f'[Automation] 任务 #{task_id} 执行异常: {e}')
        _finish_run(run, status='error', error=f'执行异常: {str(e)}')
        _update_task_last(task, status='error')
        return run.id


def _finish_run(run, status='ok', response='', error='', tool_calls=None):
    """完成运行记录。"""
    run.finished_at = datetime.utcnow()
    run.status = status
    run.result = json.dumps({
        'status': status,
        'response': response[:1000] if response else '',
        'error': error[:1000] if error else '',
        'tool_calls': (tool_calls or [])[:20],
        'rounds': len(tool_calls) if tool_calls else 0,
    }, ensure_ascii=False)
    db.session.commit()


def _update_task_last(task, status='ok'):
    """更新任务本身的 last_run / last_result。"""
    task.last_run = datetime.utcnow()
    task.last_result = json.dumps({
        'status': status,
        'response': '完整记录见运行记录',
    }, ensure_ascii=False)
    db.session.commit()
