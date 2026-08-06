"""自动化任务数据模型。

定时 AI Agent 任务：按 cron 表达式定时执行，用 LLM 调用 MCP 工具完成任务。
"""
from datetime import datetime
from extensions import db


class AutomationTask(db.Model):
    __tablename__ = 'automation_task'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    prompt = db.Column(db.Text, nullable=False)
    mcp_servers = db.Column(db.String(500), default='')  # 逗号分隔的 MCP 服务器名
    cron_expression = db.Column(db.String(100), default='0 9 * * *')
    schedule_config = db.Column(db.Text, default='')  # JSON: {mode, frequency, time, days, interval_hours, once_datetime, ...}
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    last_run = db.Column(db.DateTime, nullable=True)
    last_result = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'prompt': self.prompt,
            'mcp_servers': self.mcp_servers,
            'cron_expression': self.cron_expression,
            'schedule_config': self.schedule_config,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'end_date': self.end_date.isoformat() if self.end_date else None,
            'is_active': self.is_active,
            'last_run': self.last_run.isoformat() if self.last_run else None,
            'last_result': (self.last_result or '')[:500],
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class TaskRun(db.Model):
    """任务运行记录。每次执行（手动或定时）产生一条。"""
    __tablename__ = 'automation_task_run'

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('automation_task.id', ondelete='CASCADE'), nullable=False)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    finished_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default='running')  # running | ok | error
    result = db.Column(db.Text, default='')  # JSON: {response, tool_calls, rounds, error}
    trigger = db.Column(db.String(20), default='manual')  # manual | scheduled

    task = db.relationship('AutomationTask', backref=db.backref('runs', lazy='dynamic', order_by='TaskRun.started_at.desc()'))

    def to_dict(self):
        return {
            'id': self.id,
            'task_id': self.task_id,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'finished_at': self.finished_at.isoformat() if self.finished_at else None,
            'status': self.status,
            'result': (self.result or '')[:1000],
            'trigger': self.trigger,
        }
