"""pytest 共享 fixtures。"""
import os
import sys

import pytest

# 把 src/ 加入 sys.path，让测试能直接 import modules.*
_SRC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src')
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)


@pytest.fixture
def app(tmp_path, monkeypatch):
    """构造一个隔离的 Flask app，resource 指向 tmp_path。

    每个 MCP 测试都拿到一个干净的应用 + 干净的文件系统。
    自动注册 mcp_bp，避免每个测试样板代码。

    同时 monkeypatch Config 的路径常量，让 wiki_service 等硬编码
    读 Config 的模块也指向 tmp_path。
    """
    from flask import Flask
    from extensions import db as _db
    from modules.mcp import mcp_bp
    from config import Config

    resource_dir = tmp_path / 'resource'
    resource_dir.mkdir()
    article_dir = resource_dir / 'article'
    article_dir.mkdir()
    wiki_dir = resource_dir / 'wiki'
    wiki_dir.mkdir()
    (wiki_dir / 'concepts').mkdir()
    (resource_dir / 'instance').mkdir()

    resource_path = str(resource_dir)
    # 关键：让所有读 Config 的模块（含 wiki_service）都指向 tmp_path
    monkeypatch.setattr(Config, 'RESOURCE_BASE_PATH', resource_path)
    monkeypatch.setattr(Config, 'ARTICLE_PATH', str(article_dir))
    monkeypatch.setattr(Config, 'WIKI_PATH', str(wiki_dir))
    monkeypatch.setattr(Config, 'INSTANCE_PATH', str(resource_dir / 'instance'))

    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
        RESOURCE_BASE_PATH=resource_path,
        ARTICLE_PATH=str(article_dir),
        IMAGE_PATH=str(resource_dir / 'img'),
        ATTACHMENT_PATH=str(resource_dir / 'attachments'),
        WIKI_PATH=str(wiki_dir),
        INSTANCE_PATH=str(resource_dir / 'instance'),
    )

    _db.init_app(app)
    if 'mcp' not in {bp.name for bp in app.blueprints.values()}:
        app.register_blueprint(mcp_bp)

    with app.app_context():
        # 导入所有 model 让 create_all 能创建对应表
        from modules.wiki.models import WikiPage  # noqa: F401
        _db.create_all()

    yield app


@pytest.fixture
def client(app):
    """Flask test client。"""
    return app.test_client()


@pytest.fixture
def db(app):
    """已初始化的 SQLAlchemy 实例。"""
    from extensions import db as _db
    with app.app_context():
        yield _db
