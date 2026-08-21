"""智能体（DeepSeek Harness）模块。

通过 common.dsh_bridge 统一管理 DSH 进程：发现 / 启动 / 状态。
桌面壳（shell）以 Wiki/DSH 模式切换方式嵌入 DSH web；/agent 作为 Web 浏览器降级入口。
DSH 缺失或版本过低时优雅降级。
"""
from flask import Blueprint, render_template, request
from common.response import success_response, error_response
from common import dsh_bridge

agent_bp = Blueprint('agent', __name__, template_folder='templates')


@agent_bp.route('/shell')
def shell():
    """桌面壳：Wiki/DSH 模式切换页（v0.2）。"""
    return render_template('shell.html')


@agent_bp.route('/agent')
def agent():
    return render_template('agent.html', active_view='agent')


@agent_bp.route('/api/agent/status')
def agent_status():
    """DSH 状态（供桌面壳 / 智能体页初始化与轮询）"""
    return success_response(dsh_bridge.get_status())


@agent_bp.route('/api/agent/start', methods=['POST'])
def agent_start():
    """拉起 DSH web（若未在运行）"""
    if not dsh_bridge.is_local_origin(request.headers.get('Origin')):
        return error_response('跨源请求被拒绝', 403)
    return success_response(dsh_bridge.start())
