"""MCP 图谱与文件夹工具测试：get_graph / create_folder。

get_graph：从已审批 WikiPage 构建节点和边，无 seed 返回全图（硬上限 80）。
create_folder：在 article 根目录内创建文件夹。
"""
import json
import os

import pytest


# ---------- get_graph ----------

class TestGetGraph:

    def test_returns_nodes_and_edges(self, app, db):
        from modules.wiki.models import WikiPage
        with app.app_context():
            # 两个互相链接的概念
            p1 = WikiPage(
                title='概念A', slug='concept_a', body='# A\n\n[[概念B]]',
                summary='', sources='[]', links='["概念B"]',
                review_status='approved',
            )
            p2 = WikiPage(
                title='概念B', slug='concept_b', body='# B',
                summary='', sources='[]', links='[]',
                review_status='approved',
            )
            db.session.add_all([p1, p2])
            db.session.commit()

            from modules.mcp.tools_read import handle_get_graph
            result = handle_get_graph({})

        data = json.loads(result['content'][0]['text'])
        assert 'nodes' in data
        assert 'edges' in data
        assert isinstance(data['nodes'], list)
        assert isinstance(data['edges'], list)
        # 至少有这两个节点
        titles = [n.get('title', '') for n in data['nodes']]
        assert any('概念A' in t for t in titles)
        assert any('概念B' in t for t in titles)

    def test_empty_db_returns_empty_graph(self, app):
        with app.app_context():
            from modules.mcp.tools_read import handle_get_graph
            result = handle_get_graph({})
        data = json.loads(result['content'][0]['text'])
        assert data['nodes'] == []
        assert data['edges'] == []

    def test_node_count_hard_cap_80(self, app, db):
        """超过 80 个节点时必须截断到 80。"""
        from modules.wiki.models import WikiPage
        with app.app_context():
            for i in range(100):
                p = WikiPage(
                    title=f'概念{i}', slug=f'concept_{i}', body=f'# 概念{i}',
                    summary='', sources='[]', links='[]',
                    review_status='approved',
                )
                db.session.add(p)
            db.session.commit()

            from modules.mcp.tools_read import handle_get_graph
            result = handle_get_graph({})

        data = json.loads(result['content'][0]['text'])
        assert len(data['nodes']) <= 80

    def test_seed_returns_local_neighborhood(self, app, db):
        """seed 模式只返回种子节点及其邻居。"""
        from modules.wiki.models import WikiPage
        with app.app_context():
            # 中心节点连到多个其他节点
            center = WikiPage(
                title='中心', slug='center', body='中心',
                summary='', sources='[]',
                links='["邻居1", "邻居2", "邻居3"]',
                review_status='approved',
            )
            for name in ['邻居1', '邻居2', '邻居3', '孤立节点']:
                slug = name.lower().replace(' ', '_')
                p = WikiPage(
                    title=name, slug=slug, body=f'# {name}',
                    summary='', sources='[]', links='[]',
                    review_status='approved',
                )
                db.session.add(p)
            db.session.add(center)
            db.session.commit()

            from modules.mcp.tools_read import handle_get_graph
            result = handle_get_graph({'seed': 'center'})

        data = json.loads(result['content'][0]['text'])
        # seed 模式应该只包含中心 + 邻居，不含孤立节点
        ids = [n.get('id') for n in data['nodes']]
        titles = [n.get('title') for n in data['nodes']]
        assert 'center' in ids or any('中心' in str(t) for t in titles)
        # 孤立节点不应出现
        assert '孤立节点' not in ids
        assert not any('孤立' in str(t) for t in titles)

    def test_seed_nonexistent_returns_isError_or_empty(self, app, db):
        with app.app_context():
            from modules.mcp.tools_read import handle_get_graph
            result = handle_get_graph({'seed': 'does_not_exist'})
        # seed 不存在时返回空图或 isError
        if result.get('isError'):
            pass  # 接受 isError
        else:
            data = json.loads(result['content'][0]['text'])
            assert data['nodes'] == []


# ---------- create_folder ----------

class TestCreateFolder:

    def test_creates_folder_under_article_root(self, app):
        with app.test_request_context():
            from modules.mcp.tools_write import handle_create_folder
            result = handle_create_folder({'path': '新目录'})

        data = json.loads(result['content'][0]['text'])
        assert data['created'] is True
        assert 'path' in data

        article_root = app.config['ARTICLE_PATH']
        assert os.path.isdir(os.path.join(article_root, '新目录'))

    def test_existing_folder_returns_created_false(self, app):
        article_root = app.config['ARTICLE_PATH']
        os.makedirs(os.path.join(article_root, '已存在'))

        with app.test_request_context():
            from modules.mcp.tools_write import handle_create_folder
            result = handle_create_folder({'path': '已存在'})

        data = json.loads(result['content'][0]['text'])
        assert data['created'] is False

    def test_nested_path_creates_parents(self, app):
        with app.test_request_context():
            from modules.mcp.tools_write import handle_create_folder
            result = handle_create_folder({'path': '父/子/孙'})

        data = json.loads(result['content'][0]['text'])
        assert data['created'] is True

        article_root = app.config['ARTICLE_PATH']
        assert os.path.isdir(os.path.join(article_root, '父', '子', '孙'))

    def test_path_traversal_raises(self, app):
        from modules.mcp.errors import MCPError
        with app.test_request_context():
            from modules.mcp.tools_write import handle_create_folder
            with pytest.raises(MCPError) as exc:
                handle_create_folder({'path': '../../../etc'})
            assert exc.value.code == -32602

    def test_missing_path_arg_raises(self, app):
        from modules.mcp.errors import MCPError
        with app.test_request_context():
            from modules.mcp.tools_write import handle_create_folder
            with pytest.raises(MCPError):
                handle_create_folder({})

    def test_icon_written_to_meta(self, app):
        """create_folder 时如果传 icon，应写入 .zsnote.json。"""
        with app.test_request_context():
            from modules.mcp.tools_write import handle_create_folder
            result = handle_create_folder({'path': '带图标', 'icon': '📁'})

        article_root = app.config['ARTICLE_PATH']
        meta_path = os.path.join(article_root, '带图标', '.zsnote.json')
        assert os.path.isfile(meta_path)
        with open(meta_path, 'r', encoding='utf-8') as f:
            meta = json.load(f)
        assert meta.get('icon') == '📁'
