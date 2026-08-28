"""slug 安全化工具 — 统一记忆 / Wiki 概念页的文件名规范化。"""


def safe_slug(s):
    r"""把 slug 里的 /、\、空格替换为 _，避免路径分隔符破坏文件名。"""
    return s.replace('/', '_').replace('\\', '_').replace(' ', '_')
