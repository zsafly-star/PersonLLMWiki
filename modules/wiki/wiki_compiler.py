import os
import json
import re
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from flask import current_app
from extensions import db
from common.llm import LLMService
from common.llm_config import LLMConfigService
from .models import WikiPage
from . import wiki_service

_compile_status = {
    'running': False,
    'progress': '',
    'errors': [],
    'completed': 0,
    'total': 0,
}

_status_lock = threading.Lock()
_db_lock = threading.Lock()


def get_compile_status():
    with _status_lock:
        return dict(_compile_status)


def _get_llm():
    config = LLMConfigService.get_active()
    if not config:
        raise RuntimeError('\u672a\u914d\u7f6e LLM')
    adapter = LLMService.get_adapter(config.provider, api_key=config.api_key, base_url=config.base_url)
    model = config.model or 'gpt-4o'
    return adapter, model


def _get_compiled_hashes():
    return wiki_service.load_source_hashes()


def _save_file_hashes(existing_hashes, processed_files):
    for f in processed_files:
        existing_hashes[f['title']] = f['hash']
    wiki_service.save_source_hashes(existing_hashes)


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
    if _compile_status['running']:
        return {'status': 'already_running'}

    _compile_status['running'] = True
    _compile_status['progress'] = '\u542f\u52a8\u7f16\u8bd1...'
    _compile_status['errors'] = []
    _compile_status['completed'] = 0
    _compile_status['total'] = 0

    t = threading.Thread(target=_compile_worker, args=(app, incremental, init))
    t.daemon = True
    t.start()

    return {'status': 'started'}


def _compile_worker(app, incremental, init):
    with app.app_context():
        _do_compile(incremental=incremental, init=init)


def _do_compile(incremental=True, init=False):
    _compile_status['running'] = True
    _compile_status['progress'] = '\u626b\u63cf\u6587\u7ae0\u76ee\u5f55'
    _compile_status['errors'] = []
    _compile_status['completed'] = 0

    try:
        wiki_service.ensure_wiki_dirs()

        if init or not incremental:
            _compile_status['progress'] = '\u521d\u59cb\u5316 Wiki...'
            _init_wiki()

        article_files = wiki_service.scan_article_files()
        if not article_files:
            _compile_status['progress'] = '\u6587\u7ae0\u76ee\u5f55\u4e0b\u6ca1\u6709 .md \u6587\u4ef6'
            _compile_status['running'] = False
            return

        existing_pages = {p.slug: p for p in WikiPage.query.all()}

        compiled_hashes = _get_compiled_hashes()

        if incremental:
            changed_files = [f for f in article_files if f['title'] not in compiled_hashes or compiled_hashes[f['title']] != f['hash']]
            _compile_status['progress'] = f'\u68c0\u6d4b\u5230 {len(changed_files)} \u4e2a\u6587\u4ef6\u9700\u8981\u66f4\u65b0\uff08\u5171 {len(article_files)} \u4e2a\uff09'
        else:
            changed_files = article_files
            _compile_status['progress'] = '\u6267\u884c\u5168\u91cf\u7f16\u8bd1'

        if not changed_files:
            _compile_status['progress'] = '\u6240\u6709\u6587\u4ef6\u5df2\u662f\u6700\u65b0\uff0c\u65e0\u9700\u7f16\u8bd1'
            _compile_status['running'] = False
            return

        adapter, model = _get_llm()
        _compile_status['total'] = len(changed_files)

        all_concepts = []
        batch_size = 5
        total_files = len(changed_files)
        processed_count = 0
        batch_idx = 0

        while processed_count < total_files:
            if batch_idx > 0 and batch_size < 10:
                avg_content_len = sum(len(f['content']) for f in changed_files[:processed_count]) / processed_count
                if avg_content_len < 2000:
                    batch_size = min(10, batch_size + 1)
                elif avg_content_len > 5000:
                    batch_size = max(3, batch_size - 1)

            batch_end = min(processed_count + batch_size, total_files)
            batch_files = changed_files[processed_count:batch_end]
            batch_idx += 1

            with _status_lock:
                _compile_status['progress'] = f'\u6279\u91cf\u63d0\u53d6\u6982\u5ff5 ({processed_count + 1}-{batch_end}/{total_files})\uff0c\u6279\u6b21\u5927\u5c0f: {len(batch_files)}'

            try:
                concepts = _batch_extract_concepts(adapter, model, batch_files)
                all_concepts.extend(concepts)
                with _status_lock:
                    _compile_status['completed'] += len(batch_files)
                processed_count = batch_end
            except RuntimeError:
                with _status_lock:
                    _compile_status['progress'] = f'\u6279\u91cf\u63d0\u53d6\u5931\u8d25\uff0c\u964d\u7ea7\u4e3a\u9010\u4e2a\u63d0\u53d6'

                for f in batch_files:
                    with _status_lock:
                        _compile_status['progress'] = f'\u63d0\u53d6\u6982\u5ff5 ({processed_count + 1}/{total_files}): {f["title"]}'
                    try:
                        concepts = _extract_concepts(adapter, model, f['title'], f['content'])
                        for concept in concepts:
                            concept['_source_title'] = f['title']
                            concept['_source_path'] = f['path']
                            concept['_source_hash'] = f['hash']
                        all_concepts.extend(concepts)
                    except RuntimeError as ee:
                        error_msg = f'{f["title"]}: {str(ee)}'
                        with _status_lock:
                            _compile_status['progress'] = f'\u7f16\u8bd1\u5931\u8d25: {error_msg}'
                            _compile_status['errors'].append(error_msg)
                            _compile_status['running'] = False
                        return
                    except Exception as ee:
                        with _status_lock:
                            _compile_status['errors'].append(f'{f["title"]}: {str(ee)}')

                    processed_count += 1
                    with _status_lock:
                        _compile_status['completed'] += 1

        if not all_concepts:
            _compile_status['progress'] = '\u6ca1\u6709\u9700\u8981\u66f4\u65b0\u7684\u6982\u5ff5'
            _compile_status['running'] = False
            return

        with _status_lock:
            _compile_status['progress'] = f'\u751f\u6210\u9875\u9762 (\u5171 {len(all_concepts)} \u4e2a\u6982\u5ff5)'

        merged = _merge_concepts(all_concepts)
        generated_slugs = []

        existing_concept_names = {p.title for p in WikiPage.query.with_entities(WikiPage.title).all()}
        all_concept_names = set(merged.keys()) | existing_concept_names
        known_concepts_str = ', '.join(sorted(all_concept_names))

        app_ref = current_app._get_current_object()
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
                    slug = _generate_page(adapter, model, concept_name, entries, existing_pages, known_concepts_str)
                    with _status_lock:
                        completed_count += 1
                        _compile_status['progress'] = f'\u751f\u6210\u9875\u9762 ({completed_count}/{total_concepts}): {concept_name}'
                    return slug
                except RuntimeError as e:
                    error_stop.set()
                    first_error[0] = (concept_name, str(e))
                    return None
                except Exception as e:
                    with _status_lock:
                        _compile_status['errors'].append(f'\u751f\u6210 {concept_name} \u5931\u8d25: {str(e)}')
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
            error_msg = f'\u751f\u6210 {concept_name} \u5931\u8d25: {err_msg}'
            with _status_lock:
                _compile_status['progress'] = f'\u7f16\u8bd1\u5931\u8d25: {error_msg}'
                _compile_status['errors'].append(error_msg)
                _compile_status['running'] = False
            _save_file_hashes(compiled_hashes, changed_files)
            if generated_slugs:
                wiki_service.generate_index()
            return

        wiki_service.generate_index()
        _save_file_hashes(compiled_hashes, changed_files)

        _compile_status['progress'] = '\u7f16\u8bd1\u5b8c\u6210'

    except Exception as e:
        import traceback
        _compile_status['progress'] = f'\u7f16\u8bd1\u5931\u8d25: {str(e)}'
        _compile_status['errors'].append(traceback.format_exc())
        db.session.rollback()
    finally:
        _compile_status['running'] = False


EXTRACT_PROMPT = """你是一个知识提取专家。请从以下内容中提取核心概念。

对于每个概念，返回一个 JSON 数组，每个元素包含：
- "name": 概念名称
- "summary": 一句话概述（50字以内）
- "key_points": 关键要点列表（3-5个）

请只返回 JSON 数组，不要其他内容。

源文件: {title}

{content}"""

BATCH_EXTRACT_PROMPT = """你是一个知识提取专家。请从以下多篇文章中提取核心概念。

每篇文章用 ====文件名==== 分隔。

对于每个概念，返回一个 JSON 数组，每个元素包含：
- "name": 概念名称
- "summary": 一句话概述（50字以内）
- "key_points": 关键要点列表（3-5个）
- "_source_title": 来源文章名称

请只返回 JSON 数组，不要其他内容。

{content}"""

GENERATE_PROMPT = """你是一个知识 Wiki 编写专家。请根据以下信息生成一个 Wiki 页面。

概念名称: {concept_name}
已知概念列表: {known_concepts}
相关信息:
{context}

要求:
1. 用 Markdown 格式
2. 使用 [[概念名]] 语法链接到相关概念，只能链接"已知概念列表"中存在的概念名，必须使用列表中的原始名称，不要修改或缩写
3. 内容结构清晰，包含概述、详细说明、相关概念
4. 语言简洁准确
5. 在末尾列出相关概念链接

请直接输出 Markdown 内容，不要包含标题的 # 行。"""


def _extract_concepts(adapter, model, title, content):
    prompt = EXTRACT_PROMPT.format(title=title, content=content[:8000])
    messages = [{'role': 'user', 'content': prompt}]
    response = adapter.chat(messages, model=model)

    if response.startswith('OpenAI API \u8c03\u7528\u5931\u8d25') or \
       response.startswith('Claude API \u8c03\u7528\u5931\u8d25') or \
       response.startswith('Gemini API \u8c03\u7528\u5931\u8d25') or \
       response.startswith('Ollama API \u8c03\u7528\u5931\u8d25') or \
       response.startswith('\u672a\u914d\u7f6e'):
        raise RuntimeError(f"LLM \u8c03\u7528\u5931\u8d25: {response}")

    try:
        json_match = re.search(r'\[.*\]', response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except json.JSONDecodeError:
        pass

    return [{'name': title, 'summary': content[:100], 'key_points': []}]


def _batch_extract_concepts(adapter, model, articles):
    batch_content = ""
    for article in articles:
        batch_content += f"===={article['title']}====\n"
        batch_content += article['content'][:4000] + "\n\n"

    prompt = BATCH_EXTRACT_PROMPT.format(content=batch_content)
    messages = [{'role': 'user', 'content': prompt}]

    try:
        response = adapter.chat(messages, model=model)

        if response.startswith('OpenAI API \u8c03\u7528\u5931\u8d25') or \
           response.startswith('Claude API \u8c03\u7528\u5931\u8d25') or \
           response.startswith('Gemini API \u8c03\u7528\u5931\u8d25') or \
           response.startswith('Ollama API \u8c03\u7528\u5931\u8d25') or \
           response.startswith('\u672a\u914d\u7f6e'):
            raise RuntimeError(f"LLM \u8c03\u7528\u5931\u8d25: {response}")

        json_match = re.search(r'\[.*\]', response, re.DOTALL)
        if json_match:
            concepts = json.loads(json_match.group())
            for concept in concepts:
                source_title = concept.get('_source_title', '')
                for article in articles:
                    if article['title'] == source_title:
                        concept['_source_path'] = article['path']
                        concept['_source_hash'] = article['hash']
                        break
            return concepts
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"\u6279\u91cf\u63d0\u53d6\u5931\u8d25: {str(e)}")

    return []


def _merge_concepts(concepts):
    merged = {}
    for c in concepts:
        name = c.get('name', '').strip()
        if not name:
            continue
        key = name.lower()
        if key not in merged:
            merged[key] = []
        merged[key].append(c)
    return merged


def _generate_page(adapter, model, concept_name, entries, existing_pages, known_concepts=''):
    context_parts = []
    source_titles = []
    source_hashes = set()
    for entry in entries:
        source_title = entry.get('_source_title', '')
        if source_title:
            source_titles.append(source_title)
        source_hash = entry.get('_source_hash', '')
        if source_hash:
            source_hashes.add(source_hash)
        points = entry.get('key_points', [])
        summary = entry.get('summary', '')
        context_parts.append(f"- {summary}")
        for p in points:
            context_parts.append(f"  - {p}")

    context = '\n'.join(context_parts)

    prompt = GENERATE_PROMPT.format(concept_name=concept_name, known_concepts=known_concepts, context=context)
    messages = [{'role': 'user', 'content': prompt}]
    body = adapter.chat(messages, model=model)

    if body.startswith('OpenAI API \u8c03\u7528\u5931\u8d25') or \
       body.startswith('Claude API \u8c03\u7528\u5931\u8d25') or \
       body.startswith('Gemini API \u8c03\u7528\u5931\u8d25') or \
       body.startswith('Ollama API \u8c03\u7528\u5931\u8d25') or \
       body.startswith('\u672a\u914d\u7f6e'):
        raise RuntimeError(f"LLM \u8c03\u7528\u5931\u8d25: {body}")

    wikilinks = re.findall(r'\[\[(.+?)\]\]', body)

    slug = concept_name.lower().replace(' ', '_').replace('/', '_')

    content_hash = wiki_service.compute_hash(body)

    wiki_service.save_concept_page(
        slug=slug,
        title=concept_name,
        body=body,
        summary=entries[0].get('summary', ''),
        sources=source_titles,
        kind='concept',
        confidence=0.8,
    )

    with _db_lock:
        if slug in existing_pages:
            page = existing_pages[slug]
            page.title = concept_name
            page.summary = entries[0].get('summary', '')
            page.body = body
            page.sources = json.dumps(source_titles, ensure_ascii=False)
            page.links = json.dumps(wikilinks, ensure_ascii=False)
            page.content_hash = content_hash
            page.updated_at = datetime.utcnow()
        else:
            page = WikiPage(
                title=concept_name,
                slug=slug,
                summary=entries[0].get('summary', ''),
                body=body,
                sources=json.dumps(source_titles, ensure_ascii=False),
                links=json.dumps(wikilinks, ensure_ascii=False),
                kind='concept',
                confidence=0.8,
                content_hash=content_hash,
            )
            db.session.add(page)
            existing_pages[slug] = page

        db.session.commit()

    return slug


def query_wiki(question, save=False):
    adapter, model = _get_llm()

    pages = WikiPage.query.order_by(WikiPage.updated_at.desc()).limit(10).all()
    context_parts = []
    for p in pages:
        context_parts.append(f"## {p.title}\n{p.body[:500]}")

    context = '\n\n'.join(context_parts)

    prompt = f"""\u4f60\u662f\u4e00\u4e2a\u77e5\u8bc6\u52a9\u624b\u3002\u8bf7\u6839\u636e\u4ee5\u4e0b Wiki \u5185\u5bb9\u56de\u7b54\u95ee\u9898\u3002

Wiki \u5185\u5bb9:
{context}

\u95ee\u9898: {question}

\u8bf7\u7528\u4e2d\u6587\u56de\u7b54\uff0c\u5982\u679c Wiki \u4e2d\u6ca1\u6709\u76f8\u5173\u4fe1\u606f\uff0c\u8bf7\u8bf4\u660e\u3002"""

    messages = [{'role': 'user', 'content': prompt}]
    answer = adapter.chat(messages, model=model)

    if save:
        import time
        slug = f"q_{int(time.time())}"
        wiki_service.save_query_page(slug, question, answer)

    return answer
