import json
import re
import threading
from datetime import datetime

from flask import current_app
from extensions import db
from . import prompts
from .extractor import _is_llm_error
from ..models import WikiPage
from .. import wiki_service

_db_lock = threading.Lock()


def generate_page(adapter, model, concept_name, entries, existing_pages, known_concepts=''):
    context_parts = []
    source_titles = []
    for entry in entries:
        source_title = entry.get('_source_title', '')
        if source_title:
            source_titles.append(source_title)
        points = entry.get('key_points', [])
        summary = entry.get('summary', '')
        context_parts.append(f"- {summary}")
        for p in points:
            context_parts.append(f"  - {p}")

    context = '\n'.join(context_parts)

    prompt = prompts.GENERATE_PROMPT.format(
        concept_name=concept_name,
        known_concepts=known_concepts,
        context=context,
    )
    messages = [{'role': 'user', 'content': prompt}]
    body = adapter.chat(messages, model=model)

    if _is_llm_error(body):
        raise RuntimeError(f"LLM 调用失败: {body}")

    wikilinks = re.findall(r'\[\[(.+?)\]\]', body)
    provenance_refs = re.findall(r'\^\[([^\]]+)\]', body)

    slug = concept_name.lower().replace(' ', '_').replace('/', '_')
    content_hash = wiki_service.compute_hash(body)

    wiki_service.save_concept_page(
        slug=slug,
        title=concept_name,
        body=body,
        summary=entries[0].get('summary', ''),
        sources=source_titles,
        kind='concept',
        confidence=entries[0].get('confidence', 0.8),
    )

    with _db_lock:
        if slug in existing_pages:
            page = existing_pages[slug]
            page.title = concept_name
            page.summary = entries[0].get('summary', '')
            page.body = body
            page.sources = json.dumps(source_titles, ensure_ascii=False)
            page.links = json.dumps(wikilinks, ensure_ascii=False)
            page.provenance_refs = json.dumps(provenance_refs, ensure_ascii=False)
            page.content_hash = content_hash
            page.review_status = 'pending'
            page.updated_at = datetime.utcnow()
        else:
            page = WikiPage(
                title=concept_name,
                slug=slug,
                summary=entries[0].get('summary', ''),
                body=body,
                sources=json.dumps(source_titles, ensure_ascii=False),
                links=json.dumps(wikilinks, ensure_ascii=False),
                provenance_refs=json.dumps(provenance_refs, ensure_ascii=False),
                kind='concept',
                confidence=entries[0].get('confidence', 0.8),
                content_hash=content_hash,
                review_status='pending',
            )
            db.session.add(page)
            existing_pages[slug] = page

        db.session.commit()

    return slug


def generate_candidate_page(adapter, model, concept_name, entries, known_concepts=''):
    context_parts = []
    source_titles = []
    for entry in entries:
        source_title = entry.get('_source_title', '')
        if source_title:
            source_titles.append(source_title)
        points = entry.get('key_points', [])
        summary = entry.get('summary', '')
        context_parts.append(f"- {summary}")
        for p in points:
            context_parts.append(f"  - {p}")

    context = '\n'.join(context_parts)

    prompt = prompts.GENERATE_PROMPT.format(
        concept_name=concept_name,
        known_concepts=known_concepts,
        context=context,
    )
    messages = [{'role': 'user', 'content': prompt}]
    body = adapter.chat(messages, model=model)

    if _is_llm_error(body):
        raise RuntimeError(f"LLM 调用失败: {body}")

    wikilinks = re.findall(r'\[\[(.+?)\]\]', body)
    provenance_refs = re.findall(r'\^\[([^\]]+)\]', body)

    return {
        'title': concept_name,
        'slug': concept_name.lower().replace(' ', '_').replace('/', '_'),
        'summary': entries[0].get('summary', ''),
        'body': body,
        'sources': source_titles,
        'links': wikilinks,
        'provenance_refs': provenance_refs,
        'kind': 'concept',
        'confidence': entries[0].get('confidence', 0.8),
        'status': 'pending',
    }
