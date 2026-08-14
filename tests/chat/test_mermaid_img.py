"""Mermaid 代理端点测试。

覆盖场景：
1. base64url 编码格式正确性
2. 简单 flowchart 正常渲染 (200)
3. 含中文标签的图表正常渲染
4. 空 code 返回错误
5. mermaid.ink 400 时代理正确上报
6. 多种图类型均可渲染
"""
import base64
import urllib.parse
from unittest.mock import patch

import pytest


# ---- 编码逻辑测试 ----
def _encode_mermaid(code):
    """与 routes.py 同等的 base64url 编码。"""
    return base64.urlsafe_b64encode(code.encode('utf-8')).decode('ascii').rstrip('=')


class TestMermaidEncoding:
    """base64url 编码正确性（纯逻辑，无需 Flask）。"""

    def test_simple_flowchart_encoding(self):
        code = 'flowchart TD\n    A --> B'
        e = _encode_mermaid(code)
        assert '+' not in e
        assert '=' not in e
        assert '\n' not in e

    def test_chinese_label_roundtrip(self):
        code = 'flowchart TD\n    START(["入口 START"]) --> R["Router 节点"]'
        e = _encode_mermaid(code)
        decoded = base64.urlsafe_b64decode(e + '==').decode('utf-8')
        assert '入口 START' in decoded
        assert 'Router 节点' in decoded

    def test_encoding_is_url_safe(self):
        for code in [
            'flowchart TD\n    A --> B',
            'sequenceDiagram\n    A->>B: hi',
            'classDiagram\n    class Foo { +bar() }',
        ]:
            e = _encode_mermaid(code)
            assert '?' not in e
            assert '#' not in e


# ---- Flask 端点集成测试 ----

class FakeResp200:
    status_code = 200
    content = b'\x89PNG\r\n\x1a\n'
    headers = {'Content-Type': 'image/png'}


class FakeResp400:
    status_code = 400
    content = b'Unknown diagram error'
    headers = {'Content-Type': 'text/plain'}


@pytest.fixture
def mermaid_client(app, client):
    """注册 chat_bp 后的 test client。"""
    with app.app_context():
        from modules.chat.routes import chat_bp
        if 'chat' not in {bp.name for bp in app.blueprints.values()}:
            app.register_blueprint(chat_bp)
    return client


class TestMermaidProxy:
    """代理端点集成测试。"""

    def test_valid_flowchart_returns_image(self, mermaid_client):
        with patch('modules.chat.routes.requests.get', return_value=FakeResp200):
            code = 'flowchart TD\n    A --> B'
            resp = mermaid_client.get('/api/chat/mermaid-img?code=' + urllib.parse.quote(code))
            assert resp.status_code == 200
            assert resp.content_type == 'image/png'

    def test_empty_code_returns_error(self, mermaid_client):
        resp = mermaid_client.get('/api/chat/mermaid-img?code=')
        j = resp.get_json()
        assert j is not None and j.get('code') != 200

    def test_mermaid_ink_400_reported(self, mermaid_client):
        with patch('modules.chat.routes.requests.get', return_value=FakeResp400):
            code = 'flowchart TD\n    invalid --> ???'
            resp = mermaid_client.get('/api/chat/mermaid-img?code=' + urllib.parse.quote(code))
            j = resp.get_json()
            assert j is not None
            assert '400' in str(j.get('message', ''))

    def test_chinese_labels_preserved(self, mermaid_client):
        with patch('modules.chat.routes.requests.get', return_value=FakeResp200):
            code = 'flowchart TD\n    A["中文标签"] --> B["另一个"]'
            resp = mermaid_client.get('/api/chat/mermaid-img?code=' + urllib.parse.quote(code))
            assert resp.status_code == 200

    def test_sequence_diagram(self, mermaid_client):
        with patch('modules.chat.routes.requests.get', return_value=FakeResp200):
            code = 'sequenceDiagram\n    participant A as "用户"\n    A->>B: 请求'
            resp = mermaid_client.get('/api/chat/mermaid-img?code=' + urllib.parse.quote(code))
            assert resp.status_code == 200

    def test_class_diagram(self, mermaid_client):
        with patch('modules.chat.routes.requests.get', return_value=FakeResp200):
            code = 'classDiagram\n    class "智能体Agent" {\n        +观察()\n    }'
            resp = mermaid_client.get('/api/chat/mermaid-img?code=' + urllib.parse.quote(code))
            assert resp.status_code == 200

    def test_mindmap(self, mermaid_client):
        with patch('modules.chat.routes.requests.get', return_value=FakeResp200):
            code = 'mindmap\n    root(("中心"))\n        分支A["节点A"]'
            resp = mermaid_client.get('/api/chat/mermaid-img?code=' + urllib.parse.quote(code))
            assert resp.status_code == 200
