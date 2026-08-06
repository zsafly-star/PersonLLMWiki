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


@pytest.fixture
def temp_resource(tmp_path):
    """提供一个临时 resource 目录"""
    return str(tmp_path / "resource")


def test_get_close_action_default(temp_resource):
    """无记录时返回 None"""
    assert get_close_action(temp_resource) is None


def test_set_and_get_close_action(temp_resource):
    """写入后能正确读取"""
    set_close_action(temp_resource, "minimize")
    assert get_close_action(temp_resource) == "minimize"

    set_close_action(temp_resource, "exit")
    assert get_close_action(temp_resource) == "exit"


def test_set_close_action_creates_dirs(temp_resource):
    """写入时自动创建 instance 目录"""
    set_close_action(temp_resource, "minimize")
    assert os.path.isdir(os.path.join(temp_resource, "instance"))


def test_is_first_launch_default(temp_resource):
    """无标记文件时为首次启动"""
    assert is_first_launch(temp_resource) is True


def test_mark_launched(temp_resource):
    """标记后不再是首次"""
    mark_launched(temp_resource)
    assert is_first_launch(temp_resource) is False


def test_invalid_close_action_raises(temp_resource):
    """非法值应报错"""
    with pytest.raises(ValueError):
        set_close_action(temp_resource, "invalid")
