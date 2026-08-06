"""MCP 审批工具 handler 测试：list_candidates / approve_candidate / reject_candidate。

这三个工具是"LLM 不可自审批"原则下的人工审批接口。
- list_candidates 列出 pending 页面
- approve_candidate 通过审批
- reject_candidate 拒绝并删除

测试不 mock service 层，使用真实 DB（验证真实行为，非 Mock 行为）。
"""
import json

import pytest


class TestListCandidates:

    def test_returns_pending_pages(self, app, db):
        from modules.wiki.models import WikiPage
        with app.app_context():
            pending1 = WikiPage(
                title='待审1', slug='pend1', body='内容1', summary='摘要1',
                sources='[]', links='[]', review_status='pending',
            )
            pending2 = WikiPage(
                title='待审2', slug='pend2', body='内容2', summary='摘要2',
                sources='[]', links='[]', review_status='pending',
            )
            approved = WikiPage(
                title='已审', slug='appr', body='x', summary='',
                sources='[]', links='[]', review_status='approved',
            )
            db.session.add_all([pending1, pending2, approved])
            db.session.commit()

            from modules.mcp.tools_read import handle_list_candidates
            result = handle_list_candidates({})

        data = json.loads(result['content'][0]['text'])
        assert isinstance(data, list)
        assert len(data) == 2
        titles = [c['title'] for c in data]
        assert '待审1' in titles and '待审2' in titles
        assert '已审' not in titles

    def test_no_pending_returns_empty_list(self, app, db):
        with app.app_context():
            from modules.mcp.tools_read import handle_list_candidates
            result = handle_list_candidates({})
        data = json.loads(result['content'][0]['text'])
        assert data == []

    def test_each_candidate_has_preview_and_id(self, app, db):
        from modules.wiki.models import WikiPage
        with app.app_context():
            page = WikiPage(
                title='预览测试', slug='preview1', body='正文内容',
                summary='摘要', sources='[{"file":"src.md"}]',
                links='[]', review_status='pending',
            )
            db.session.add(page)
            db.session.commit()

            from modules.mcp.tools_read import handle_list_candidates
            result = handle_list_candidates({})

        data = json.loads(result['content'][0]['text'])
        item = data[0]
        assert 'id' in item
        assert 'slug' in item
        assert 'title' in item
        assert 'preview' in item


class TestApproveCandidate:

    def test_approve_changes_status_to_approved(self, app, db):
        from modules.wiki.models import WikiPage
        with app.app_context():
            page = WikiPage(
                title='审批', slug='approve_test', body='正文',
                summary='', sources='[]', links='[]',
                review_status='pending',
            )
            db.session.add(page)
            db.session.commit()
            page_id = page.id

            from modules.mcp.tools_write import handle_approve_candidate
            result = handle_approve_candidate({'id': page_id})

        data = json.loads(result['content'][0]['text'])
        assert data['approved'] is True
        assert data['id'] == page_id

        # 验证 DB 状态
        with app.app_context():
            page = db.session.get(WikiPage, page_id)
            assert page.review_status == 'approved'

    def test_approve_nonexistent_returns_isError(self, app, db):
        with app.app_context():
            from modules.mcp.tools_write import handle_approve_candidate
            result = handle_approve_candidate({'id': 9999})
        assert result.get('isError') is True

    def test_approve_already_approved_returns_isError(self, app, db):
        from modules.wiki.models import WikiPage
        with app.app_context():
            page = WikiPage(
                title='已审批', slug='already_appr', body='x',
                summary='', sources='[]', links='[]',
                review_status='approved',
            )
            db.session.add(page)
            db.session.commit()
            page_id = page.id

            from modules.mcp.tools_write import handle_approve_candidate
            result = handle_approve_candidate({'id': page_id})

        assert result.get('isError') is True

    def test_missing_id_arg_raises_mcperror(self, app):
        from modules.mcp.errors import MCPError
        with app.app_context():
            from modules.mcp.tools_write import handle_approve_candidate
            with pytest.raises(MCPError) as exc:
                handle_approve_candidate({})
            assert exc.value.code == -32602


class TestRejectCandidate:

    def test_reject_deletes_page_from_db(self, app, db):
        from modules.wiki.models import WikiPage
        with app.app_context():
            page = WikiPage(
                title='拒绝', slug='reject_test', body='x',
                summary='', sources='[]', links='[]',
                review_status='pending',
            )
            db.session.add(page)
            db.session.commit()
            page_id = page.id

            from modules.mcp.tools_write import handle_reject_candidate
            result = handle_reject_candidate({'id': page_id})

        data = json.loads(result['content'][0]['text'])
        assert data['rejected'] is True

        with app.app_context():
            page = db.session.get(WikiPage, page_id)
            assert page is None

    def test_reject_nonexistent_returns_isError(self, app, db):
        with app.app_context():
            from modules.mcp.tools_write import handle_reject_candidate
            result = handle_reject_candidate({'id': 9999})
        assert result.get('isError') is True

    def test_missing_id_arg_raises_mcperror(self, app):
        from modules.mcp.errors import MCPError
        with app.app_context():
            from modules.mcp.tools_write import handle_reject_candidate
            with pytest.raises(MCPError) as exc:
                handle_reject_candidate({})
            assert exc.value.code == -32602
