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
)
from .tools_office import (
    handle_read_document,
    handle_get_structure,
    handle_get_outline,
    handle_create_document,
    handle_add_element,
    handle_set_element,
    handle_list_sheets,
    handle_read_sheet,
    handle_write_cells,
)


def _register_all():
    """注册所有 MCP 工具。重复导入幂等。"""
    tools = [
        # ---------- Tier 1: 只读 ----------
        Tool(
            name='list_folders',
            description='列出 ZSSNote 文章知识库的顶层目录结构。无副作用，无成本。返回每个文件夹的名称、路径、图标和笔记数量。',
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

        # ---------- Phase 6: OfficeCLI 文档工具 ----------
        Tool(
            name='read_document',
            description='读取 Office 文档（Word/Excel/PPT），返回 HTML 渲染内容。AI 可以像人类一样"看到"文档布局。需要配置 OFFICECLI_PATH。',
            input_schema={
                'type': 'object',
                'properties': {
                    'path': {'type': 'string', 'description': '文档文件路径（.docx/.xlsx/.pptx）'},
                },
                'required': ['path'],
                'additionalProperties': False,
            },
            handler=handle_read_document,
            cost='none',
        ),
        Tool(
            name='get_document_structure',
            description='获取 Office 文档的 JSON 结构化数据。通过选择器定位具体元素。\n'
                        '- Word/PPT: selector 如 "/" (全文档), "/section[1]", "/slide[1]/shape[1]"\n'
                        '- Excel: selector 如 "$Sheet1" (整个工作表), "$Sheet1:A1:D10" (单元格区域)\n'
                        '需要配置 OFFICECLI_PATH。',
            input_schema={
                'type': 'object',
                'properties': {
                    'path': {'type': 'string', 'description': '文档文件路径'},
                    'selector': {
                        'type': 'string', 'default': '/',
                        'description': '元素选择器，如 "/" "$Sheet1" "/slide[1]/shape[1]"',
                    },
                },
                'required': ['path'],
                'additionalProperties': False,
            },
            handler=handle_get_structure,
            cost='none',
        ),
        Tool(
            name='get_document_outline',
            description='获取 Office 文档大纲（PPT 幻灯片标题列表 / Word 段落结构）。快速了解文档组织。需要配置 OFFICECLI_PATH。',
            input_schema={
                'type': 'object',
                'properties': {
                    'path': {'type': 'string', 'description': '文档文件路径'},
                },
                'required': ['path'],
                'additionalProperties': False,
            },
            handler=handle_get_outline,
            cost='none',
        ),
        Tool(
            name='create_document',
            description='创建新的空白 Office 文档（.docx / .xlsx / .pptx）。需要配置 OFFICECLI_PATH。',
            input_schema={
                'type': 'object',
                'properties': {
                    'path': {'type': 'string', 'description': '新文档文件路径（扩展名决定类型）'},
                },
                'required': ['path'],
                'additionalProperties': False,
            },
            handler=handle_create_document,
            cost='none',
        ),
        Tool(
            name='add_element',
            description='向 Office 文档添加元素。\n'
                        '- PPT: add slide（type=slide, props: title, subtitle）, add shape（type=shape, props: text, x, y, font, size, color）\n'
                        '- Word: add paragraph（type=paragraph, props: text, font, size）, add table\n'
                        '- Excel: add sheet（type=sheet, props: name）\n'
                        '需要配置 OFFICECLI_PATH。',
            input_schema={
                'type': 'object',
                'properties': {
                    'path': {'type': 'string', 'description': '文档文件路径'},
                    'target': {
                        'type': 'string',
                        'description': '添加目标位置。PPT: "/" 或 "/slide[1]"; Word: "/section[1]"; Excel: 省略',
                    },
                    'type': {
                        'type': 'string',
                        'description': '元素类型: slide, shape, paragraph, table, sheet',
                    },
                    'props': {
                        'type': 'object',
                        'description': '元素属性（键值对），如 {"title":"标题","text":"内容","x":"2cm","y":"5cm","font":"Arial","size":"24","color":"FF0000"}',
                    },
                },
                'required': ['path', 'target', 'type'],
                'additionalProperties': False,
            },
            handler=handle_add_element,
            cost='none',
        ),
        Tool(
            name='set_element',
            description='修改 Office 文档中的元素属性。先用 get_document_structure 查看结构，再用此工具修改。\n'
                        '示例: set /slide[1]/shape[1] text="新文字" font="Arial"\n'
                        '需要配置 OFFICECLI_PATH。',
            input_schema={
                'type': 'object',
                'properties': {
                    'path': {'type': 'string', 'description': '文档文件路径'},
                    'selector': {
                        'type': 'string',
                        'description': '元素选择器，如 "/slide[1]/shape[1]" 或 "$Sheet1:A1"',
                    },
                    'props': {
                        'type': 'object',
                        'description': '要修改的属性（键值对），如 {"text":"新内容","color":"00FF00"}',
                    },
                },
                'required': ['path', 'selector', 'props'],
                'additionalProperties': False,
            },
            handler=handle_set_element,
            cost='none',
        ),
        Tool(
            name='list_sheets',
            description='列出 Excel 文件中的所有工作表名称和索引。需要配置 OFFICECLI_PATH。',
            input_schema={
                'type': 'object',
                'properties': {
                    'path': {'type': 'string', 'description': 'Excel 文件路径'},
                },
                'required': ['path'],
                'additionalProperties': False,
            },
            handler=handle_list_sheets,
            cost='none',
        ),
        Tool(
            name='read_sheet',
            description='读取 Excel 工作表的 JSON 结构化数据（可指定 sheet 和 range）。需要配置 OFFICECLI_PATH。',
            input_schema={
                'type': 'object',
                'properties': {
                    'path': {'type': 'string', 'description': 'Excel 文件路径'},
                    'sheet': {'type': 'string', 'description': '工作表名（可选，默认 Sheet1）'},
                    'range': {'type': 'string', 'description': '单元格范围，如 A1:D10（可选）'},
                },
                'required': ['path'],
                'additionalProperties': False,
            },
            handler=handle_read_sheet,
            cost='none',
        ),
        Tool(
            name='write_cells',
            description='向 Excel 工作表批量写入单元格数据。需要配置 OFFICECLI_PATH。',
            input_schema={
                'type': 'object',
                'properties': {
                    'path': {'type': 'string', 'description': 'Excel 文件路径'},
                    'sheet': {'type': 'string', 'description': '工作表名（可选，默认 Sheet1）'},
                    'cells': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'cell': {'type': 'string', 'description': '单元格引用如 A1'},
                                'value': {'type': 'string', 'description': '单元格值'},
                            },
                        },
                        'description': '单元格数据数组 [{"cell":"A1","value":"Hello"}]',
                    },
                },
                'required': ['path', 'cells'],
                'additionalProperties': False,
            },
            handler=handle_write_cells,
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
    ]

    for tool in tools:
        try:
            register_tool(tool)
        except ValueError:
            # 已注册，幂等
            pass


# 导入即注册
_register_all()
