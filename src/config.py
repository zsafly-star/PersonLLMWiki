import os
from dotenv import load_dotenv

# 查找 .env：依次检查 app 同级目录（embedded 部署）、app 上级、当前目录
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
_DEFAULT_RESOURCE_PATH = os.path.join(_PROJECT_ROOT, 'resource')

# 尝试多个位置的 .env
for _env_candidate in [
    os.path.join(_PROJECT_ROOT, '.env'),          # embedded: app/../.env
    os.path.join(_THIS_DIR, '.env'),               # 开发模式: src/.env
    os.path.join(os.getcwd(), '.env'),             # 当前目录
]:
    if os.path.isfile(_env_candidate):
        load_dotenv(_env_candidate)
        break


class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = 'static/uploads'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024

    # 实例模式：single（默认，原始单实例）/ personal（个人版，可同步公共库）/ public（公共版）
    INSTANCE_MODE = os.getenv('INSTANCE_MODE', 'single')

    RESOURCE_BASE_PATH = os.getenv('RESOURCE_BASE_PATH', _DEFAULT_RESOURCE_PATH)
    ARTICLE_PATH = os.path.join(RESOURCE_BASE_PATH, 'article')
    IMAGE_PATH = os.path.join(RESOURCE_BASE_PATH, 'img')
    ATTACHMENT_PATH = os.path.join(RESOURCE_BASE_PATH, 'attachments')
    WIKI_PATH = os.path.join(RESOURCE_BASE_PATH, 'wiki')
    INSTANCE_PATH = os.path.join(RESOURCE_BASE_PATH, 'instance')

    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(INSTANCE_PATH, 'sseditor.db')

    # 公共库配置（仅 personal 模式生效）
    COMMON_GIT_REPO = os.getenv('COMMON_GIT_REPO', '')          # 公共库 Git 远程地址
    COMMON_RESOURCE_PATH = os.getenv('COMMON_RESOURCE_PATH', '')  # 公共库本地目录
    COMMON_ARTICLE_PATH = os.path.join(COMMON_RESOURCE_PATH, 'article') if COMMON_RESOURCE_PATH else ''
    COMMON_WIKI_PATH = os.path.join(COMMON_RESOURCE_PATH, 'wiki') if COMMON_RESOURCE_PATH else ''

    # Phase 3: 权限与作者
    AUTHOR_NAME = os.getenv('AUTHOR_NAME', '')                   # 提交者标识
    MCP_ADMIN_TOKEN = os.getenv('MCP_ADMIN_TOKEN', '')            # 管理员 Token（全权限）
    MCP_SUBMITTER_TOKEN = os.getenv('MCP_SUBMITTER_TOKEN', '')    # 提交者 Token（仅 submit_to_public）
    # 向后兼容：ZSSNOTE_MCP_TOKEN 等价于 ADMIN_TOKEN
    if not MCP_ADMIN_TOKEN:
        MCP_ADMIN_TOKEN = os.getenv('ZSSNOTE_MCP_TOKEN', '')


class LLMConfig:
    SUPPORTED_MODELS = {
        'openai': ['gpt-4', 'gpt-3.5-turbo'],
        'claude': ['claude-3-sonnet', 'claude-3-haiku'],
        'gemini': ['gemini-pro'],
        'local': ['llama2-7b', 'qwen-7b']
    }
