"""MCP 检索工具 handler 测试：search_kb。

成本：消耗 OpenAI Embedding 配额。
测试策略：mock retrieval.hybrid_search，验证 handler 包装逻辑，
不真调 OpenAI（避免 testing-anti-patterns Anti-pattern 1: 测试 Mock 行为）。
"""
import json
from unittest.mock import patch

import pytest


class TestSearchKb:

    def test_returns_ranked_results_with_snippet_and_score(self, app, db):
        from modules.wiki.models import WikiPage
        with app.app_context():
            # 准备：DB 里有几页，retrieval 会查到
            for slug, title, body in [
                ('vec', '向量检索', '向量检索的正文内容'),
                ('bm25', '关键词匹配', 'BM25 关键词算法'),
            ]:
                page = WikiPage(
                    title=title, slug=slug, body=body, summary=title,
                    sources='[]', links='[]', review_status='approved',
                )
                db.session.add(page)
            db.session.commit()

            # mock hybrid_search 返回 [(slug, title, score)]
            fake_results = [('vec', '向量检索', 0.92), ('bm25', '关键词匹配', 0.65)]
            with patch('modules.wiki.compiler.retrieval.hybrid_search',
                       return_value=fake_results):
                from modules.mcp.tools_search import handle_search_kb
                result = handle_search_kb({'query': '向量检索'})

        data = json.loads(result['content'][0]['text'])
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]['slug'] == 'vec'
        assert data[0]['title'] == '向量检索'
        assert data[0]['score'] == 0.92
        assert 'snippet' in data[0]

    def test_missing_query_arg_raises_mcperror(self, app):
        from modules.mcp.errors import MCPError
        with app.app_context():
            from modules.mcp.tools_search import handle_search_kb
            with pytest.raises(MCPError) as exc:
                handle_search_kb({})
            assert exc.value.code == -32602

    def test_empty_query_raises_mcperror(self, app):
        from modules.mcp.errors import MCPError
        with app.app_context():
            from modules.mcp.tools_search import handle_search_kb
            with pytest.raises(MCPError):
                handle_search_kb({'query': '   '})

    def test_top_k_default_5(self, app, db):
        from modules.wiki.models import WikiPage
        with app.app_context():
            page = WikiPage(
                title='x', slug='x1', body='y', summary='',
                sources='[]', links='[]', review_status='approved',
            )
            db.session.add(page)
            db.session.commit()

            captured_args = {}

            def fake_hybrid(question, top_k=5):
                captured_args['top_k'] = top_k
                return []

            with patch('modules.wiki.compiler.retrieval.hybrid_search',
                       side_effect=fake_hybrid):
                from modules.mcp.tools_search import handle_search_kb
                handle_search_kb({'query': 'something'})

        assert captured_args['top_k'] == 5

    def test_top_k_capped_at_10(self, app, db):
        from modules.wiki.models import WikiPage
        with app.app_context():
            page = WikiPage(
                title='x', slug='x2', body='y', summary='',
                sources='[]', links='[]', review_status='approved',
            )
            db.session.add(page)
            db.session.commit()

            captured = {}

            def fake_hybrid(question, top_k=5):
                captured['top_k'] = top_k
                return []

            with patch('modules.wiki.compiler.retrieval.hybrid_search',
                       side_effect=fake_hybrid):
                from modules.mcp.tools_search import handle_search_kb
                # 用户请求 100，应被限制到 10
                handle_search_kb({'query': 'x', 'top_k': 100})

        assert captured['top_k'] == 10

    def test_empty_results_returns_empty_list(self, app, db):
        with app.app_context():
            with patch('modules.wiki.compiler.retrieval.hybrid_search',
                       return_value=[]):
                from modules.mcp.tools_search import handle_search_kb
                result = handle_search_kb({'query': '不存在的内容'})
        data = json.loads(result['content'][0]['text'])
        assert data == []

    def test_returns_source_type_field(self, app, db):
        from modules.wiki.models import WikiPage
        with app.app_context():
            page = WikiPage(
                title='概念', slug='concept', body='正文', summary='摘要',
                sources='[]', links='[]', review_status='approved',
            )
            db.session.add(page)
            db.session.commit()

            with patch('modules.wiki.compiler.retrieval.hybrid_search',
                       return_value=[('concept', '概念', 0.8)]):
                from modules.mcp.tools_search import handle_search_kb
                result = handle_search_kb({'query': '概念'})
        data = json.loads(result['content'][0]['text'])
        assert 'source_type' in data[0]
        # DB 找到的页面，source_type 应为 wiki
        assert data[0]['source_type'] == 'wiki'

    def test_retrieval_failure_returns_isError_with_cost_warning(self, app):
        """检索失败时返回 isError 并提示可能已消耗 Embedding 配额。"""
        with app.app_context():
            with patch('modules.wiki.compiler.retrieval.hybrid_search',
                       side_effect=RuntimeError('OpenAI API error')):
                from modules.mcp.tools_search import handle_search_kb
                result = handle_search_kb({'query': 'x'})

        assert result.get('isError') is True
        text = result['content'][0]['text']
        # 错误信息应包含成本提示
        assert 'Embedding' in text or '配额' in text or 'OpenAI' in text
