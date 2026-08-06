from datetime import datetime
from extensions import db


class LLMProviderConfig(db.Model):
    __tablename__ = 'llm_provider_config'

    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    api_key = db.Column(db.String(500), default='')
    base_url = db.Column(db.String(500), default='')
    model = db.Column(db.String(100), default='')
    is_active = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'provider': self.provider,
            'name': self.name,
            'api_key': self._mask_key(self.api_key) if self.api_key else '',
            'base_url': self.base_url,
            'model': self.model,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

    def to_dict_with_key(self):
        return {
            'id': self.id,
            'provider': self.provider,
            'name': self.name,
            'api_key': self.api_key,
            'base_url': self.base_url,
            'model': self.model,
            'is_active': self.is_active,
        }

    @staticmethod
    def _mask_key(key):
        if not key or len(key) < 8:
            return '****'
        return key[:4] + '****' + key[-4:]


class LLMConfigService:
    @staticmethod
    def get_all():
        configs = LLMProviderConfig.query.order_by(LLMProviderConfig.created_at.desc()).all()
        return [c.to_dict() for c in configs]

    @staticmethod
    def get_by_id(config_id):
        config = LLMProviderConfig.query.get(config_id)
        return config.to_dict_with_key() if config else None

    @staticmethod
    def get_active():
        config = LLMProviderConfig.query.filter_by(is_active=True).first()
        return config

    @staticmethod
    def create(data):
        if data.get('is_active'):
            LLMProviderConfig.query.filter_by(is_active=True).update({'is_active': False})

        config = LLMProviderConfig(
            provider=data.get('provider'),
            name=data.get('name', ''),
            api_key=data.get('api_key', ''),
            base_url=data.get('base_url', ''),
            model=data.get('model', ''),
            is_active=data.get('is_active', False),
        )
        db.session.add(config)
        db.session.commit()
        return config.to_dict()

    @staticmethod
    def update(config_id, data):
        config = LLMProviderConfig.query.get(config_id)
        if not config:
            return None

        if 'is_active' in data and data['is_active']:
            LLMProviderConfig.query.filter_by(is_active=True).update({'is_active': False})

        for field in ['provider', 'name', 'api_key', 'base_url', 'model', 'is_active']:
            if field in data:
                setattr(config, field, data[field])

        db.session.commit()
        return config.to_dict()

    @staticmethod
    def delete(config_id):
        config = LLMProviderConfig.query.get(config_id)
        if not config:
            return False
        db.session.delete(config)
        db.session.commit()
        return True

    @staticmethod
    def test_connection(config_id):
        config = LLMProviderConfig.query.get(config_id)
        if not config:
            return {'success': False, 'message': '配置不存在'}

        from common.llm import LLMService
        try:
            kwargs = {}
            if config.api_key:
                kwargs['api_key'] = config.api_key
            if config.base_url:
                kwargs['base_url'] = config.base_url

            adapter = LLMService.get_adapter(config.provider, **kwargs)
            model = config.model or adapter.get_models()[0]
            result = adapter.chat(
                [{'role': 'user', 'content': '请回复"连接成功"'}],
                model=model
            )
            # chat() 可能返回 ChatCompletionMessage 对象（含 tool_calls），
            # 取 .content 字符串用于 JSON 序列化
            if hasattr(result, 'content'):
                result = result.content
            return {'success': True, 'message': result}
        except Exception as e:
            return {'success': False, 'message': str(e)}
