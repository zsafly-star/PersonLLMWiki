from flask import Blueprint, request, render_template, Response, stream_with_context
import json
import os
import threading
import queue as _q
import time
import requests
from werkzeug.utils import secure_filename
from common.llm import LLMService
from config import Config
from .services import ChatService
from common.response import success_response, error_response

chat_bp = Blueprint('chat', __name__, template_folder='templates')

# 流式输出延迟配置（秒）
_STREAM_THINKING_TOKEN_DELAY = 0.01   # 思考文字逐字推送间隔
_STREAM_CHUNK_DELAY = 0.02           # 答案分块推送间隔

# 工具名中文映射表（两个 SSE 生成器共享）
TOOL_CN_MAP = {
    'create_document': '创建文档', 'add_element': '写入内容',
    'get_structure': '获取结构', 'get_outline': '获取大纲',
    'set_element': '设置元素', 'read_document': '读取文档',
    'read_sheet': '读取表格', 'write_cells': '写入数据',
    'list_sheets': '获取表格', 'search_kb': '搜索知识库',
    'read_note': '读取笔记', 'read_wiki_page': '读取Wiki',
    'list_folders': '列出目录', 'write_note': '保存笔记',
    'compile_wiki': '编译Wiki', 'approve_candidate': '审批内容',
    'query_materials_by_params': '查询物料', 'get_material': '物料详情',
    'create_folder': '创建目录',
    'websearch__web_search': '联网搜索',
}


# Office 文件扩展名 → 用 OfficeCLI 读取
_OFFICE_EXTS = {'.docx', '.doc', '.xlsx', '.xls', '.pptx', '.ppt'}

# PDF 文件扩展名 → 提示 LLM 通过 pdf-mcp 工具按需读取
_PDF_EXTS = {'.pdf'}

# 可作为 UTF-8 文本读取的扩展名
_TEXT_EXTS = {
    '.txt', '.md', '.markdown', '.json', '.csv', '.xml', '.html', '.htm',
    '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.c', '.cpp', '.h', '.hpp',
    '.go', '.rs', '.rb', '.php', '.sh', '.bat', '.ps1', '.yml', '.yaml',
    '.toml', '.ini', '.cfg', '.conf', '.log', '.sql', '.css', '.scss',
    '.vue', '.svelte', '.env', '.gitignore', '.dockerfile',
}


def _read_text_file(filepath, filename):
    """读取文本文件内容，自动过滤 base64 内联图片。"""
    from modules.mcp.image_extractor import strip_inline_images

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    content = strip_inline_images(content)
    if len(content) > 80000:
        content = content[:80000] + '\n...(内容过长已截断)'
    return '=== ' + filename + '（文本文件，已读取） ===\n```\n' + content + '\n```'


def _read_office_file(filepath, filename):
    """通过 OfficeCLI 读取 Office 文档为 HTML。"""
    from modules.mcp.tools_office import _run_officecli
    rc, stdout, stderr = _run_officecli(['view', filepath, 'html'], timeout=60)
    if rc != 0:
        return '=== ' + filename + ' (OfficeCLI 读取失败: ' + (stderr or '未知错误') + ') ==='
    content = stdout
    if len(content) > 80000:
        content = content[:80000] + '\n...(内容过长已截断)'
    return '=== ' + filename + '（Office 文档，已读取） ===\n' + content


def _pdf_hint(filepath, filename):
    """PDF 附件不预读，提示 LLM 通过 pdf-mcp 工具按需读取。

    pdf-mcp 提供 pdf_info / pdf_read_pages / pdf_search 等工具，
    由 Agent 决定读取哪些页面，避免大 PDF 撑爆上下文。
    """
    size_kb = os.path.getsize(filepath) // 1024
    return (
        '📎 附件 ' + filename + ' (' + str(size_kb) + ' KB, PDF)。'
        '内容未预读，请按需调用 pdf-mcp 工具读取：'
        '先用 pdf-mcp__pdf_info 了解页数/大纲，'
        '再用 pdf-mcp__pdf_read_pages 或 pdf-mcp__pdf_search 读取相关内容。'
        '文件路径: ' + filepath
    )


def _read_attachments(filepaths):
    """按文件格式读取附件内容，拼接为文本供 LLM 使用。

    - Office 文档（.docx/.xlsx/.pptx 等）：调用 OfficeCLI view 预读
    - PDF 文档（.pdf）：不预读，提示 LLM 调用 pdf-mcp 工具按需读取
    - 文本文件（.txt/.md/.json/.py 等）：UTF-8 直接读取
    - 其他二进制文件：标注文件大小
    """
    parts = []
    for filepath in filepaths:
        if not filepath:
            continue
        # 知识库文件的路径是相对于 ARTICLE_PATH 的，需要解析
        if not os.path.isfile(filepath):
            kb_full = os.path.join(Config.ARTICLE_PATH, filepath)
            if os.path.isfile(kb_full):
                filepath = kb_full
            else:
                continue
        filename = os.path.basename(filepath)
        ext = os.path.splitext(filename)[1].lower()

        try:
            if ext in _OFFICE_EXTS:
                parts.append(_read_office_file(filepath, filename))
            elif ext in _PDF_EXTS:
                parts.append(_pdf_hint(filepath, filename))
            elif ext in _TEXT_EXTS or not ext:
                parts.append(_read_text_file(filepath, filename))
            else:
                size = os.path.getsize(filepath)
                parts.append('=== ' + filename + ' (' + str(size) + ' bytes, 二进制文件，无法读取) ===')
        except UnicodeDecodeError:
            size = os.path.getsize(filepath)
            parts.append('=== ' + filename + ' (' + str(size) + ' bytes, 二进制文件，无法读取) ===')
        except Exception as e:
            parts.append('=== ' + filename + ' (读取失败: ' + str(e) + ') ===')
    return '\n\n'.join(parts)


def _resolve_llm():
    """获取活跃 LLM 配置，返回 (provider, model, kwargs)。"""
    from common.llm_config import LLMConfigService
    config = LLMConfigService.get_active()
    if config:
        kwargs = {}
        if config.api_key:
            kwargs['api_key'] = config.api_key
        if config.base_url:
            kwargs['base_url'] = config.base_url
        return config.provider, config.model or '', kwargs
    return None, None, {}


@chat_bp.route('/chat')
def chat_page():
    return render_template('chat.html', active_view='chat')


@chat_bp.route('/api/chat/sessions', methods=['GET'])
def get_sessions():
    sessions = ChatService.get_all_sessions()
    return success_response(sessions)


@chat_bp.route('/api/chat/sessions', methods=['POST'])
def create_session():
    data = request.get_json() or {}
    model_name = data.get('model_name')
    session = ChatService.create_session(model_name)
    return success_response(session, '创建成功')


@chat_bp.route('/api/chat/sessions/<int:session_id>', methods=['GET'])
def get_session(session_id):
    session = ChatService.get_session_with_messages(session_id)
    if session:
        return success_response(session)
    return error_response('会话不存在', 404)


@chat_bp.route('/api/chat/sessions/<int:session_id>', methods=['DELETE'])
def delete_session(session_id):
    success = ChatService.delete_session(session_id)
    if success:
        return success_response(None, '删除成功')
    return error_response('会话不存在', 404)


@chat_bp.route('/api/chat/sessions/<int:session_id>', methods=['PUT'])
def update_session(session_id):
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    if not name:
        return error_response('名称不能为空', 400)
    if len(name) > 100:
        return error_response('名称不能超过100个字符', 400)
    result = ChatService.update_session(session_id, name)
    if result:
        return success_response(result, '修改成功')
    return error_response('会话不存在', 404)


@chat_bp.route('/api/chat/sessions/<int:session_id>/messages', methods=['POST'])
def send_message(session_id):
    data = request.get_json()
    if not data or 'content' not in data:
        return error_response('缺少消息内容')

    try:
        use_wiki = data.get('use_wiki', False)
        response = ChatService.chat(session_id, data['content'], use_wiki=use_wiki)
        session = ChatService.get_session_with_messages(session_id)
        return success_response(session, '发送成功')
    except ValueError as e:
        return error_response(str(e), 404)
    except Exception as e:
        return error_response(f'发送失败: {str(e)}')


@chat_bp.route('/api/chat/upload', methods=['POST'])
def upload_file():
    """文件上传（Phase 5）。保存到 attachment 目录，返回路径。"""
    if 'file' not in request.files:
        return error_response('未收到文件', 400)

    file = request.files['file']
    original_name = file.filename
    if not original_name:
        return error_response('文件名为空', 400)

    # secure_filename 会剥离中文字符，保留原名用于显示，用安全名存储
    original_ext = os.path.splitext(original_name)[1].lower()  # 先提取扩展名
    safe_name = secure_filename(original_name)
    # 如果安全名丢失了扩展名，补回去
    safe_ext = os.path.splitext(safe_name)[1].lower()
    if original_ext and safe_ext != original_ext:
        safe_name = safe_name + original_ext
    if not safe_name or len(safe_name) < 2:
        import uuid
        safe_name = 'upload_' + uuid.uuid4().hex[:8] + original_ext

    # 限制文件大小 50MB
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > 50 * 1024 * 1024:
        return error_response('文件超过 50MB 限制', 400)

    upload_dir = os.path.join(Config.ATTACHMENT_PATH, 'chat_uploads')
    os.makedirs(upload_dir, exist_ok=True)

    # 加时间戳防冲突
    ts = int(time.time())
    saved_name = f'{ts}_{safe_name}'
    filepath = os.path.join(upload_dir, saved_name)
    file.save(filepath)

    return success_response({
        'filename': original_name,
        'path': filepath,
        'size': size,
        'saved_name': saved_name,
    }, '上传成功')


@chat_bp.route('/api/chat/kb-tree', methods=['POST'])
def kb_tree():
    """获取知识库目录树。POST {path: '子目录路径'} 返回 {folders:[], files:[]}。"""
    data = request.get_json() or {}
    sub_path = data.get('path', '').strip().lstrip('/')
    root = Config.ARTICLE_PATH
    dir_path = os.path.join(root, sub_path) if sub_path else root
    # 安全检查：防止越界
    if not os.path.abspath(dir_path).startswith(os.path.abspath(root)):
        return error_response('路径越界')
    if not os.path.isdir(dir_path):
        return error_response('目录不存在', 404)
    try:
        entries = os.listdir(dir_path)
    except PermissionError:
        return error_response('无权限访问')
    folders = []
    files = []
    for name in entries:
        full = os.path.join(dir_path, name)
        if os.path.isdir(full):
            if not name.startswith('.') and name != '__pycache__':
                folders.append(name)
        elif os.path.isfile(full):
            if not name.startswith('.') and not name.startswith('~'):
                # Only show readable formats
                ext = os.path.splitext(name)[1].lower()
                if ext in ('.md', '.docx', '.txt', '.pdf', '.xlsx', '.doc', '.pptx'):
                    files.append(name)
    folders.sort()
    files.sort()
    return success_response({
        'folders': folders,
        'files': files,
        'current': sub_path,
    })


def _generate_agent_sse(session_id, message_history, mode, stream_msg_id, user_message=None):
    """共享 Agent SSE 生成器（v4 连续流）。

    流程：后台线程跑 agent_chat → thinking_stream（逐字） → thinking_done → chunk → done。
    """
    from common.agent import agent_chat
    from app import app as _app
    from extensions import db
    from .models import ChatMessage

    sep = '\n\n'
    thinking_text = ''          # 累积所有思考文字（字符串）
    tool_calls_info = []        # 仅用于导出文件提取

    result_queue = _q.Queue()

    def _run_agent():
        try:
            with _app.app_context():
                def on_progress(evt, data):
                    result_queue.put(('progress', {'type': evt, 'data': data}))
                result = agent_chat(message_history, use_tools=True, mode=mode,
                                    progress_callback=on_progress)
                result_queue.put(('ok', result))
        except Exception as e:
            result_queue.put(('error', str(e)))

    agent_thread = threading.Thread(target=_run_agent, daemon=True)
    agent_thread.start()

    while True:
        try:
            status, value = result_queue.get(timeout=2)
            if status == 'progress':
                evt = value
                if evt['type'] == 'thinking_text':
                    text = evt['data'].get('text', '')
                    if text:
                        if not thinking_text:
                            # 刚开始有思考文字，先发 thinking_start 让前端初始化 UI
                            yield f"data: {json.dumps({'thinking_start': True}, ensure_ascii=False)}{sep}"
                        thinking_text += text
                        for i in range(0, len(text)):
                            token = text[i:i+1]
                            yield f"data: {json.dumps({'thinking_stream': {'token': token}}, ensure_ascii=False)}{sep}"
                            time.sleep(_STREAM_THINKING_TOKEN_DELAY)
                elif evt['type'] == 'tool_start':
                    d = evt['data']
                    # 首个工具调用且没有思考文字时，发 thinking_start
                    if not thinking_text and not tool_calls_info:
                        yield f"data: {json.dumps({'thinking_start': True}, ensure_ascii=False)}{sep}"
                    tool_calls_info.append({
                        'tool_name': d['name'],
                        'tool_arguments': d.get('arguments', {}),
                    })
                elif evt['type'] == 'tool_result':
                    # 不发送 SSE 事件，纯记录
                    pass
                elif evt['type'] in ('custom_stage_start', 'custom_stage_end'):
                    pass  # 连续流不区分阶段
            elif status == 'ok':
                result = value
                break
            elif status == 'error':
                result = value
                break
        except _q.Empty:
            if agent_thread.is_alive():
                yield f"data: {json.dumps({'heartbeat': True}, ensure_ascii=False)}{sep}"
            else:
                status, result = 'error', 'Agent 异常终止'
                break

    # 提取导出文件
    exported_files = []
    _seen = set()
    for tc in reversed(tool_calls_info):
        if tc['tool_name'] == 'create_document':
            args = tc['tool_arguments']
            fpath = args.get('path', '') if isinstance(args, dict) else (args if isinstance(args, str) else '')
            fname = os.path.basename(fpath) if fpath else ''
            if fname and fname not in _seen:
                _seen.add(fname)
                exported_files.insert(0, {'filename': fname, 'path': fpath})

    yield f"data: {json.dumps({'thinking_done': True}, ensure_ascii=False)}{sep}"

    if status == 'error':
        full_response = '执行失败: ' + result
        yield f"data: {json.dumps({'chunk': full_response}, ensure_ascii=False)}{sep}"
        ChatService.update_message(stream_msg_id, full_response)
        thinking_payload = {'thinking_text': thinking_text, 'exported_files': exported_files}
        _msg = ChatMessage.query.get(stream_msg_id)
        if _msg:
            _msg.thinking_json = json.dumps(thinking_payload, ensure_ascii=False)
        db.session.commit()
        yield f"data: {json.dumps({'done': True, 'thinking': thinking_payload}, ensure_ascii=False)}{sep}"
    else:
        response_text = result.get('response', '')
        full_response = response_text

        chunk_size = 32
        sent_chars = 0
        for i in range(0, len(full_response), chunk_size):
            chunk_text = full_response[i:i + chunk_size]
            payload = json.dumps({'chunk': chunk_text}, ensure_ascii=False)
            try:
                yield f"data: {payload}{sep}"
                sent_chars = i + chunk_size
                time.sleep(_STREAM_CHUNK_DELAY)
            except (GeneratorExit, BrokenPipeError, ConnectionError):
                break

        saved_content = full_response[:sent_chars] if sent_chars < len(full_response) else full_response
        if sent_chars < len(full_response):
            saved_content += '\n\n_[已停止生成]_'
        ChatService.update_message(stream_msg_id, saved_content)
        thinking_payload = {'thinking_text': thinking_text, 'exported_files': exported_files}
        _msg = ChatMessage.query.get(stream_msg_id)
        if _msg:
            _msg.thinking_json = json.dumps(thinking_payload, ensure_ascii=False)
        db.session.commit()
        yield f"data: {json.dumps({'done': True, 'stopped': sent_chars < len(full_response), 'thinking': thinking_payload}, ensure_ascii=False)}{sep}"

    # 自动生成标题（仅 stream_message 传入 user_message）
    if user_message:
        from .models import ChatSession as Cs
        session_obj = Cs.query.get(session_id)
        if session_obj and (not session_obj.name or session_obj.name.startswith('会话 ')):
            try:
                provider2, model2, kwargs2 = _resolve_llm()
                if provider2:
                    title_prompt = [
                        {'role': 'system', 'content': '请根据用户的第一条消息，用4-10个汉字概括对话主题，直接输出标题，不要加引号、不要有多余内容。'},
                        {'role': 'user', 'content': user_message},
                    ]
                    title = LLMService.chat(provider2, model2, title_prompt, **kwargs2)
                    title = title.strip().strip('"\'""''')
                    if title and len(title) <= 30:
                        session_obj.name = title
                        db.session.commit()
            except Exception:
                pass

    updated = ChatService.get_session_with_messages(session_id)
    session_name = updated['session']['name'] if updated else ''
    yield f"data: {json.dumps({'session_name': session_name}, ensure_ascii=False)}{sep}"


@chat_bp.route('/api/chat/sessions/<int:session_id>/stream', methods=['POST'])
def stream_message(session_id):
    data = request.get_json()
    if not data or 'content' not in data:
        return error_response('缺少消息内容')

    session = ChatService.get_session(session_id)
    if not session:
        return error_response('会话不存在', 404)

    use_wiki = data.get('use_wiki', False)
    user_message = data['content']
    attachments = data.get('attachments', [])
    mode = data.get('mode', 'quick')  # 'quick' or 'expert'

    # 使用前端传来的 display_text（含原始文件名），避免存储 saved_name
    user_message = data.get('display_text', user_message)

    ChatService.add_message(session_id, 'user', user_message)

    from .models import ChatMessage
    messages = ChatMessage.query.filter_by(session_id=session_id)\
        .order_by(ChatMessage.created_at.asc()).all()
    message_history = [{'role': m.role, 'content': m.content} for m in messages]

    # 读取附件内容并注入到最后一条用户消息中供 LLM 使用
    if attachments and message_history:
        attachment_content = _read_attachments(attachments)
        if attachment_content:
            message_history[-1]['content'] = message_history[-1]['content'] + '\n\n---\n[系统提示：以下附件内容已预先从文件中读取并内联在下方，请直接阅读使用，勿再调用文件读取工具]\n\n' + attachment_content

    # Wiki 知识库：将上下文注入到最后一条用户消息中
    if use_wiki:
        wiki_prompt = ChatService._build_wiki_prompt()
        if wiki_prompt and message_history:
            message_history[-1]['content'] = wiki_prompt + '\n\n---\n\n' + message_history[-1]['content']

    # Agent 模式：自动识别，始终走 agent_chat（带 MCP 工具调用）
    stream_msg = ChatService.add_message(session_id, 'assistant', '')

    return Response(
        stream_with_context(_generate_agent_sse(session_id, message_history, mode, stream_msg.id, user_message=user_message)),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


@chat_bp.route('/api/chat/sessions/<int:session_id>/to-article', methods=['POST'])
def chat_to_article(session_id):
    data = request.get_json()
    title = data.get('title') if data else None
    folder_path = data.get('folder_path') if data else None

    try:
        article = ChatService.chat_to_article(session_id, title, folder_path)
        return success_response(article, '保存成功')
    except ValueError as e:
        return error_response(str(e), 404)
    except Exception as e:
        return error_response(f'保存失败: {str(e)}')


@chat_bp.route('/api/chat/messages/<int:message_id>', methods=['DELETE'])
def delete_message(message_id):
    try:
        ChatService.delete_message_pair(message_id)
        return success_response(None, '删除成功')
    except ValueError as e:
        return error_response(str(e), 404)
    except Exception as e:
        return error_response(f'删除失败: {str(e)}')


@chat_bp.route('/api/chat/messages/<int:message_id>/edit', methods=['POST'])
def edit_message(message_id):
    """修改用户消息内容，删除其后的 AI 回复。"""
    data = request.get_json()
    if not data or 'content' not in data:
        return error_response('缺少消息内容')
    try:
        ChatService.edit_message(message_id, data['content'])
        return success_response(None, '修改成功')
    except ValueError as e:
        return error_response(str(e), 404)
    except Exception as e:
        return error_response(f'修改失败: {str(e)}')


@chat_bp.route('/api/chat/sessions/<int:session_id>/regenerate', methods=['POST'])
def regenerate_response(session_id):
    """修改用户消息后，删除旧回复，流式重新生成。"""
    data = request.get_json()
    if not data or 'message_id' not in data:
        return error_response('缺少 message_id')

    message_id = data['message_id']
    new_content = data.get('content', '')
    mode = data.get('mode', 'quick')

    session = ChatService.get_session(session_id)
    if not session:
        return error_response('会话不存在', 404)

    # 如果提供了新内容，edit_message 会同时截断后续消息并返回历史
    if new_content:
        _, message_history = ChatService.edit_message(message_id, new_content)
    else:
        # 无新内容时，手动截断旧回复
        from .models import ChatMessage
        user_msg = ChatMessage.query.get(message_id)
        if user_msg:
            ChatMessage.query.filter(
                ChatMessage.session_id == session_id,
                ChatMessage.id > message_id
            ).delete(synchronize_session=False)
            from extensions import db
            db.session.commit()
        message_history = [{'role': m.role, 'content': m.content}
                           for m in ChatMessage.query.filter_by(session_id=session_id)
                           .order_by(ChatMessage.created_at.asc()).all()]

    # 创建空的 assistant 消息占位
    stream_msg = ChatService.add_message(session_id, 'assistant', '')

    return Response(
        stream_with_context(_generate_agent_sse(session_id, message_history, mode, stream_msg.id)),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


@chat_bp.route('/api/chat/messages/<int:message_id>/to-article', methods=['POST'])
def message_to_article(message_id):
    """将单条消息保存为文章。"""
    from .models import ChatMessage
    msg = ChatMessage.query.get(message_id)
    if not msg:
        return error_response('消息不存在', 404)
    if msg.role != 'assistant':
        return error_response('只能保存 AI 回复', 400)

    data = request.get_json() or {}
    title = data.get('title', '')
    folder_path = data.get('folder_path', '')

    try:
        article = ChatService.message_to_article(msg, title, folder_path)
        return success_response(article, '保存成功')
    except ValueError as e:
        return error_response(str(e), 404)
    except Exception as e:
        return error_response(f'保存失败: {str(e)}')


@chat_bp.route('/api/chat/models', methods=['GET'])
def get_models():
    models = LLMService.get_all_models()
    return success_response(models)


@chat_bp.route('/api/chat/active-config', methods=['GET'])
def get_active_config():
    from common.llm_config import LLMConfigService
    config = LLMConfigService.get_active()
    if not config:
        return success_response(None)
    return success_response({
        'provider': config.provider,
        'model': config.model,
        'name': config.name,
        'id': config.id,
    })


@chat_bp.route('/api/chat/model-configs', methods=['GET'])
def list_model_configs():
    """获取所有可用的 LLM 配置列表"""
    from common.llm_config import LLMConfigService
    configs = LLMConfigService.get_all()
    active = LLMConfigService.get_active()
    active_id = active.id if active else None
    return success_response({
        'models': configs,
        'active_id': active_id,
    })


@chat_bp.route('/api/chat/model-configs/switch', methods=['POST'])
def switch_model():
    """切换活跃 LLM 配置"""
    from common.llm_config import LLMConfigService
    data = request.get_json(silent=True) or {}
    config_id = data.get('id')
    if not config_id:
        return error_response('缺少配置 ID')

    config = LLMConfigService.update(config_id, {'is_active': True})
    if not config:
        return error_response('配置不存在')

    return success_response(config)


@chat_bp.route('/api/chat/preview-doc', methods=['GET'])
def preview_doc():
    """根据相对路径预览文档内容"""
    rel_path = request.args.get('path', '').strip()
    if not rel_path:
        return error_response('缺少文件路径')

    # 拼接完整路径
    full_path = os.path.join(Config.ARTICLE_PATH, rel_path)

    # 安全检查
    if '..' in rel_path or not os.path.isfile(full_path):
        return error_response('文件不存在', 404)

    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return success_response({
            'title': os.path.splitext(os.path.basename(rel_path))[0],
            'content': content,
            'path': rel_path,
            'type': 'markdown',
        })
    except Exception as e:
        return error_response(f'读取失败: {str(e)}')


@chat_bp.route('/api/chat/preview-attachment', methods=['GET'])
def preview_attachment():
    """预览上传的附件内容。根据 saved_name 在 chat_uploads 中查找。"""
    return _resolve_and_preview('chat_uploads', strip_images=True)


def _preview_file_by_ext(filepath, filename, strip_images=False):
    """按扩展名预览文件内容（供 preview_attachment / preview_export 共用）。"""
    ext = os.path.splitext(filename)[1].lower()
    try:
        if ext in _OFFICE_EXTS:
            from modules.mcp.tools_office import _run_officecli
            rc, stdout, stderr = _run_officecli(['view', filepath, 'html'], timeout=60)
            if rc != 0:
                return error_response('OfficeCLI 读取失败: ' + (stderr or '未知错误'))
            return success_response({'title': filename, 'content': stdout, 'type': 'html'})
        elif ext in _TEXT_EXTS or not ext:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            if strip_images:
                from modules.mcp.image_extractor import strip_inline_images
                content = strip_inline_images(content)
            return success_response({'title': filename, 'content': content, 'type': 'markdown'})
        elif ext in _PDF_EXTS:
            size_kb = os.path.getsize(filepath) // 1024
            return success_response({
                'title': filename,
                'content': 'PDF 文件（' + str(size_kb) + ' KB），暂不支持在线预览。请下载后查看。',
                'type': 'text',
            })
        else:
            return error_response('不支持预览此文件类型')
    except UnicodeDecodeError:
        return error_response('文件编码不支持预览')
    except Exception as e:
        return error_response(f'读取失败: {str(e)}')


def _resolve_and_preview(subdir, strip_images=False):
    """安全解析文件名并预览 {ATTACHMENT_PATH}/{subdir}/ 下的文件。"""
    filename = request.args.get('file', '').strip()
    if not filename:
        return error_response('缺少文件名')
    if '..' in filename or '/' in filename or '\\' in filename:
        return error_response('非法文件名', 400)

    filepath = os.path.join(Config.ATTACHMENT_PATH, subdir, filename)
    if not os.path.isfile(filepath):
        return error_response('文件不存在', 404)
    return _preview_file_by_ext(filepath, filename, strip_images=strip_images)


@chat_bp.route('/api/chat/file-exports/preview', methods=['GET'])
def preview_export():
    """预览 file_exports 目录中的导出文件。"""
    return _resolve_and_preview('file_exports', strip_images=True)


@chat_bp.route('/api/chat/file-exports/download', methods=['GET'])
def download_export():
    """下载 file_exports 目录中的导出文件。"""
    filename = request.args.get('file', '').strip()
    if not filename:
        return error_response('缺少文件名')
    if '..' in filename or '/' in filename or '\\' in filename:
        return error_response('非法文件名', 400)

    filepath = os.path.join(Config.ATTACHMENT_PATH, 'file_exports', filename)
    if not os.path.isfile(filepath):
        return error_response('文件不存在', 404)

    from flask import send_file
    return send_file(filepath, as_attachment=True, download_name=filename)


# 兼容旧版 API 端点
@chat_bp.route('/api/chat/history', methods=['GET'])
def get_chat_history():
    """获取聊天历史（兼容旧版）"""
    sessions = ChatService.get_all_sessions()
    messages = []
    for session in sessions:
        session_messages = session.get('messages', [])
        for msg in session_messages:
            messages.append({
                'role': msg.get('role'),
                'content': msg.get('content'),
                'timestamp': msg.get('created_at', 0)
            })
    return success_response(messages)


@chat_bp.route('/api/chat/history', methods=['DELETE'])
def clear_chat_history():
    """清除聊天历史（兼容旧版）"""
    sessions = ChatService.get_all_sessions()
    for session in sessions:
        session_id = session.get('id')
        if session_id:
            ChatService.delete_session(session_id)
    return success_response(None, '清除成功')


@chat_bp.route('/api/chat/completion', methods=['POST'])
def chat_completion():
    """聊天完成接口（兼容旧版）"""
    data = request.get_json()
    if not data or 'message' not in data:
        return error_response('缺少消息内容')

    try:
        model = data.get('model', 'default')
        session = ChatService.create_session(model)
        session_id = session.get('id')
        
        response = ChatService.chat(session_id, data['message'])
        return success_response({
            'response': response
        })
    except Exception as e:
        return error_response(f'请求失败: {str(e)}')


# ---- Mermaid 代理（绕过浏览器 ORB 拦截） ----

@chat_bp.route('/api/chat/mermaid-img', methods=['GET'])
def mermaid_proxy():
    """代理 mermaid.ink 图片请求，避免浏览器 ORB 拦截。"""
    code = request.args.get('code', '').strip()
    if not code:
        return error_response('缺少 mermaid 代码')
    try:
        # mermaid.ink 支持直接 base64url 编码原始代码
        import base64
        encoded = base64.urlsafe_b64encode(code.encode('utf-8')).decode('ascii').rstrip('=')
        url = 'https://mermaid.ink/img/' + encoded
        resp = requests.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
        if resp.status_code >= 400:
            return error_response(f'Mermaid 渲染失败 (HTTP {resp.status_code})，请检查语法')
        content_type = resp.headers.get('Content-Type', 'image/png')
        return Response(resp.content, mimetype=content_type,
                        headers={'Cache-Control': 'public, max-age=3600'})
    except requests.Timeout:
        return error_response('Mermaid 渲染超时，图表可能过于复杂')
    except Exception as e:
        return error_response(f'Mermaid 渲染失败: {str(e)}')
