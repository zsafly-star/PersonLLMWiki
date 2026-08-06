"""公共库同步服务（Phase 2）。

功能：
- git pull 公共库到本地 COMMON_RESOURCE_PATH
- 同步后更新本地向量索引（公共库 Wiki 概念页已是编译成品，无需重新跑 LLM）
- 同步状态管理（线程安全）

仅在 INSTANCE_MODE=personal 时生效。
"""

import os
import threading
import subprocess

from config import Config


_sync_lock = threading.Lock()
_sync_status = {
    'running': False,
    'last_sync': None,
    'message': '',
    'common_page_count': 0,
}


def get_sync_status():
    """获取同步状态"""
    return dict(_sync_status)


def is_common_enabled():
    """是否启用了公共库同步"""
    return (
        Config.INSTANCE_MODE == 'personal'
        and bool(Config.COMMON_RESOURCE_PATH)
    )


def _run_git(args, cwd):
    """执行 git 命令，返回 (returncode, stdout, stderr)"""
    result = subprocess.run(
        ['git'] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def _clone_or_pull():
    """clone（首次）或 pull（后续）公共库"""
    repo_url = Config.COMMON_GIT_REPO
    local_path = Config.COMMON_RESOURCE_PATH

    if not repo_url:
        return False, '未配置 COMMON_GIT_REPO'

    os.makedirs(os.path.dirname(local_path), exist_ok=True)

    if not os.path.isdir(os.path.join(local_path, '.git')):
        # 首次 clone
        rc, out, err = _run_git(['clone', repo_url, local_path], os.path.dirname(local_path))
        if rc != 0:
            return False, f'git clone 失败: {err}'
        return True, f'git clone 成功: {out}'
    else:
        # 后续 pull
        rc, out, err = _run_git(['pull', '--ff-only'], local_path)
        if rc != 0:
            return False, f'git pull 失败: {err}'
        return True, f'git pull 成功: {out}'


def _count_common_pages():
    """统计公共库概念页数量"""
    from modules.wiki import wiki_service
    pages = wiki_service.list_common_concept_pages()
    return len(pages)


def _update_local_index():
    """同步后更新本地向量索引 + BM25 索引"""
    from modules.wiki.compiler.retrieval import update_page_embeddings
    try:
        update_page_embeddings()
        return True, '向量索引更新完成'
    except Exception as e:
        return False, f'向量索引更新失败: {e}'


def sync_common_library():
    """执行公共库同步（同步执行，调用方可在线程中调用）"""
    if not is_common_enabled():
        return {'success': False, 'message': '公共库同步未启用（需 INSTANCE_MODE=personal + COMMON_RESOURCE_PATH）'}

    with _sync_lock:
        if _sync_status['running']:
            return {'success': False, 'message': '同步正在进行中'}
        _sync_status['running'] = True
        _sync_status['message'] = '开始同步...'

    try:
        # Step 1: git pull
        _sync_status['message'] = '正在拉取公共库...'
        ok, msg = _clone_or_pull()
        if not ok:
            _sync_status['message'] = msg
            return {'success': False, 'message': msg}

        # Step 2: 统计页面
        _sync_status['message'] = '统计公共库页面...'
        count = _count_common_pages()
        _sync_status['common_page_count'] = count

        # Step 3: 更新本地索引
        _sync_status['message'] = '更新向量索引...'
        ok, msg = _update_local_index()

        import datetime
        _sync_status['last_sync'] = datetime.datetime.now().isoformat()
        _sync_status['message'] = f'同步完成：公共库 {count} 个概念页，{msg}'

        return {'success': True, 'message': _sync_status['message'], 'page_count': count}

    except subprocess.TimeoutExpired:
        _sync_status['message'] = '同步超时（git 操作超过 120 秒）'
        return {'success': False, 'message': _sync_status['message']}
    except Exception as e:
        _sync_status['message'] = f'同步失败: {e}'
        return {'success': False, 'message': _sync_status['message']}
    finally:
        _sync_status['running'] = False


def sync_common_library_async():
    """异步触发公共库同步（后台线程）"""
    if not is_common_enabled():
        return {'success': False, 'message': '公共库同步未启用'}

    with _sync_lock:
        if _sync_status['running']:
            return {'success': False, 'message': '同步正在进行中'}

    t = threading.Thread(target=sync_common_library, daemon=True)
    t.start()
    return {'success': True, 'message': '同步已启动'}
