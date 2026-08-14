"""端口分配工具测试"""
import socket
import pytest
from common.port_utils import find_free_port


def test_find_free_port_returns_int():
    """应返回一个整数端口号"""
    port = find_free_port()
    assert isinstance(port, int)


def test_find_free_port_in_range():
    """端口应在 5000-5100 范围内"""
    port = find_free_port()
    assert 5000 <= port <= 5100


def test_find_free_port_actually_free():
    """返回的端口应可绑定"""
    port = find_free_port()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(('127.0.0.1', port))
    finally:
        s.close()


def test_find_free_port_skips_occupied():
    """已占用的端口应被跳过"""
    # 先占一个 5000~5100 范围内的端口
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupied = None
    for p in range(5000, 5101):
        try:
            s.bind(('127.0.0.1', p))
            occupied = p
            break
        except OSError:
            continue
    if occupied is None:
        s.close()
        pytest.skip('5000-5100 范围内无可用端口供测试占用')
    s.listen(1)
    try:
        port = find_free_port()
        assert port != occupied
    finally:
        s.close()
