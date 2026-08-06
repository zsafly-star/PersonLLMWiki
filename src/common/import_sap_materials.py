"""SAP 物料数据 → PersonLLMWiki 批量导入工具（Phase 2 配套）。

从 SAP MCP 的 materials.db 读取 spec_params 表，
将每个有规格书的物料编译成一个 Wiki 概念页面，
批量导入到 PersonLLMWiki 的 DB + 文件系统。

用法：
  python -m common.import_sap_materials --db-path /path/to/materials.db

或在 PersonLLMWiki 运行时通过 API 触发：
  POST /api/wiki/import-sap
"""

import os
import sys
import json
import sqlite3
import argparse
import hashlib
from datetime import datetime


def _generate_wiki_body(matnr, maktx, category, params, spec_pdf_url='', confidence=''):
    """从物料参数生成 Wiki 页面正文（Markdown）"""
    lines = []

    if category:
        lines.append(f'**物料类别**: {category}\n')

    if params:
        lines.append('## 技术参数\n')
        lines.append('| 参数 | 值 |')
        lines.append('|------|----|')
        for key, value in params.items():
            lines.append(f'| {key} | {value} |')
        lines.append('')

    if spec_pdf_url:
        lines.append(f'## 规格书\n')
        lines.append(f'[查看规格书 PDF]({spec_pdf_url})\n')

    if confidence:
        lines.append(f'> 参数提取置信度: {confidence}\n')

    lines.append(f'^[SAP 物料:{matnr}]')

    return '\n'.join(lines)


def _generate_summary(maktx, category, params):
    """生成摘要"""
    parts = []
    if maktx:
        parts.append(maktx)
    if category:
        parts.append(category)
    if params:
        param_str = ' '.join(f'{k}:{v}' for k, v in list(params.items())[:5])
        parts.append(param_str)
    return ' | '.join(parts)[:200]


def _generate_slug(matnr):
    """从物料号生成 slug"""
    return f'sap_material_{matnr}'


def import_materials_from_sap_db(sap_db_path, batch_size=None, dry_run=False):
    """从 SAP MCP 的 SQLite 导入物料到 Wiki。

    Args:
        sap_db_path: SAP MCP 的 materials.db 路径
        batch_size: 限制导入数量（None = 全量）
        dry_run: True 只统计不写入

    Returns:
        {total, imported, skipped, errors}
    """
    if not os.path.isfile(sap_db_path):
        return {'error': f'数据库不存在: {sap_db_path}'}

    # 连接 SAP MCP 的 SQLite（只读）
    sap_conn = sqlite3.connect(f'file:{sap_db_path}?mode=ro', uri=True)
    sap_conn.row_factory = sqlite3.Row
    cursor = sap_conn.cursor()

    query = 'SELECT matnr, maktx, category, params_json, spec_pdf_name, spec_pdf_url, extracted_at, confidence FROM spec_params'
    if batch_size:
        query += f' LIMIT {batch_size}'

    cursor.execute(query)
    rows = cursor.fetchall()
    sap_conn.close()

    if dry_run:
        return {
            'total': len(rows),
            'imported': 0,
            'skipped': 0,
            'errors': 0,
            'dry_run': True,
            'message': f'试运行：发现 {len(rows)} 条物料数据可导入',
        }

    # 导入到 PersonLLMWiki
    # 延迟导入——确保在 Flask app context 内运行
    from extensions import db
    from modules.wiki.models import WikiPage
    from modules.wiki import wiki_service

    imported = 0
    skipped = 0
    errors = 0

    for row in rows:
        matnr = row['matnr']
        maktx = row['maktx'] or ''
        category = row['category'] or ''
        spec_pdf_url = row['spec_pdf_url'] or ''
        confidence = row['confidence'] or ''
        extracted_at = row['extracted_at'] or ''

        try:
            params = json.loads(row['params_json']) if row['params_json'] else {}
        except json.JSONDecodeError:
            params = {}

        slug = _generate_slug(matnr)
        title = f'{maktx} ({matnr})' if maktx else f'物料 {matnr}'
        summary = _generate_summary(maktx, category, params)
        body = _generate_wiki_body(matnr, maktx, category, params, spec_pdf_url, confidence)
        sources = [f'SAP:{matnr}']
        if extracted_at:
            sources.append(f'提取时间:{extracted_at}')

        # 检查是否已存在
        existing = WikiPage.query.filter_by(slug=slug).first()
        content_hash = hashlib.sha256(body.encode('utf-8')).hexdigest()

        if existing and existing.content_hash == content_hash:
            skipped += 1
            continue

        if existing:
            # 更新
            existing.title = title
            existing.summary = summary
            existing.body = body
            existing.kind = 'material'
            existing.sources = json.dumps(sources, ensure_ascii=False)
            existing.content_hash = content_hash
            existing.review_status = 'approved'
            existing.author = 'sap_import'
        else:
            # 新建
            page = WikiPage(
                title=title,
                slug=slug,
                kind='material',
                summary=summary,
                body=body,
                sources=json.dumps(sources, ensure_ascii=False),
                content_hash=content_hash,
                review_status='approved',
                author='sap_import',
            )
            db.session.add(page)

        # 写概念页文件
        wiki_service.save_concept_page(slug, title, body, summary, sources, 'material')

        imported += 1

    db.session.commit()

    # 更新索引
    try:
        wiki_service.generate_index()
    except Exception:
        pass

    # 异步更新向量索引
    try:
        from modules.wiki.compiler.retrieval import update_page_embeddings
        update_page_embeddings()
    except Exception:
        pass

    return {
        'total': len(rows),
        'imported': imported,
        'skipped': skipped,
        'errors': errors,
    }


# ────────────────── CLI 入口 ──────────────────

def main():
    parser = argparse.ArgumentParser(description='SAP 物料数据导入 PersonLLMWiki')
    parser.add_argument('--db-path', required=True, help='SAP MCP materials.db 路径')
    parser.add_argument('--batch', type=int, default=None, help='限制导入数量（测试用）')
    parser.add_argument('--dry-run', action='store_true', help='只统计不写入')
    args = parser.parse_args()

    # 初始化 Flask app context
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from app import app

    with app.app_context():
        result = import_materials_from_sap_db(
            args.db_path,
            batch_size=args.batch,
            dry_run=args.dry_run,
        )

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
