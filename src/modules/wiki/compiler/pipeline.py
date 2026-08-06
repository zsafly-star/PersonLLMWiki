import os
import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from flask import current_app
from extensions import db
from common.llm import LLMService
from common.llm_config import LLMConfigService
from . import prompts
from .status import (
    already_running, reset, set_progress, add_error,
    increment_completed, set_total, finish, get_compile_status,
)
from .hasher import get_compiled_hashes, save_file_hashes, detect_changed_files
from .extractor import get_llm, extract_concepts, batch_extract_concepts, merge_concepts
from .generator import generate_page, generate_candidate_page
from .retrieval import hybrid_search, update_page_embeddings
from ..models import WikiPage
from .. import wiki_service


def _init_wiki():
    concepts_dir = wiki_service.get_concepts_dir()
    queries_dir = wiki_service.get_queries_dir()

    if os.path.isdir(concepts_dir):
        for f in os.listdir(concepts_dir):
            if f.endswith('.md'):
                os.remove(os.path.join(concepts_dir, f))

    if os.path.isdir(queries_dir):
        for f in os.listdir(queries_dir):
            if f.endswith('.md'):
                os.remove(os.path.join(queries_dir, f))

    WikiPage.query.delete()
    db.session.commit()
    wiki_service.save_source_hashes({})


def compile_wiki(app, incremental=True, init=False):
    if already_running():
        return {'status': 'already_running'}

    reset('启动编译...')
    t = threading.Thread(target=_compile_worker, args=(app, incremental, init))
    t.daemon = True
    t.start()

    return {'status': 'started'}


def _compile_worker(app, incremental, init):
    with app.app_context():
        _do_compile(incremental=incremental, init=init)


def _do_compile(incremental=True, init=False):
    reset('扫描文章目录')

    try:
        wiki_service.ensure_wiki_dirs()

        if init or not incremental:
            set_progress('初始化 Wiki...')
            _init_wiki()

        article_files = wiki_service.scan_article_files()
        if not article_files:
            finish('文章目录下没有 .md 文件')
            return

        existing_pages = {p.slug: p for p in WikiPage.query.all()}
        compiled_hashes = get_compiled_hashes()

        if incremental:
            changed_files = detect_changed_files(article_files, compiled_hashes)
            set_progress(f'检测到 {len(changed_files)} 个文件需要更新（共 {len(article_files)} 个）')
        else:
            changed_files = article_files
            set_progress('执行全量编译')

        if not changed_files:
            finish('所有文件已是最新，无需编译')
            return

        adapter, model = get_llm()
        set_total(len(changed_files))

        all_concepts = _phase1_extract(adapter, model, changed_files)

        if not all_concepts:
            finish('没有需要更新的概念')
            return

        set_progress(f'生成页面 (共 {len(all_concepts)} 个概念)')

        merged = merge_concepts(all_concepts)

        existing_concept_names = {p.title for p in WikiPage.query.with_entities(WikiPage.title).all()}
        all_concept_names = set(merged.keys()) | existing_concept_names
        known_concepts_str = ', '.join(sorted(all_concept_names))

        app_ref = current_app._get_current_object()
        generated_slugs = _phase2_generate(
            app_ref, adapter, model, merged, existing_pages, known_concepts_str
        )

        wiki_service.generate_index()
        save_file_hashes(compiled_hashes, changed_files)

        try:
            set_progress('更新向量索引...')
            update_page_embeddings()
        except Exception:
            pass

        finish('编译完成')

    except Exception as e:
        import traceback
        set_progress(f'编译失败: {str(e)}')
        add_error(traceback.format_exc())
        db.session.rollback()
        finish(f'编译失败: {str(e)}')


def _phase1_extract(adapter, model, changed_files):
    all_concepts = []
    batch_size = 5
    total_files = len(changed_files)
    processed_count = 0

    while processed_count < total_files:
        if processed_count > 0 and batch_size < 10:
            avg_len = sum(len(f['content']) for f in changed_files[:processed_count]) / processed_count
            if avg_len < 2000:
                batch_size = min(10, batch_size + 1)
            elif avg_len > 5000:
                batch_size = max(3, batch_size - 1)

        batch_end = min(processed_count + batch_size, total_files)
        batch_files = changed_files[processed_count:batch_end]

        set_progress(f'批量提取概念 ({processed_count + 1}-{batch_end}/{total_files})，批次大小: {len(batch_files)}')

        try:
            concepts = batch_extract_concepts(adapter, model, batch_files)
            all_concepts.extend(concepts)
            increment_completed(len(batch_files))
            processed_count = batch_end
        except RuntimeError:
            set_progress('批量提取失败，降级为逐个提取')
            for f in batch_files:
                set_progress(f'提取概念 ({processed_count + 1}/{total_files}): {f["title"]}')
                try:
                    concepts = extract_concepts(adapter, model, f['title'], f['content'])
                    for concept in concepts:
                        concept['_source_title'] = f['title']
                        concept['_source_path'] = f['path']
                        concept['_source_hash'] = f['hash']
                    all_concepts.extend(concepts)
                except RuntimeError as ee:
                    error_msg = f'{f["title"]}: {str(ee)}'
                    set_progress(f'编译失败: {error_msg}')
                    add_error(error_msg)
                    finish(f'编译失败: {error_msg}')
                    return []
                except Exception as ee:
                    add_error(f'{f["title"]}: {str(ee)}')

                processed_count += 1
                increment_completed()

    return all_concepts


def _phase2_generate(app_ref, adapter, model, merged, existing_pages, known_concepts_str):
    generated_slugs = []
    max_workers = 5
    merged_list = list(merged.items())
    total_concepts = len(merged_list)
    completed_count = 0
    error_stop = threading.Event()
    first_error = [None]

    def generate_one(item):
        nonlocal completed_count
        concept_name, entries = item
        if error_stop.is_set():
            return None
        with app_ref.app_context():
            try:
                slug = generate_page(adapter, model, concept_name, entries, existing_pages, known_concepts_str)
                completed_count += 1
                set_progress(f'生成页面 ({completed_count}/{total_concepts}): {concept_name}')
                return slug
            except RuntimeError as e:
                error_stop.set()
                first_error[0] = (concept_name, str(e))
                return None
            except Exception as e:
                add_error(f'生成 {concept_name} 失败: {str(e)}')
                return None

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(generate_one, item): item for item in merged_list}

        for future in as_completed(futures):
            if error_stop.is_set():
                executor.shutdown(wait=False, cancel_futures=True)
                break
            result = future.result()
            if result is not None:
                generated_slugs.append(result)

    if first_error[0]:
        concept_name, err_msg = first_error[0]
        error_msg = f'生成 {concept_name} 失败: {err_msg}'
        set_progress(f'编译失败: {error_msg}')
        add_error(error_msg)
        finish(f'编译失败: {error_msg}')
        wiki_service.generate_index()
        return generated_slugs

    return generated_slugs


def query_wiki(question, save=False):
    adapter, model = get_llm()

    try:
        results = hybrid_search(question, top_k=5)
    except Exception:
        results = []

    if results:
        pages_data = []
        for slug, title, score in results:
            page = WikiPage.query.filter_by(slug=slug).first()
            if page:
                pages_data.append({
                    'title': page.title,
                    'body': page.body[:2000] if page.body else '',
                    'summary': page.summary or '',
                })

        if pages_data:
            context_parts = []
            for pd in pages_data:
                context_parts.append(f"## {pd['title']}\n{pd['summary']}\n{pd['body']}")
            context = '\n\n'.join(context_parts)
        else:
            context = _fallback_context()
    else:
        context = _fallback_context()

    prompt = prompts.QUERY_ANSWER_PROMPT.format(context=context, question=question)
    messages = [{'role': 'user', 'content': prompt}]
    answer = adapter.chat(messages, model=model)

    if save:
        import time
        slug = f"q_{int(time.time())}"
        wiki_service.save_query_page(slug, question, answer)

    return {'answer': answer, 'sources': [r[1] for r in results[:3]] if results else []}


def _fallback_context():
    pages = WikiPage.query.order_by(WikiPage.updated_at.desc()).limit(10).all()
    context_parts = []
    for p in pages:
        context_parts.append(f"## {p.title}\n{p.body[:500]}")
    return '\n\n'.join(context_parts)
