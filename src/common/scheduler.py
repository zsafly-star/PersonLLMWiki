"""定时任务调度器。

基于 APScheduler，支持 cron 表达式定时任务。
- 硬编码任务：SAP 物料同步
- 动态任务：从 automation_task 表加载（支持日期区间校验）

通过 .env 配置：
  SCHEDULER_ENABLED=true          # 启用调度器（默认 true）
  SAP_SYNC_CRON="0 0 * * *"      # SAP 同步 cron 表达式（默认每天 0 点）
  SAP_MCP_URL=http://sap:8000/mcp # SAP MCP 端点
  SAP_MCP_DB_PATH=D:/.../materials.db  # SAP MCP 数据库路径
"""

import os
import json
import logging
import requests
from datetime import datetime, date, timedelta

from config import Config

logger = logging.getLogger(__name__)

_scheduler = None
AUTO_JOB_PREFIX = 'auto_'


def _sync_sap_and_import():
    """定时任务：SAP 物料同步 + 导入到 Wiki。

    流程：
    1. 触发 SAP MCP sync_materials（拉取最新物料到 SQLite）
    2. 从 SQLite 导入有规格书的物料到 Wiki
    """
    logger.info('[Scheduler] SAP 物料同步任务开始')

    # Step 1: 触发 SAP MCP 同步（如果配置了 MCP URL）
    sap_mcp_url = os.environ.get('SAP_MCP_URL', '')
    if sap_mcp_url:
        try:
            logger.info(f'[Scheduler] 触发 SAP MCP sync_materials: {sap_mcp_url}')
            resp = requests.post(sap_mcp_url, json={
                'jsonrpc': '2.0',
                'method': 'tools/call',
                'params': {
                    'name': 'sync_materials',
                    'arguments': {'force_full': False},
                },
                'id': 1,
            }, timeout=300)
            result = resp.json()
            if 'error' in result:
                logger.warning(f'[Scheduler] SAP MCP 同步返回错误: {result["error"]}')
            else:
                logger.info('[Scheduler] SAP MCP 同步完成')
        except Exception as e:
            logger.warning(f'[Scheduler] SAP MCP 同步失败（继续执行导入）: {e}')

    # Step 2: 从 SAP SQLite 导入到 Wiki
    sap_db_path = os.environ.get('SAP_MCP_DB_PATH', '')
    if not sap_db_path:
        # 尝试默认路径
        from common.import_sap_materials import import_materials_from_sap_db
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        default_path = os.path.normpath(os.path.join(project_root, '..', 'MCP', 'sap', 'data', 'materials.db'))
        if os.path.isfile(default_path):
            sap_db_path = default_path

    if not sap_db_path or not os.path.isfile(sap_db_path):
        logger.warning('[Scheduler] SAP MCP 数据库不存在，跳过导入')
        return

    try:
        from common.import_sap_materials import import_materials_from_sap_db
        from app import app

        with app.app_context():
            result = import_materials_from_sap_db(sap_db_path)
            logger.info(f'[Scheduler] 导入完成: {json.dumps(result, ensure_ascii=False)}')

    except Exception as e:
        logger.error(f'[Scheduler] 导入失败: {e}')


def init_scheduler(app):
    """初始化定时任务调度器。

    在 Flask app 启动时调用。
    """
    global _scheduler

    if _scheduler is not None:
        return _scheduler

    enabled = os.environ.get('SCHEDULER_ENABLED', 'true').lower() == 'true'
    if not enabled:
        logger.info('[Scheduler] 调度器已禁用（SCHEDULER_ENABLED != true）')
        return None

    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    _scheduler = BackgroundScheduler(daemon=True)

    # SAP 物料同步任务
    cron_expr = os.environ.get('SAP_SYNC_CRON', '0 0 * * *')  # 默认每天 0 点
    parts = cron_expr.split()

    if len(parts) == 5:
        trigger = CronTrigger(
            minute=parts[0],
            hour=parts[1],
            day=parts[2],
            month=parts[3],
            day_of_week=parts[4],
        )
    else:
        logger.warning(f'[Scheduler] cron 表达式格式错误: {cron_expr}，使用默认每天 0 点')
        trigger = CronTrigger(hour=0, minute=0)

    _scheduler.add_job(
        func=_sync_sap_and_import,
        trigger=trigger,
        id='sap_sync',
        name='SAP 物料同步',
        replace_existing=True,
        misfire_grace_time=3600,
    )

    _scheduler.start()
    logger.info(f'[Scheduler] 调度器已启动，SAP 同步 cron: {cron_expr}')

    # 加载自动化任务
    reload_automation_jobs()

    return _scheduler


def get_scheduler_status():
    """获取调度器状态"""
    if _scheduler is None:
        return {'running': False, 'jobs': []}

    jobs = []
    for job in _scheduler.get_jobs():
        jobs.append({
            'id': job.id,
            'name': job.name,
            'next_run': job.next_run_time.isoformat() if job.next_run_time else None,
            'trigger': str(job.trigger),
        })

    return {
        'running': _scheduler.running,
        'jobs': jobs,
    }


def trigger_job_now(job_id='sap_sync'):
    """手动触发一个定时任务"""
    if _scheduler is None:
        return False, '调度器未启动'

    # 自动化任务：直接调用执行函数
    if job_id.startswith(AUTO_JOB_PREFIX):
        task_id_str = job_id[len(AUTO_JOB_PREFIX):]
        try:
            task_id = int(task_id_str)
        except ValueError:
            return False, f'无效的自动化任务 ID: {task_id_str}'
        _execute_automation_task(task_id)
        return True, f'自动化任务 {task_id} 已触发'

    job = _scheduler.get_job(job_id)
    if job is None:
        return False, f'任务不存在: {job_id}'

    # 添加一次性立即执行任务
    _scheduler.add_job(
        func=job.func,
        args=job.args,
        kwargs=job.kwargs,
        id=f'{job_id}_manual_{datetime.now().strftime("%Y%m%d%H%M%S")}',
        replace_existing=False,
    )
    return True, f'任务 {job_id} 已触发'


# ── 自动化任务（动态加载）──

def _execute_automation_task(task_id):
    """在 Flask app context 中执行自动化任务。"""
    try:
        from app import app
        with app.app_context():
            from common.automation_runner import run_task
            run_task(task_id, trigger='scheduled')
    except Exception as e:
        logger.error(f'[Scheduler] 自动化任务 #{task_id} 执行失败: {e}')


def _make_auto_wrapper(task_id):
    """创建调度器专用的 wrapper 函数。

    检查日期区间和双周奇偶，在有效期内才执行。
    """
    def wrapper():
        # 检查双周模式：只偶数周执行（以年初第一周为第1周）
        try:
            from app import app
            with app.app_context():
                from modules.automation.models import AutomationTask
                task = AutomationTask.query.get(task_id)
                if task and task.schedule_config:
                    cfg = json.loads(task.schedule_config)
                    if cfg.get('frequency') == 'biweekly':
                        week_num = datetime.now().isocalendar()[1]
                        if week_num % 2 != 0:  # 奇数周跳过
                            logger.info(f'[Scheduler] 双周任务 #{task_id} 奇数周({week_num})，跳过')
                            return
        except Exception as e:
            logger.warning(f'[Scheduler] 双周检查异常: {e}')
        _execute_automation_task(task_id)
    return wrapper


def reload_automation_jobs():
    """从数据库重新加载所有活跃的自动化任务到调度器。

    先移除旧任务，再根据 DB 中 is_active=1 的任务重新注册。
    """
    if _scheduler is None:
        return

    from app import app
    with app.app_context():
        from modules.automation.models import AutomationTask
        from apscheduler.triggers.cron import CronTrigger

        # 移除旧的自动化任务
        for job in _scheduler.get_jobs():
            if job.id.startswith(AUTO_JOB_PREFIX):
                try:
                    _scheduler.remove_job(job.id)
                except Exception:
                    pass
                logger.info(f'[Scheduler] 移除旧任务: {job.id}')

        # 从 DB 加载活跃任务
        today = date.today()
        tasks = AutomationTask.query.filter_by(is_active=True).all()

        for task in tasks:
            # 日期区间校验：已过期的不注册
            if task.end_date and task.end_date < today:
                logger.info(f'[Scheduler] 任务 #{task.id} 已过期，跳过')
                continue

            job_id = f'{AUTO_JOB_PREFIX}{task.id}'

            try:
                cron_expr = (task.cron_expression or '0 9 * * *').strip()

                if cron_expr == 'once':
                    # 单次执行：从 schedule_config 读取 datetime，使用 DateTrigger
                    sched_cfg = json.loads(task.schedule_config or '{}')
                    run_time_str = sched_cfg.get('datetime', '')
                    if not run_time_str:
                        logger.warning(f'[Scheduler] once 任务 #{task.id} 缺少执行时间')
                        continue
                    from apscheduler.triggers.date import DateTrigger
                    run_time = datetime.fromisoformat(run_time_str)
                    if run_time < datetime.now():
                        logger.info(f'[Scheduler] once 任务 #{task.id} 已过期，跳过')
                        continue
                    trigger = DateTrigger(run_date=run_time)
                else:
                    parts = cron_expr.split()
                    if len(parts) == 5:
                        trigger = CronTrigger(
                            minute=parts[0],
                            hour=parts[1],
                            day=parts[2],
                            month=parts[3],
                            day_of_week=parts[4],
                        )
                    else:
                        logger.warning(f'[Scheduler] 任务 #{task.id} cron 格式错误: {cron_expr}')
                        continue

                _scheduler.add_job(
                    func=_make_auto_wrapper(task.id),
                    trigger=trigger,
                    id=job_id,
                    name=task.name,
                    replace_existing=True,
                    misfire_grace_time=3600,
                )
                logger.info(f'[Scheduler] 已注册任务: {job_id} ({task.name}) trigger={trigger}')
            except Exception as e:
                logger.error(f'[Scheduler] 注册任务 #{task.id} 失败: {e}')
