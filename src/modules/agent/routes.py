"""智能体（DeepSeek Harness）模块。

通过 common.dsh_bridge 统一管理 DSH 进程：发现 / 启动 / 状态。
智能体 Tab 以 iframe 嵌入 DSH web，DSH 缺失或版本过低时优雅降级。
"""
from flask import Blueprint, render_template
from common.response import success_response
from common import dsh_bridge

agent_bp = Blueprint('agent', __name__, template_folder='templates')


@agent_bp.route('/agent')
def agent():
    return render_template('agent.html', active_view='agent')


@agent_bp.route('/api/agent/status')
def agent_status():
    """DSH 状态（供智能体 Tab 初始化 / 轮询）"""
    return success_response(dsh_bridge.get_status())


@agent_bp.route('/api/agent/start', methods=['POST'])
def agent_start():
    """拉起 DSH web（若未在运行）"""
    return success_response(dsh_bridge.start())
