import os
import sys as _sys
from dotenv import load_dotenv

# 用户数据目录（固定，不可自定义）
_USER_HOME = os.path.expanduser('~')
_USER_DATA_DIR = os.path.join(_USER_HOME, '.personllmwiki')

# .env 只从用户数据目录读取
_env_path = os.path.join(_USER_DATA_DIR, '.env')
if os.path.isfile(_env_path):
    load_dotenv(_env_path)

# 种子数据目录（首次播种用，安装时自带）
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if getattr(_sys, 'frozen', False):
    _SEED_DIR = os.path.join(os.path.dirname(_sys._MEIPASS), 'seed')
else:
    _SEED_DIR = os.path.join(_PROJECT_ROOT, 'seed')


class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = 'static/uploads'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024

    # 实例模式：single（默认，原始单实例）/ personal（个人版，可同步公共库）/ public（公共版）
    INSTANCE_MODE = os.getenv('INSTANCE_MODE', 'single')

    SEED_DIR = _SEED_DIR

    # ===== 路径体系 =====
    # USER_DATA_DIR       ~/.personllmwiki/       固定，不可自定义
    # INSTANCE_PATH       USER_DATA_DIR/instance/  数据库、配置
    # MCP_DIR             USER_DATA_DIR/mcp/       MCP 二进制
    # SKILLS_DIR          USER_DATA_DIR/skills/    技能定义
    # RESOURCE_BASE_PATH  从 .env 读取，默认 USER_DATA_DIR/resource/  用户可自定义

    USER_DATA_DIR = _USER_DATA_DIR
    INSTANCE_PATH = os.path.join(USER_DATA_DIR, 'instance')
    MCP_DIR = os.path.join(USER_DATA_DIR, 'mcp')
    SKILLS_DIR = os.path.join(USER_DATA_DIR, 'skills')

    RESOURCE_BASE_PATH = os.getenv('RESOURCE_BASE_PATH',
                                   os.path.join(USER_DATA_DIR, 'resource'))
    ARTICLE_PATH = os.path.join(RESOURCE_BASE_PATH, 'article')
    IMAGE_PATH = os.path.join(RESOURCE_BASE_PATH, 'img')
    ATTACHMENT_PATH = os.path.join(RESOURCE_BASE_PATH, 'attachments')
    WIKI_PATH = os.path.join(RESOURCE_BASE_PATH, 'wiki')

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
