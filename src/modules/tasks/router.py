"""L1 Router：场景意图分发（轻量 LLM 分类）。

输入用户意图 + 可用场景清单，返回匹配场景 name 或 None（无匹配退回普通对话）。
"""
import json
import re

from common.llm_config import LLMConfigService
from common.llm import LLMService

from .models import Scenario


def load_active_scenarios():
    """返回当前启用的场景对象列表。"""
    return Scenario.query.filter_by(is_active=True).order_by(Scenario.id).all()


def _extract_json(text):
    """从 LLM 输出中提取第一个 JSON 对象。"""
    if not text:
        return None
    text = text.strip()
    # 去掉 markdown 代码围栏
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 兜底：抓取第一个 { ... } 块
        m = re.search(r'\{.*\}', text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
    return None


def route_intent(user_text):
    """返回匹配的场景 name，无匹配返回 None。"""
    scenarios = load_active_scenarios()
    if not scenarios or not user_text:
        return None

    config = LLMConfigService.get_active()
    if not config:
        return None

    options = '\n'.join(
        f"- {s.name}（{s.label}）：{s.description or '无描述'}"
        for s in scenarios
    )
    messages = [
        {'role': 'system', 'content': (
            '你是场景路由分类器。根据用户意图，判断是否匹配下列场景之一。\n'
            '只输出 JSON，格式：{"scene": "<name>"} 或 {"scene": null}。\n'
            '可选场景：\n' + options + '\n'
            '若用户意图不属于任何场景，输出 {"scene": null}。'
        )},
        {'role': 'user', 'content': user_text},
    ]

    try:
        provider = config.provider
        model = config.model or ''
        kwargs = {}
        if config.api_key:
            kwargs['api_key'] = config.api_key
        if config.base_url:
            kwargs['base_url'] = config.base_url

        resp = LLMService.chat(provider, model, messages, **kwargs)
        data = _extract_json(resp if isinstance(resp, str) else json.dumps(resp))
        if not isinstance(data, dict):
            return None

        scene = data.get('scene')
        valid = {s.name for s in scenarios}
        return scene if scene in valid else None
    except Exception:
        return None
