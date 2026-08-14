"""桌面应用偏好读写（关闭行为、首次启动标记）。

偏好文件存储在 ~/.personllmwiki/instance/desktop_prefs.json
"""

import json
import os

VALID_ACTIONS = {"minimize", "exit"}


def _prefs_path():
    """获取偏好文件路径"""
    from config import Config
    return os.path.join(Config.INSTANCE_PATH, "desktop_prefs.json")


def _read_prefs():
    """读取全部偏好，不存在则返回空 dict"""
    path = _prefs_path()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _write_prefs(prefs):
    """写入全部偏好（自动创建目录，原子写入）"""
    import tempfile
    path = _prefs_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    dir_ = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=dir_, prefix=".desktop_prefs-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(prefs, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def get_close_action():
    """获取关闭行为偏好。

    Returns:
        str | None: "minimize" / "exit" / None（未设置）
    """
    return _read_prefs().get("close_action")


def set_close_action(action):
    """设置关闭行为偏好。

    Args:
        action: "minimize" 或 "exit"

    Raises:
        ValueError: action 非法
    """
    if action not in VALID_ACTIONS:
        raise ValueError(f"close_action 必须是 {VALID_ACTIONS} 之一，收到: {action}")
    prefs = _read_prefs()
    prefs["close_action"] = action
    _write_prefs(prefs)


def is_first_launch():
    """是否为首次启动"""
    return not _read_prefs().get("launched", False)


def mark_launched():
    """标记已启动过（不再是首次）"""
    prefs = _read_prefs()
    prefs["launched"] = True
    _write_prefs(prefs)
