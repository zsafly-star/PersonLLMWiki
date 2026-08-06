"""动态端口分配工具"""

import socket

PORT_RANGE_START = 5000
PORT_RANGE_END = 5100


def find_free_port(start=PORT_RANGE_START, end=PORT_RANGE_END):
    """在 start~end 范围内找一个可绑定的空闲端口。

    Args:
        start: 起始端口（含）
        end: 结束端口（含）

    Returns:
        int: 可用端口号

    Raises:
        RuntimeError: 范围内无可用端口
    """
    for port in range(start, end + 1):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(('127.0.0.1', port))
            s.close()
            return port
        except OSError:
            continue
    raise RuntimeError(f"端口 {start}-{end} 范围内无可用端口")
