import json
import re
import threading

from common.llm import LLMService
from common.llm_config import LLMConfigService
from . import prompts

_db_lock = threading.Lock()


def get_llm():
    config = LLMConfigService.get_active()
    if not config:
        raise RuntimeError('未配置 LLM')
    adapter = LLMService.get_adapter(config.provider, api_key=config.api_key, base_url=config.base_url)
    model = config.model or 'gpt-4o'
    return adapter, model


def _is_llm_error(response):
    error_prefixes = (
        'OpenAI API 调用失败',
        'Claude API 调用失败',
        'Gemini API 调用失败',
        'Ollama API 调用失败',
        '未配置',
    )
    return any(response.startswith(p) for p in error_prefixes)


def extract_concepts(adapter, model, title, content):
    prompt = prompts.EXTRACT_PROMPT.format(title=title, content=content[:8000])
    messages = [{'role': 'user', 'content': prompt}]
    response = adapter.chat(messages, model=model)

    if _is_llm_error(response):
        raise RuntimeError(f"LLM 调用失败: {response}")

    try:
        json_match = re.search(r'\[.*\]', response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except json.JSONDecodeError:
        pass

    return [{'name': title, 'summary': content[:100], 'key_points': [], 'confidence': 0.5, 'tags': []}]


def batch_extract_concepts(adapter, model, articles):
    batch_content = ""
    for article in articles:
        batch_content += f"===={article['title']}====\n"
        batch_content += article['content'][:4000] + "\n\n"

    prompt = prompts.BATCH_EXTRACT_PROMPT.format(content=batch_content)
    messages = [{'role': 'user', 'content': prompt}]

    try:
        response = adapter.chat(messages, model=model)

        if _is_llm_error(response):
            raise RuntimeError(f"LLM 调用失败: {response}")

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
        raise RuntimeError(f"批量提取失败: {str(e)}")

    return []


def merge_concepts(concepts):
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
