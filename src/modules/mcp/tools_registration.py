"""MCP 工具注册入口。

在模块导入时把所有工具 handler 注册到 TOOL_REGISTRY。
app.py 只要 from modules.mcp import mcp_bp 即可自动注册全部工具。
"""
from .registry import Tool, register_tool
from .tools_read import (
    handle_list_folders,
    handle_read_note,
    handle_list_wiki_pages,
    handle_read_wiki_page,
    handle_get_compile_status,
    handle_list_candidates,
    handle_get_graph,
)
from .tools_search import handle_search_kb
from .tools_write import (
    handle_write_note,
    handle_compile_wiki,
    handle_approve_candidate,
    handle_reject_candidate,
    handle_create_folder,
    handle_submit_to_public,
    handle_create_todo,
    handle_save_text_file,
)
from .tools_workspace import (
    handle_list_workspace,
    handle_read_workspace_file,
    handle_write_workspace_file,
)
from .tools_memory import (
    handle_search_memory,
    handle_list_memories,
    handle_remember,
    handle_forget_memory,
)
from .tools_skill import (
    handle_suggest_skill,
)


def _register_all():
    """注册所有 MCP 工具。重复导入幂等。"""
    tools = [
        # ---------- Tier 1: 只读 ----------
        Tool(
            name='list_folders',
            description='列出 PersonLLMWiki 文章知识库的顶层目录结构。无副作用，无成本。返回每个文件夹的名称、路径、图标和笔记数量。',
            input_schema={
                'type': 'object',
                'properties': {},
                'additionalProperties': False,
            },
            handler=handle_list_folders,
            cost='none',
        ),
        Tool(
            name='read_note',
            description='按路径读取一篇文章。默认返回标题+摘要+元数据；full=true 返回完整 Markdown。无成本。',
            input_schema={
                'type': 'object',
                'properties': {
                    'path': {
                        'type': 'string',
                        'description': '相对于知识库根目录的路径，例如 "工作/会议.md"',
                    },
                    'full': {
                        'type': 'boolean',
                        'default': False,
                        'description': 'true 返回完整 Markdown 正文',
                    },
                },
                'required': ['path'],
                'additionalProperties': False,
            },
            handler=handle_read_note,
            cost='none',
        ),
        Tool(
            name='list_wiki_pages',
            description='列出已审批的 Wiki 概念页面。无成本。返回 slug、title、source_count。',
            input_schema={
                'type': 'object',
                'properties': {
                    'limit': {
                        'type': 'integer', 'default': 50, 'minimum': 1, 'maximum': 200,
                    },
                    'offset': {
                        'type': 'integer', 'default': 0, 'minimum': 0,
                    },
                },
                'additionalProperties': False,
            },
            handler=handle_list_wiki_pages,
            cost='none',
        ),
        Tool(
            name='read_wiki_page',
            description='读取单个 Wiki 概念页面正文（含来源溯源）。无成本。',
            input_schema={
                'type': 'object',
                'properties': {
                    'slug': {
                        'type': 'string',
                        'description': '概念页面的 slug（小写、下划线分隔）',
                    },
                },
                'required': ['slug'],
                'additionalProperties': False,
            },
            handler=handle_read_wiki_page,
            cost='none',
        ),
        Tool(
            name='get_compile_status',
            description='查询当前 Wiki 编译进度。无成本。用于轮询 compile_wiki 的结果，替代 SSE 推送。',
            input_schema={
                'type': 'object',
                'properties': {},
                'additionalProperties': False,
            },
            handler=handle_get_compile_status,
            cost='none',
        ),
        Tool(
            name='list_candidates',
            description='列出待审批的 Wiki 候选页面。无成本。',
            input_schema={
                'type': 'object',
                'properties': {
                    'limit': {
                        'type': 'integer', 'default': 20, 'minimum': 1, 'maximum': 100,
                    },
                },
                'additionalProperties': False,
            },
            handler=handle_list_candidates,
            cost='none',
        ),
        Tool(
            name='get_graph',
            description='获取知识星链图谱数据。无 seed 返回全图（硬上限 80 节点）；有 seed 返回该概念的局部邻居。无成本。',
            input_schema={
                'type': 'object',
                'properties': {
                    'seed': {
                        'type': 'string',
                        'description': '种子概念名或 slug，返回其邻居子图',
                    },
                    'depth': {
                        'type': 'integer', 'default': 1, 'minimum': 1, 'maximum': 2,
                        'description': 'BFS 深度',
                    },
                },
                'additionalProperties': False,
            },
            handler=handle_get_graph,
            cost='none',
        ),

        # ---------- Tier 2: 检索 ----------
        Tool(
            name='search_kb',
            description='语义检索知识库。消耗 OpenAI Embedding 配额。返回 Top-K 相关片段及来源路径，向量检索(0.7) + BM25(0.3) 混合排序。',
            input_schema={
                'type': 'object',
                'properties': {
                    'query': {'type': 'string', 'description': '自然语言查询'},
                    'top_k': {
                        'type': 'integer', 'default': 5, 'minimum': 1, 'maximum': 10,
                    },
                    'delivery': {
                        'type': 'string', 'enum': ['flat', 'layered'], 'default': 'flat',
                        'description': 'flat=返回片段列表（默认），layered=按摘要/片段/原文三层组装',
                    },
                    'budget_tokens': {
                        'type': 'integer',
                        'description': 'layered 模式的 token 预算（可选，默认 1500）',
                    },
                },
                'required': ['query'],
                'additionalProperties': False,
            },
            handler=handle_search_kb,
            cost='openai-embedding',
        ),

        # ---------- Tier 3: 写入 ----------
        Tool(
            name='write_note',
            description=(
                '创建或覆盖一篇文章（Markdown）。直接写入文件系统，即时生效。'
                '路径必须在 article 根目录内，扩展名必须为 .md。'
                '【图片支持】如果内容包含图片，请使用 ![alt](data:image/xxx;base64,...) '
                '格式内嵌到 content 中，系统会自动提取并保存到知识库图片目录，'
                'Markdown 中的引用会自动替换为正确的相对路径。'
                '支持 PNG/JPEG/GIF/BMP/WebP/SVG 格式。'
            ),
            input_schema={
                'type': 'object',
                'properties': {
                    'path': {
                        'type': 'string',
                        'description': '相对于知识库根目录的路径，例如 "工作/会议.md"',
                    },
                    'content': {
                        'type': 'string',
                        'description': (
                            'Markdown 正文内容。'
                            '如果包含图片，请使用 ![alt](data:image/xxx;base64,...) '
                            '格式内嵌（支持 PNG/JPEG/GIF/BMP/WebP/SVG），'
                            '系统会自动提取并保存图片。'
                        ),
                    },
                    'create_folders': {
                        'type': 'boolean', 'default': True,
                        'description': 'true 时自动创建不存在的父目录',
                    },
                },
                'required': ['path', 'content'],
                'additionalProperties': False,
            },
            handler=handle_write_note,
            cost='none',
        ),
        Tool(
            name='save_text_file',
            description=(
                '将任意文本/Markdown 内容写入指定文件。支持覆盖和追加两种模式。'
                '默认路径相对于文章根目录（ARTICLE_PATH），与 write_note 同根，'
                '因此 mode="append" 可直接向已有知识库文章追加内容。'
                'root="resource" 时路径相对于资源根目录（RESOURCE_BASE_PATH）。'
                '【超长内容】若单次写入受限，请分多次调用：首次用 '
                'mode="overwrite" 创建文件，后续用 mode="append" 追加。'
            ),
            input_schema={
                'type': 'object',
                'properties': {
                    'path': {
                        'type': 'string',
                        'description': '相对路径。默认相对于文章根目录（如 "OpenHarmony/笔记.md"），root="resource" 时相对于资源根目录（如 "data/export.json"）',
                    },
                    'content': {
                        'type': 'string',
                        'description': (
                            '要写入的文本内容。'
                            '若内容过长导致单次传输失败，请分块并用 mode="append" 追加。'
                        ),
                    },
                    'mode': {
                        'type': 'string',
                        'enum': ['overwrite', 'append'],
                        'default': 'overwrite',
                        'description': 'overwrite 覆盖写入（原子替换），append 追加到文件末尾',
                    },
                    'root': {
                        'type': 'string',
                        'enum': ['article', 'resource'],
                        'default': 'article',
                        'description': '路径锚定根目录。article=文章目录（默认），resource=资源根目录（用于 JSON/CSV 等数据文件）',
                    },
                    'create_folders': {
                        'type': 'boolean', 'default': True,
                        'description': 'true 时自动创建不存在的父目录',
                    },
                },
                'required': ['path', 'content'],
                'additionalProperties': False,
            },
            handler=handle_save_text_file,
            cost='none',
        ),
        Tool(
            name='compile_wiki',
            description='触发 Wiki 知识编译（概念提取→页面生成）。消耗 OpenAI LLM 配额。编译产出进入待审批状态，不会自动入库。用 get_compile_status 轮询进度。',
            input_schema={
                'type': 'object',
                'properties': {
                    'incremental': {
                        'type': 'boolean', 'default': True,
                        'description': 'true 只编译变更文件，false 全量重编',
                    },
                    'init': {
                        'type': 'boolean', 'default': False,
                        'description': 'true 清空已有 Wiki 重新开始',
                    },
                },
                'additionalProperties': False,
            },
            handler=handle_compile_wiki,
            cost='openai-llm',
        ),
        Tool(
            name='approve_candidate',
            description='通过一个候选 Wiki 页面，使其正式入库并加入索引/图谱。安全约束：应仅在用户明确要求时调用，LLM 不应自动批量审批。',
            input_schema={
                'type': 'object',
                'properties': {
                    'id': {'type': 'integer', 'description': '候选页面 ID'},
                },
                'required': ['id'],
                'additionalProperties': False,
            },
            handler=handle_approve_candidate,
            cost='none',
        ),
        Tool(
            name='reject_candidate',
            description='拒绝并删除一个候选页面。只删未入库的候选（pending），不影响已审批页面。',
            input_schema={
                'type': 'object',
                'properties': {
                    'id': {'type': 'integer', 'description': '候选页面 ID'},
                },
                'required': ['id'],
                'additionalProperties': False,
            },
            handler=handle_reject_candidate,
            cost='none',
        ),
        Tool(
            name='create_folder',
            description='在文章知识库创建文件夹，可设 Fluent Emoji 图标。路径必须在 article 根目录内。',
            input_schema={
                'type': 'object',
                'properties': {
                    'path': {
                        'type': 'string',
                        'description': '相对于知识库根目录的文件夹路径',
                    },
                    'icon': {
                        'type': 'string',
                        'description': 'Fluent Emoji 图标名（可选）',
                    },
                },
                'required': ['path'],
                'additionalProperties': False,
            },
            handler=handle_create_folder,
            cost='none',
        ),
        Tool(
            name='submit_to_public',
            description=(
                '提交知识到公共库审批队列。提交后进入 pending 状态，'
                '需管理员审批后才正式入库。提交者 Token 可调用此工具。'
            ),
            input_schema={
                'type': 'object',
                'properties': {
                    'title': {'type': 'string', 'description': '知识标题'},
                    'body': {'type': 'string', 'description': '知识正文（Markdown）'},
                    'summary': {'type': 'string', 'description': '摘要（可选）'},
                    'sources': {
                        'type': 'array',
                        'items': {'type': 'string'},
                        'description': '来源引用列表（可选）',
                    },
                    'kind': {'type': 'string', 'default': 'concept'},
                    'author': {'type': 'string', 'description': '提交者标识（可选，默认取服务端配置）'},
                },
                'required': ['title', 'body'],
                'additionalProperties': False,
            },
            handler=handle_submit_to_public,
            cost='none',
        ),

        # ---------- Phase 7: 待办工具 ----------
        Tool(
            name='create_todo',
            description='创建一条待办事项。可关联 Wiki 页面。AI 助手可用此工具帮用户记下待办。',
            input_schema={
                'type': 'object',
                'properties': {
                    'title': {'type': 'string', 'description': '待办内容'},
                    'priority': {
                        'type': 'string', 'default': 'normal',
                        'description': '优先级：high / normal / low',
                    },
                    'related_slug': {
                        'type': 'string',
                        'description': '关联的 Wiki 页面 slug（可选）',
                    },
                },
                'required': ['title'],
                'additionalProperties': False,
            },
            handler=handle_create_todo,
            cost='none',
        ),

        # ---------- Phase 8: 工作空间工具 ----------
        Tool(
            name='list_workspace',
            description='列出当前任务工作空间目录的内容。path 为空表示根目录。返回每个条目是目录还是文件、相对路径和文件大小。无成本。',
            input_schema={
                'type': 'object',
                'properties': {
                    'path': {
                        'type': 'string',
                        'default': '',
                        'description': '相对于工作空间根目录的子目录，空字符串表示根目录',
                    },
                },
                'additionalProperties': False,
            },
            handler=handle_list_workspace,
            cost='none',
        ),
        Tool(
            name='read_workspace_file',
            description='读取当前任务工作空间内的文本文件（UTF-8）。返回文件内容，超长自动截断。二进制文件无法读取。无成本。',
            input_schema={
                'type': 'object',
                'properties': {
                    'path': {
                        'type': 'string',
                        'description': '相对于工作空间根目录的文件路径，如 "src/main.py"',
                    },
                },
                'required': ['path'],
                'additionalProperties': False,
            },
            handler=handle_read_workspace_file,
            cost='none',
        ),
        Tool(
            name='write_workspace_file',
            description='在当前任务工作空间内写入或追加文本文件。mode=overwrite 覆盖写入，mode=append 追加到末尾。会自动创建不存在的父目录。无成本。',
            input_schema={
                'type': 'object',
                'properties': {
                    'path': {
                        'type': 'string',
                        'description': '相对于工作空间根目录的文件路径，如 "README.md"',
                    },
                    'content': {
                        'type': 'string',
                        'description': '要写入的文本内容',
                    },
                    'mode': {
                        'type': 'string',
                        'enum': ['overwrite', 'append'],
                        'default': 'overwrite',
                        'description': 'overwrite 覆盖写入，append 追加到文件末尾',
                    },
                },
                'required': ['path', 'content'],
                'additionalProperties': False,
            },
            handler=handle_write_workspace_file,
            cost='none',
        ),

        # ---------- 1.2 记忆模块工具（记忆轨，独立于知识库） ----------
        Tool(
            name='search_memory',
            description='语义检索记忆（记忆轨，独立于知识库 search_kb）。消耗 OpenAI Embedding 配额。返回 Top-K 相关记忆及正文片段。',
            input_schema={
                'type': 'object',
                'properties': {
                    'query': {'type': 'string', 'description': '自然语言查询'},
                    'top_k': {
                        'type': 'integer', 'default': 5, 'minimum': 1, 'maximum': 10,
                    },
                    'kind': {
                        'type': 'string',
                        'enum': ['preference', 'fact', 'decision', 'other'],
                        'description': '记忆类型过滤（可选）',
                    },
                },
                'required': ['query'],
                'additionalProperties': False,
            },
            handler=handle_search_memory,
            cost='openai-embedding',
        ),
        Tool(
            name='list_memories',
            description='列出记忆（记忆轨）。可按 kind/status 过滤，支持分页。无成本。',
            input_schema={
                'type': 'object',
                'properties': {
                    'kind': {
                        'type': 'string',
                        'enum': ['preference', 'fact', 'decision', 'other'],
                        'description': '记忆类型过滤（可选）',
                    },
                    'status': {
                        'type': 'string',
                        'enum': ['auto', 'promoted', 'revoked'],
                        'description': '状态过滤（可选）',
                    },
                    'limit': {
                        'type': 'integer', 'default': 50, 'minimum': 1, 'maximum': 200,
                    },
                    'offset': {
                        'type': 'integer', 'default': 0, 'minimum': 0,
                    },
                },
                'additionalProperties': False,
            },
            handler=handle_list_memories,
            cost='none',
        ),
        Tool(
            name='remember',
            description='记住一条记忆（记忆轨，status=auto）。kind 可选 preference/fact/decision/other。无成本。',
            input_schema={
                'type': 'object',
                'properties': {
                    'body': {'type': 'string', 'description': '记忆正文'},
                    'kind': {
                        'type': 'string',
                        'enum': ['preference', 'fact', 'decision', 'other'],
                        'description': '记忆类型',
                    },
                    'slug': {
                        'type': 'string',
                        'description': '记忆 slug（可选，不传自动生成）',
                    },
                },
                'required': ['body', 'kind'],
                'additionalProperties': False,
            },
            handler=handle_remember,
            cost='none',
        ),
        Tool(
            name='forget_memory',
            description='撤回一条记忆（软删除，物理保留）。应仅在用户明确要求时调用，LLM 不应自动撤回。',
            input_schema={
                'type': 'object',
                'properties': {
                    'slug': {'type': 'string', 'description': '要撤回的记忆 slug'},
                },
                'required': ['slug'],
                'additionalProperties': False,
            },
            handler=handle_forget_memory,
            cost='none',
        ),
        Tool(
            name='suggest_skill',
            description='当识别到可复用操作流程时，生成技能候选草案（写入 candidates/，需人工审批后才生效）。',
            input_schema={
                'type': 'object',
                'properties': {
                    'name': {'type': 'string', 'description': '技能名'},
                    'description': {'type': 'string', 'description': '技能描述'},
                    'body': {'type': 'string', 'description': '技能工作流正文（Markdown）'},
                },
                'required': ['name', 'description', 'body'],
                'additionalProperties': False,
            },
            handler=handle_suggest_skill,
            cost='none',
        ),
    ]

    for tool in tools:
        try:
            register_tool(tool)
        except ValueError:
            # 已注册，幂等
            pass


# 导入即注册
_register_all()
