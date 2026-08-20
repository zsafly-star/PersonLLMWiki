"""自动化任务执行引擎。

复用公共 react loop（common/agent_core.run_agent_loop），专门为定时任务设计：
- 接受自定义 system prompt（即任务描述）
- 支持按 MCP 服务器过滤工具
- 执行结果写入 AutomationTask.last_result
"""

import json
import logging
from datetime import datetime

from extensions import db
from common.mcp_client import get_bus
from common.agent_core import run_agent_loop, get_active_llm

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 10


def _filter_tools(task_mcp_servers):
    """根据任务配置的 MCP 服务器过滤工具列表。

    Args:
        task_mcp_servers: 逗号分隔的服务器名，空字符串表示不过滤

    Returns:
        LLM function-calling 格式的工具列表
    """
    bus = get_bus()
    all_tools = bus.get_tools_for_llm()

    if not task_mcp_servers:
        return all_tools

    server_names = set(s.strip() for s in task_mcp_servers.split(',') if s.strip())
    if not server_names:
        return all_tools

    filtered = []
    for tool in all_tools:
        tool_name = tool['function']['name']
        # 本地工具（不含 __）始终包含
        if '__' not in tool_name:
            filtered.append(tool)
            continue
        # 远程工具：按服务器名过滤
        server = tool_name.split('__', 1)[0]
        if server in server_names:
            filtered.append(tool)

    return filtered


def run_task(task_id, trigger='scheduled'):
    """执行一个自动化任务（同步），将结果写入 TaskRun 记录。

    Args:
        task_id: 任务 ID
        trigger: 'manual' | 'scheduled'
    """
    from modules.automation.models import AutomationTask, TaskRun

    task = AutomationTask.query.get(task_id)
    if not task:
        return None

    logger.info(f'[Automation] 开始执行任务 #{task_id}: {task.name}')

    # 创建运行记录
    run = TaskRun(task_id=task.id, trigger=trigger, status='running')
    db.session.add(run)
    db.session.flush()  # 获取 run.id

    # 获取活跃 LLM
    provider, _, _ = get_active_llm()
    if not provider:
        _finish_run(run, status='error', error='未配置活跃的 LLM')
        _update_task_last(task)
        return run.id

    # 获取工具（按 MCP 服务器过滤）
    tools = _filter_tools(task.mcp_servers)

    # 构建消息
    system_prompt = f"""你是一个自动化任务执行助手。请严格按照以下任务描述执行操作：
 
{task.prompt}
 
你可以调用工具来完成任务。完成后请总结执行结果。"""
    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': task.prompt},
    ]

    try:
        result = run_agent_loop(messages, tools=tools, max_rounds=MAX_TOOL_ROUNDS)
        _finish_run(run, status='ok', response=result['response'], tool_calls=result['tool_calls'])
        _update_task_last(task)
        return run.id
    except Exception as e:
        logger.error(f'[Automation] 任务 #{task_id} 执行异常: {e}')
        _finish_run(run, status='error', error=f'执行异常: {str(e)}')
        _update_task_last(task)
        return run.id


def _finish_run(run, status='ok', response='', error='', tool_calls=None):
    """完成运行记录。"""
    run.finished_at = datetime.utcnow()
    run.status = status
    run.result = json.dumps({
        'status': status,
        'response': response[:1000] if response else '',
        'error': error[:1000] if error else '',
        'tool_calls': (tool_calls or [])[:20],
        'rounds': len(tool_calls) if tool_calls else 0,
    }, ensure_ascii=False)
    db.session.commit()


def _update_task_last(task):
    """更新任务本身的 last_run / last_result。"""
    task.last_run = datetime.utcnow()
    task.last_result = json.dumps({
        'status': 'ok',
        'response': '完整记录见运行记录',
    }, ensure_ascii=False)
    db.session.commit()
