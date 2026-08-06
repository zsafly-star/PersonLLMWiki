"""Embedding API 配置（单例）。

与 chat LLM 配置独立，因为 DeepSeek 等对话模型不提供 embedding API。
支持任意 OpenAI 兼容的 embedding 服务（OpenAI / 智谱 / 阿里千问等）。
"""

from datetime import datetime
from extensions import db


class EmbeddingConfig(db.Model):
    __tablename__ = 'embedding_config'

    id = db.Column(db.Integer, primary_key=True)
    api_key = db.Column(db.String(500), default='')
    base_url = db.Column(db.String(500), default='')
    model = db.Column(db.String(100), default='text-embedding-3-small')
    is_active = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'api_key': self._mask_key(self.api_key) if self.api_key else '',
            'base_url': self.base_url,
            'model': self.model,
            'is_active': self.is_active,
        }

    def to_dict_with_key(self):
        return {
            'id': self.id,
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


class EmbeddingConfigService:
    @staticmethod
    def get():
        """获取单例配置（仅一条记录）"""
        return EmbeddingConfig.query.first()

    @staticmethod
    def get_dict():
        config = EmbeddingConfigService.get()
        return config.to_dict() if config else None

    @staticmethod
    def get_active():
        """获取已启用的配置 ORM 对象"""
        return EmbeddingConfig.query.filter_by(is_active=True).first()

    @staticmethod
    def save(data):
        """保存配置（upsert 单例）"""
        config = EmbeddingConfig.query.first()
        if not config:
            config = EmbeddingConfig()
            db.session.add(config)

        # api_key 空串不覆盖（编辑时前端留空表示不改）
        if data.get('api_key'):
            config.api_key = data['api_key']
        config.base_url = data.get('base_url', '')
        if data.get('model'):
            config.model = data['model']
        config.is_active = data.get('is_active', True)

        db.session.commit()
        return config.to_dict()

    @staticmethod
    def test_connection():
        """测试 embedding API 连通性"""
        config = EmbeddingConfigService.get_active()
        if not config:
            return {'success': False, 'message': '未配置 Embedding API'}

        if not config.api_key:
            return {'success': False, 'message': '未配置 API Key'}

        try:
            import openai
            kwargs = {'api_key': config.api_key}
            if config.base_url:
                kwargs['base_url'] = config.base_url

            client = openai.OpenAI(**kwargs)
            response = client.embeddings.create(
                model=config.model,
                input='测试',
            )
            dim = len(response.data[0].embedding)
            return {
                'success': True,
                'message': f'连接成功，模型: {config.model}，维度: {dim}',
            }
        except Exception as e:
            return {'success': False, 'message': str(e)}
