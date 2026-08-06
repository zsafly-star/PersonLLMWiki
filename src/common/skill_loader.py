"""Skills 加载器。

扫描 bin/skills/*/SKILL.md，解析 front matter（name + description），
将可用技能注入 Agent 系统提示词。

每个 Skill = 一个文件夹 + SKILL.md（工作流指令）+ 可选 scripts/。

目录结构：
  bin/skills/
  ├── bom-picking/
  │   ├── SKILL.md          ← YAML front matter + Markdown 工作流
  │   └── scripts/
  │       └── check_bom.py
  └── <future-skill>/
      ├── SKILL.md
      └── scripts/

Agent 工作流程：
  1. 启动时加载所有 skill 的 name + description → 注入系统提示词
  2. LLM 匹配用户意图 → 返回 skill_name
  3. 读取完整 SKILL.md 内容 → 注入当前对话
  4. LLM 按 SKILL.md 工作流编排 MCP 工具执行
"""
import os
import re
import sys

# bin/skills/ 目录绝对路径
# 打包模式：bin/ 在 exe 同级，sys._MEIPASS 指向 _internal/，取其上级
# 开发模式：bin/ 在 src/ 下，__file__ 在 src/common/，向上两级
if getattr(sys, 'frozen', False):
    _SRC_ROOT = os.path.dirname(sys._MEIPASS)
else:
    _SRC_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SKILLS_DIR = os.path.join(_SRC_ROOT, 'bin', 'skills')


def _parse_front_matter(content):
    """解析 SKILL.md 的 YAML front matter。

    返回 (metadata_dict, body_str)。
    """
    # 匹配 --- 包裹的 front matter
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n?(.*)', content, re.DOTALL)
    if not match:
        return {}, content

    yaml_text = match.group(1)
    body = match.group(2)

    # 简单 YAML 解析（不依赖 PyYAML，只取顶层 key: value）
    meta = {}
    for line in yaml_text.split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if ':' in line:
            key, _, val = line.partition(':')
            meta[key.strip()] = val.strip().strip('"').strip("'")

    return meta, body


def load_skill(name):
    """加载单个 skill 的完整内容。

    返回 dict: {name, description, path, content} 或 None。
    """
    skill_dir = os.path.join(_SKILLS_DIR, name)
    skill_file = os.path.join(skill_dir, 'SKILL.md')
    if not os.path.isfile(skill_file):
        return None

    with open(skill_file, 'r', encoding='utf-8') as f:
        content = f.read()

    meta, body = _parse_front_matter(content)
    return {
        'name': meta.get('name', name),
        'description': meta.get('description', ''),
        'path': skill_dir,
        'content': content,
        'body': body,
    }


def list_skills():
    """扫描 bin/skills/ 下所有 skill，返回摘要列表。

    只返回 name + description（不含完整内容），用于注入系统提示词。
    """
    skills = []
    if not os.path.isdir(_SKILLS_DIR):
        return skills

    for entry in sorted(os.listdir(_SKILLS_DIR)):
        skill_dir = os.path.join(_SKILLS_DIR, entry)
        skill_file = os.path.join(skill_dir, 'SKILL.md')
        if not os.path.isfile(skill_file):
            continue

        try:
            with open(skill_file, 'r', encoding='utf-8') as f:
                content = f.read()
            meta, _ = _parse_front_matter(content)
            skills.append({
                'name': meta.get('name', entry),
                'description': meta.get('description', ''),
                'path': skill_dir,
            })
        except Exception:
            pass

    return skills


def get_skills_prompt():
    """生成注入 Agent 系统提示词的技能列表文本。

    如果没有 skill，返回空字符串。
    """
    skills = list_skills()
    if not skills:
        return ''

    lines = ['\n## 可用技能（Skills）', '']
    for s in skills:
        lines.append(f'- **{s["name"]}**: {s["description"]}')
    lines.append('')
    lines.append('当用户意图匹配某个技能时，系统会自动加载该技能的详细工作流指令。')
    return '\n'.join(lines)


def match_skill(user_message):
    """简单关键词匹配：返回用户消息可能匹配的 skill name。

    基于 skill description 中的关键词与用户消息做模糊匹配。
    匹配到返回 skill name，否则返回 None。
    """
    skills = list_skills()
    if not skills:
        return None

    msg_lower = user_message.lower()
    best_match = None
    best_score = 0

    for s in skills:
        desc = s['description'].lower()
        name = s['name'].lower()
        # 从 description 提取关键词
        keywords = set()
        for word in re.split(r'[\s,;/.|()]+', desc):
            word = word.strip()
            if len(word) > 2 and word not in ('the', 'for', 'and', 'when', 'with', 'from'):
                keywords.add(word)
        keywords.add(name)

        score = sum(1 for kw in keywords if kw in msg_lower)
        if score > best_score:
            best_score = score
            best_match = s['name']

    return best_match if best_score > 0 else None


def get_skill_dir(name):
    """返回 skill 目录的绝对路径。"""
    return os.path.join(_SKILLS_DIR, name)
