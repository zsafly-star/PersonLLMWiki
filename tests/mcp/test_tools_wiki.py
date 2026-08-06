"""MCP Wiki 工具 handler 测试：list_wiki_pages / read_wiki_page。

这两个工具只读，无成本。接 WikiPage 模型（approved/chat）+ wiki_service.read_concept_page。
"""
import json
import os

import pytest


# ---------- list_wiki_pages ----------

class TestListWikiPages:

    def test_returns_approved_pages_from_db(self, app, db):
        # 准备：往 DB 插入已审批的 WikiPage
        from modules.wiki.models import WikiPage
        with app.app_context():
            for title in ['概念A', '概念B']:
                page = WikiPage(
                    title=title,
                    slug=title.lower().replace(' ', '_'),
                    summary=f'{title} 的摘要',
                    body=f'# {title}\n\n正文。',
                    sources='[]',
                    links='[]',
                    review_status='approved',
                )
                db.session.add(page)
            db.session.commit()

            from modules.mcp.tools_read import handle_list_wiki_pages
            result = handle_list_wiki_pages({})

        data = json.loads(result['content'][0]['text'])
        assert isinstance(data, list)
        assert len(data) == 2
        titles = [p['title'] for p in data]
        assert '概念A' in titles
        assert '概念B' in titles

    def test_excludes_pending_pages(self, app, db):
        from modules.wiki.models import WikiPage
        with app.app_context():
            approved = WikiPage(
                title='已审批', slug='approved1', body='x', sources='[]',
                links='[]', review_status='approved',
            )
            pending = WikiPage(
                title='待审批', slug='pending1', body='y', sources='[]',
                links='[]', review_status='pending',
            )
            db.session.add(approved)
            db.session.add(pending)
            db.session.commit()

            from modules.mcp.tools_read import handle_list_wiki_pages
            result = handle_list_wiki_pages({})

        data = json.loads(result['content'][0]['text'])
        titles = [p['title'] for p in data]
        assert '已审批' in titles
        assert '待审批' not in titles

    def test_respects_limit_and_offset(self, app, db):
        from modules.wiki.models import WikiPage
        with app.app_context():
            for i in range(5):
                page = WikiPage(
                    title=f'概念{i}', slug=f'concept{i}', body='x', sources='[]',
                    links='[]', review_status='approved',
                )
                db.session.add(page)
            db.session.commit()

            from modules.mcp.tools_read import handle_list_wiki_pages
            result = handle_list_wiki_pages({'limit': 2, 'offset': 0})

        data = json.loads(result['content'][0]['text'])
        assert len(data) == 2

    def test_empty_db_returns_empty_list(self, app):
        with app.app_context():
            from modules.mcp.tools_read import handle_list_wiki_pages
            result = handle_list_wiki_pages({})
        data = json.loads(result['content'][0]['text'])
        assert data == []

    def test_each_page_has_required_fields(self, app, db):
        from modules.wiki.models import WikiPage
        with app.app_context():
            page = WikiPage(
                title='测试概念', slug='test_concept', summary='摘要',
                body='# 测试\n\n正文', sources='[{"file":"a.md"}]', links='[]',
                review_status='approved',
            )
            db.session.add(page)
            db.session.commit()

            from modules.mcp.tools_read import handle_list_wiki_pages
            result = handle_list_wiki_pages({})

        data = json.loads(result['content'][0]['text'])
        item = data[0]
        assert 'slug' in item
        assert 'title' in item
        assert 'source_count' in item


# ---------- read_wiki_page ----------

class TestReadWikiPage:

    def test_read_existing_page_returns_content_and_sources(self, app, db):
        from modules.wiki.models import WikiPage
        with app.app_context():
            page = WikiPage(
                title='向量检索',
                slug='vector_search',
                summary='向量检索摘要',
                body='# 向量检索\n\n详细内容。',
                sources='[{"file":"note.md","lines":"10-20"}]',
                links='["概念A"]',
                review_status='approved',
            )
            db.session.add(page)
            db.session.commit()

            from modules.mcp.tools_read import handle_read_wiki_page
            result = handle_read_wiki_page({'slug': 'vector_search'})

        data = json.loads(result['content'][0]['text'])
        assert data['title'] == '向量检索'
        assert data['slug'] == 'vector_search'
        assert '详细内容' in data.get('content', '')
        assert isinstance(data.get('sources'), list)

    def test_read_nonexistent_page_returns_isError(self, app):
        with app.app_context():
            from modules.mcp.tools_read import handle_read_wiki_page
            result = handle_read_wiki_page({'slug': 'does_not_exist'})
        assert result.get('isError') is True

    def test_missing_slug_arg_raises_mcperror(self, app):
        from modules.mcp.errors import MCPError
        with app.app_context():
            from modules.mcp.tools_read import handle_read_wiki_page
            with pytest.raises(MCPError) as exc:
                handle_read_wiki_page({})
            assert exc.value.code == -32602

    def test_read_falls_back_to_file_system(self, app):
        """DB 没有但文件系统有：从 wiki_service.read_concept_page 读。"""
        import json as _json
        wiki_concepts = os.path.join(app.config['WIKI_PATH'], 'concepts')
        os.makedirs(wiki_concepts, exist_ok=True)

        # 写一个带 frontmatter 的概念页
        frontmatter = {
            'title': '文件概念',
            'slug': 'file_concept',
            'summary': '文件摘要',
            'sources': [{'file': 'src.md'}],
        }
        content = '---\n' + _json.dumps(frontmatter, ensure_ascii=False, indent=2) + '\n---\n\n# 文件概念\n\n正文。\n'
        with open(os.path.join(wiki_concepts, 'file_concept.md'), 'w', encoding='utf-8') as f:
            f.write(content)

        with app.app_context():
            from modules.mcp.tools_read import handle_read_wiki_page
            result = handle_read_wiki_page({'slug': 'file_concept'})

        data = json.loads(result['content'][0]['text'])
        assert data['title'] == '文件概念'
        assert '正文' in data.get('content', '')
