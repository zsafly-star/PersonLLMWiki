import json
from datetime import datetime
from extensions import db

class ChatSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    model_name = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'model_name': self.model_name,
            'created_at': self.created_at.isoformat() + 'Z' if self.created_at else None,
            'updated_at': self.updated_at.isoformat() + 'Z' if self.updated_at else None
        }

class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('chat_session.id'))
    role = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text, nullable=False)
    thinking_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    session = db.relationship('ChatSession', backref=db.backref('messages', lazy=True))

    def to_dict(self):
        result = {
            'id': self.id,
            'session_id': self.session_id,
            'role': self.role,
            'content': self.content,
            'thinking_json': self.thinking_json,
            'exported_files': [],
            'created_at': self.created_at.isoformat() + 'Z' if self.created_at else None
        }
        # 从 thinking_json 中提取导出文件列表
        if self.thinking_json:
            try:
                tj = json.loads(self.thinking_json)
                if isinstance(tj, dict):
                    result['exported_files'] = tj.get('exported_files', [])
            except (ValueError, TypeError):
                pass
        return result
