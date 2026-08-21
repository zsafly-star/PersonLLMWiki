from flask import Blueprint, render_template, jsonify, redirect, url_for
from common.response import success_response
from config import Config

home_bp = Blueprint('home', __name__, template_folder='templates')

@home_bp.route('/')
def index():
    """浏览器访问 / 也统一进入 Wiki/DSH 模式壳。"""
    return redirect(url_for('agent.shell'))


@home_bp.route('/home')
def home():
    return render_template('home.html', active_view='home')


@home_bp.route('/api/dashboard')
def dashboard():
    """首页工作台仪表盘数据（Phase 7）。

    汇总：
    - 实例模式 + 同步状态
    - 知识库统计（页面数、候选数）
    - MCP 服务器连接状态
    - 可用工具数量
    """
    from extensions import db
    from modules.wiki.models import WikiPage

    # 知识库统计
    total_pages = WikiPage.query.filter(
        WikiPage.review_status.in_(['approved', 'chat'])
    ).count()
    pending_candidates = WikiPage.query.filter_by(review_status='pending').count()

    # 本地概念页（文件系统）
    local_concepts = 0
    common_concepts = 0
    try:
        from modules.wiki import wiki_service
        local_concepts = len(wiki_service.list_concept_pages())
        if Config.INSTANCE_MODE == 'personal' and Config.COMMON_RESOURCE_PATH:
            common_concepts = len(wiki_service.list_common_concept_pages())
    except Exception:
        pass

    # MCP 服务器状态
    mcp_servers = []
    total_tools = 0
    try:
        from common.mcp_client import get_bus
        bus = get_bus()
        mcp_servers = bus.list_servers()
        total_tools = len(bus.get_all_tools())
    except Exception:
        pass

    # 同步状态
    sync_status = {}
    try:
        from common.sync_service import get_sync_status, is_common_enabled
        sync_status = get_sync_status()
        sync_status['enabled'] = is_common_enabled()
    except Exception:
        pass

    # OfficeCLI 可用性
    officecli_available = False
    try:
        from modules.mcp.tools_office import is_officecli_available
        officecli_available = is_officecli_available()
    except Exception:
        pass

    return jsonify({
        'code': 200,
        'data': {
            'instance_mode': Config.INSTANCE_MODE,
            'knowledge': {
                'db_pages': total_pages,
                'pending_candidates': pending_candidates,
                'local_concepts': local_concepts,
                'common_concepts': common_concepts,
            },
            'mcp': {
                'servers': mcp_servers,
                'total_tools': total_tools,
            },
            'sync': sync_status,
            'officecli_available': officecli_available,
        }
    })


@home_bp.route('/api/home/attention')
def home_attention():
    """工作台「值得关注」区域数据。

    返回需要用户关注的事项列表：
    - 待审批的 Wiki 候选页面
    - 公共库同步的新增概念
    - 最近编译异常
    """
    items = []

    # 1) 待审批 Wiki 候选
    try:
        from modules.wiki.models import WikiPage
        pending_count = WikiPage.query.filter_by(review_status='pending').count()
        if pending_count > 0:
            items.append({
                'type': 'pending',
                'text': f'{pending_count} 条概念等待审批',
                'link': '/wiki',
                'action_label': '去审批',
            })
    except Exception:
        pass

    # 2) 公共库新增概念（从 sync_service 获取）
    try:
        from common.sync_service import get_sync_status
        sync = get_sync_status()
        if sync.get('new_concepts_count', 0) > 0:
            items.append({
                'type': 'new_concepts',
                'text': f'公共库新增 {sync["new_concepts_count"]} 个概念',
                'link': '/wiki',
                'action_label': '浏览',
            })
    except Exception:
        pass

    # 3) 最近失败的自动化任务运行
    try:
        from modules.automation.models import TaskRun
        failed = TaskRun.query.filter(
            TaskRun.status == 'error'
        ).order_by(TaskRun.id.desc()).limit(3).all()
        if failed:
            count = len(failed)
            items.append({
                'type': 'build_error',
                'text': f'最近编译有 {count} 项失败',
                'link': '/automation',
                'action_label': '查看',
            })
    except Exception:
        pass

    return jsonify({'code': 200, 'data': {'items': items}})


@home_bp.route('/api/scheduler/status')
def scheduler_status():
    """定时任务调度器状态"""
    from common.scheduler import get_scheduler_status
    return jsonify({'code': 200, 'data': get_scheduler_status()})


@home_bp.route('/api/scheduler/trigger/<job_id>', methods=['POST'])
def trigger_scheduler_job(job_id):
    """手动触发定时任务"""
    from common.scheduler import trigger_job_now
    ok, msg = trigger_job_now(job_id)
    if ok:
        return jsonify({'code': 200, 'message': msg})
    return jsonify({'code': 400, 'message': msg})
