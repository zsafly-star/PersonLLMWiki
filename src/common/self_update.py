"""应用自更新服务。

启动时自动检查代码更新：
1. git pull（fast-forward only，仅非 embedded 模式）
2. 检测 requirements.txt 变化 → pip install（使用当前 Python 的 -m pip）
3. DB 迁移由 app.py 现有逻辑处理

用户只需重启 PersonLLMWiki 即可完成升级。
"""

import os
import sys
import subprocess
import hashlib

from config import Config


def _is_embedded_mode():
    """检测是否运行在 embedded 模式（通过检查 sys.executable 路径是否含 runtime）"""
    return 'runtime' in os.path.dirname(sys.executable).lower()


def _get_pip_command(req_path):
    """获取 pip 安装命令，使用当前 Python 的 -m pip"""
    return [sys.executable, '-m', 'pip', 'install', '-r', req_path,
            '--quiet', '--no-warn-script-location']


def _run_git(args, cwd):
    """执行 git 命令"""
    result = subprocess.run(
        ['git'] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def _file_hash(path):
    """计算文件 MD5"""
    if not os.path.isfile(path):
        return ''
    h = hashlib.md5()
    with open(path, 'rb') as f:
        h.update(f.read())
    return h.hexdigest()


def _get_requirements_path():
    """获取 requirements.txt 路径"""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(project_root, 'requirements.txt')


def _get_requirements_hash_path():
    """获取 requirements hash 记录文件路径"""
    return os.path.join(Config.INSTANCE_PATH, '.req_hash')


def _check_and_install_deps():
    """检测 requirements.txt 变化，有变化则 pip install"""
    req_path = _get_requirements_path()
    if not os.path.isfile(req_path):
        return False, 'requirements.txt 不存在'

    current_hash = _file_hash(req_path)
    hash_file = _get_requirements_hash_path()

    saved_hash = ''
    if os.path.isfile(hash_file):
        with open(hash_file, 'r') as f:
            saved_hash = f.read().strip()

    if current_hash == saved_hash:
        return False, '依赖无变化'

    print('[SelfUpdate] 检测到 requirements.txt 变化，执行 pip install...')
    result = subprocess.run(
        _get_pip_command(req_path),
        capture_output=True,
        text=True,
        timeout=300,
    )

    if result.returncode == 0:
        os.makedirs(os.path.dirname(hash_file), exist_ok=True)
        with open(hash_file, 'w') as f:
            f.write(current_hash)
        return True, '依赖更新完成'
    else:
        return False, f'pip install 失败: {result.stderr[:200]}'


def self_update():
    """执行自更新（启动时调用）"""
    logs = []

    # Step 1: git pull 代码（仅非 embedded 模式）
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if os.path.isdir(os.path.join(project_root, '.git')) and not _is_embedded_mode():
        rc, out, err = _run_git(['pull', '--ff-only'], project_root)
        if rc == 0:
            if 'Already up to date' in out or '已经是最新的' in out:
                logs.append('代码：已是最新')
            else:
                logs.append(f'代码：已更新 ({out[:100]})')
        else:
            logs.append(f'代码：git pull 失败 ({err[:100]})')
    else:
        logs.append('代码：非 Git 仓库，跳过')

    # Step 2: 检测并安装依赖
    ok, msg = _check_and_install_deps()
    logs.append(f'依赖：{msg}')

    return logs
