"""桌面偏好读写测试"""
import json
import os
import tempfile
import pytest
from common.desktop_prefs import (
    get_close_action,
    set_close_action,
    is_first_launch,
    mark_launched,
)


@pytest.fixture(autouse=True)
def mock_instance_path(monkeypatch, tmp_path):
    """将 Config.INSTANCE_PATH 指向临时目录"""
    instance_dir = str(tmp_path / "instance")
    monkeypatch.setattr("config.Config.INSTANCE_PATH", instance_dir)


def test_get_close_action_default():
    """无记录时返回 None"""
    assert get_close_action() is None


def test_set_and_get_close_action():
    """写入后能正确读取"""
    set_close_action("minimize")
    assert get_close_action() == "minimize"

    set_close_action("exit")
    assert get_close_action() == "exit"


def test_set_close_action_creates_dirs(monkeypatch, tmp_path):
    """写入时自动创建 instance 目录"""
    instance_dir = str(tmp_path / "instance")
    monkeypatch.setattr("config.Config.INSTANCE_PATH", instance_dir)
    set_close_action("minimize")
    assert os.path.isdir(instance_dir)


def test_is_first_launch_default():
    """无标记文件时为首次启动"""
    assert is_first_launch() is True


def test_mark_launched():
    """标记后不再是首次"""
    mark_launched()
    assert is_first_launch() is False


def test_invalid_close_action_raises():
    """非法值应报错"""
    with pytest.raises(ValueError):
        set_close_action("invalid")
