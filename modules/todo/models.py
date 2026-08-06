"""任务模型（合并 Todo + Plan）。"""
from datetime import datetime
from extensions import db


class TodoItem(db.Model):
    __tablename__ = 'todo_item'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.Text, nullable=False)
    done = db.Column(db.Boolean, default=False)
    priority = db.Column(db.Text, default='normal')  # high / normal / low
    related_slug = db.Column(db.Text, nullable=True)
    source = db.Column(db.Text, default='manual')  # manual / agent
    # 看板状态：inbox(收集箱) / todo(待办) / doing(进行中) / done(已完成) / cancelled(已取消)
    status = db.Column(db.Text, default='inbox')
    created_at = db.Column(db.Text, default=lambda: datetime.now().isoformat())
    updated_at = db.Column(db.Text, default=lambda: datetime.now().isoformat())

    def to_dict(self):
        effective_status = self.status or 'inbox'
        # 向后兼容：done=True 且 status 未设置时视为 done
        if self.done and effective_status not in ('cancelled',):
            effective_status = 'done'
        return {
            'id': self.id,
            'title': self.title,
            'done': self.done,
            'priority': self.priority,
            'related_slug': self.related_slug,
            'source': self.source,
            'status': effective_status,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }


# 兼容旧代码：PlanItem 保留但指向同一张表
class PlanItem(TodoItem):
    """已弃用，保留仅为兼容。实际数据统一存入 todo_item 表。"""
    pass
