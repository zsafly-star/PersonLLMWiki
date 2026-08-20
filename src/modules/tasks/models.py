"""任务（智能体流水线）数据模型。

场景 = 数据库记录（Scenario），节点 = 场景下的有序子记录（ScenarioNode）。
任务实例 = TaskState（L4 状态持久化 + 断点续跑）。

均沿用项目 SQLAlchemy 模式（from extensions import db）。
"""
import json
from datetime import datetime

from extensions import db


class Scenario(db.Model):
    """场景 / 智能体定义。"""
    __tablename__ = 'scenario'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)  # software_delivery
    label = db.Column(db.String(100), nullable=False)              # 写代码
    description = db.Column(db.Text, default='')
    is_builtin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    nodes = db.relationship(
        'ScenarioNode', backref='scenario',
        cascade='all, delete-orphan',
        order_by='ScenarioNode.sort_order',
    )

    def to_dict(self, include_nodes=False):
        d = {
            'id': self.id,
            'name': self.name,
            'label': self.label,
            'description': self.description or '',
            'is_builtin': self.is_builtin,
            'is_active': self.is_active,
            'node_count': len(self.nodes),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_nodes:
            d['nodes'] = [n.to_dict() for n in self.nodes]
        return d


class ScenarioNode(db.Model):
    """场景节点 / 步骤。"""
    __tablename__ = 'scenario_node'

    id = db.Column(db.Integer, primary_key=True)
    scenario_id = db.Column(db.Integer, db.ForeignKey('scenario.id', ondelete='CASCADE'))
    key = db.Column(db.String(50), nullable=False)       # requirement
    name = db.Column(db.String(100), nullable=False)     # 需求
    role_prompt = db.Column(db.Text, default='')         # 角色提示词（本节点的 system prompt）
    gate = db.Column(db.Boolean, default=True)           # 节点完成后是否人工确认
    allowed_tools = db.Column(db.Text, default='[]')     # JSON 数组：MCP 工具名白名单
    skills = db.Column(db.Text, default='[]')            # JSON 数组：可用的 Skill 名
    sort_order = db.Column(db.Integer, default=0)

    def to_dict(self):
        return {
            'id': self.id,
            'scenario_id': self.scenario_id,
            'key': self.key,
            'name': self.name,
            'role_prompt': self.role_prompt or '',
            'gate': self.gate,
            'allowed_tools': parse_allowed_tools(self.allowed_tools),
            'skills': parse_allowed_tools(self.skills),
            'sort_order': self.sort_order,
        }


def parse_allowed_tools(raw):
    """把 stored JSON 字符串解析为 list，解析失败返回空列表。"""
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    try:
        val = json.loads(raw)
        return val if isinstance(val, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


class TaskState(db.Model):
    """任务实例（L4 状态）。"""
    __tablename__ = 'task_state'

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.String(50), unique=True, nullable=False)  # TODO-001
    scene = db.Column(db.String(100))                    # software_delivery
    title = db.Column(db.Text, default='')
    state = db.Column(db.String(30), default='running')  # running/awaiting_user/done/failed/paused
    current_node = db.Column(db.String(50))              # 当前执行到哪个节点 key
    plan = db.Column(db.Text, default='[]')              # JSON：节点序列快照
    artifacts = db.Column(db.Text, default='{}')         # JSON：{node_key: {summary, path}}
    pending_approval = db.Column(db.Text, default='{}')  # JSON：待确认信息
    traceability = db.Column(db.Text, default='[]')      # JSON：需求-交付物追踪
    history = db.Column(db.Text, default='[]')           # JSON：事件日志
    resume_context = db.Column(db.Text, default='{}')    # JSON：上下文重建
    workspace = db.Column(db.Text, default='')           # 工作空间（电脑文件夹绝对路径）
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    due = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'task_id': self.task_id,
            'scene': self.scene,
            'title': self.title or '',
            'state': self.state,
            'current_node': self.current_node,
            'plan': _loads(self.plan, []),
            'artifacts': _loads(self.artifacts, {}),
            'pending_approval': _loads(self.pending_approval, {}),
            'traceability': _loads(self.traceability, []),
            'history': _loads(self.history, []),
            'resume_context': _loads(self.resume_context, {}),
            'workspace': self.workspace or '',
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'due': self.due.isoformat() if self.due else None,
        }


def _loads(raw, default):
    """把 stored JSON 字符串解析为对象，失败返回 default。"""
    if raw is None:
        return default
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return default
