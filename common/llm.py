import os
import requests
from abc import ABC, abstractmethod


class BaseLLMAdapter(ABC):
    @abstractmethod
    def chat(self, messages, model=None):
        pass

    @abstractmethod
    def get_models(self):
        pass


class OpenAIAdapter(BaseLLMAdapter):
    def __init__(self, api_key=None, base_url=None):
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        self.base_url = base_url or os.getenv('OPENAI_BASE_URL')

    def _get_client(self):
        import openai
        kwargs = {'api_key': self.api_key}
        if self.base_url:
            kwargs['base_url'] = self.base_url
        return openai.OpenAI(**kwargs)

    def chat(self, messages, model='gpt-3.5-turbo', tools=None):
        if not self.api_key:
            return "未配置 OPENAI_API_KEY"

        client = self._get_client()

        try:
            create_kwargs = {'model': model, 'messages': messages}
            if tools:
                create_kwargs['tools'] = tools
            response = client.chat.completions.create(**create_kwargs)
            message = response.choices[0].message
            # 有 tools 时返回完整 message 对象（Agent 需要 tool_calls），
            # 无 tools 时返回 content 字符串（可直接序列化/拼接）
            if tools:
                return message
            return message.content or ''
        except Exception as e:
            from openai import RateLimitError, AuthenticationError, APIConnectionError, APIError
            if isinstance(e, RateLimitError):
                return f"OpenAI API 调用失败: 达到使用上限\n请稍后重试或联系管理员。"
            if isinstance(e, AuthenticationError):
                return f"OpenAI API 调用失败: 身份验证错误\n请检查 API Key 配置。"
            if isinstance(e, APIConnectionError):
                return f"OpenAI API 调用失败: 网络连接错误"
            return f"OpenAI API 调用失败: {str(e)}"

    def get_models(self):
        return ['gpt-4', 'gpt-3.5-turbo']

    def stream_chat(self, messages, model='gpt-3.5-turbo', tools=None):
        if not self.api_key:
            yield {'type': 'content', 'content': '未配置 OPENAI_API_KEY'}
            return

        client = self._get_client()

        try:
            create_kwargs = {'model': model, 'messages': messages, 'stream': True}
            if tools:
                create_kwargs['tools'] = tools
            stream = client.chat.completions.create(**create_kwargs)
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                    yield {'type': 'thinking', 'content': delta.reasoning_content}
                if delta.content:
                    yield {'type': 'content', 'content': delta.content}
        except Exception as e:
            yield {'type': 'content', 'content': f'\n\nAPI 调用失败: {str(e)}'}


class ClaudeAdapter(BaseLLMAdapter):
    def __init__(self, api_key=None, base_url=None):
        self.api_key = api_key or os.getenv('ANTHROPIC_API_KEY')
        self.base_url = base_url or os.getenv('ANTHROPIC_BASE_URL')

    def chat(self, messages, model='claude-3-sonnet'):
        if not self.api_key:
            return "未配置 ANTHROPIC_API_KEY"

        headers = {
            'Content-Type': 'application/json',
            'x-api-key': self.api_key,
            'anthropic-version': '2023-06-01'
        }

        data = {
            'model': model,
            'max_tokens': 4096,
            'messages': messages
        }

        base = self.base_url or 'https://api.anthropic.com'
        url = base.rstrip('/') + '/v1/messages'

        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            return response.json().get('content', [{}])[0].get('text', '')
        except Exception as e:
            return f"Claude API 调用失败: {str(e)}"

    def get_models(self):
        return ['claude-3-sonnet', 'claude-3-haiku']


class GeminiAdapter(BaseLLMAdapter):
    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv('GEMINI_API_KEY')

    def chat(self, messages, model='gemini-pro'):
        if not self.api_key:
            return "未配置 GEMINI_API_KEY"

        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)

            gm = genai.GenerativeModel(model)
            response = gm.generate_content(
                '\n'.join([f"{m['role']}: {m['content']}" for m in messages])
            )
            return response.text
        except Exception as e:
            return f"Gemini API 调用失败: {str(e)}"

    def get_models(self):
        return ['gemini-pro']


class OllamaAdapter(BaseLLMAdapter):
    def __init__(self, base_url=None):
        self.base_url = base_url or os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')

    def chat(self, messages, model='llama2'):
        try:
            url = self.base_url.rstrip('/') + '/api/chat'
            response = requests.post(url, json={
                'model': model,
                'messages': messages,
                'stream': False
            })
            response.raise_for_status()
            return response.json().get('message', {}).get('content', '')
        except Exception as e:
            return f"Ollama API 调用失败: {str(e)}"

    def get_models(self):
        try:
            url = self.base_url.rstrip('/') + '/api/tags'
            resp = requests.get(url)
            resp.raise_for_status()
            models = resp.json().get('models', [])
            return [m['name'] for m in models]
        except Exception:
            return ['llama2']

    def stream_chat(self, messages, model='llama2'):
        try:
            url = self.base_url.rstrip('/') + '/api/chat'
            response = requests.post(url, json={
                'model': model,
                'messages': messages,
                'stream': True
            }, stream=True)
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    import json
                    data = json.loads(line)
                    content = data.get('message', {}).get('content', '')
                    if content:
                        yield {'type': 'content', 'content': content}
                    if data.get('done'):
                        break
        except Exception as e:
            yield {'type': 'content', 'content': f'\n\nOllama API 调用失败: {str(e)}'}


class LLMService:
    ADAPTERS = {
        'openai': OpenAIAdapter,
        'claude': ClaudeAdapter,
        'gemini': GeminiAdapter,
        'ollama': OllamaAdapter,
    }

    @classmethod
    def get_adapter(cls, provider, **kwargs):
        if provider not in cls.ADAPTERS:
            raise ValueError(f"不支持的模型提供商: {provider}")
        return cls.ADAPTERS[provider](**kwargs)

    @classmethod
    def get_all_models(cls):
        models = {}
        for provider, adapter_cls in cls.ADAPTERS.items():
            adapter = adapter_cls()
            models[provider] = adapter.get_models()
        return models

    @classmethod
    def chat(cls, provider, model, messages, **kwargs):
        adapter = cls.get_adapter(provider, **kwargs)
        return adapter.chat(messages, model)

    @classmethod
    def stream_chat(cls, provider, model, messages, **kwargs):
        adapter = cls.get_adapter(provider, **kwargs)
        if hasattr(adapter, 'stream_chat'):
            yield from adapter.stream_chat(messages, model)
        else:
            yield adapter.chat(messages, model)

    @classmethod
    def get_provider_list(cls):
        return list(cls.ADAPTERS.keys())
