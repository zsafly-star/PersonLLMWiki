"""JSON-RPC 2.0 错误码常量。

参考规范：https://www.jsonrpc.org/specification#section-5.1
MCP 额外错误码使用 -32001 起（保留区间 -32000 ~ -32099）。
"""


# JSON-RPC 预定义错误码
PARSE_ERROR = -32700       # JSON 解析失败
INVALID_REQUEST = -32600   # 不是合法的 JSON-RPC 请求
METHOD_NOT_FOUND = -32601  # 方法不存在
INVALID_PARAMS = -32602    # 参数非法（含路径越界）
INTERNAL_ERROR = -32603    # 服务层异常

# MCP 扩展错误码
UNAUTHORIZED = -32001      # Token 鉴权失败


class MCPError(Exception):
    """携带 JSON-RPC 错误码的异常。

    routes 层捕获后转换为 JSON-RPC error 响应。
    工具 handler 内部错误不抛 MCPError，而是返回 {isError: True}。
    """

    def __init__(self, code: int, message: str, data=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    def to_dict(self):
        err = {'code': self.code, 'message': self.message}
        if self.data is not None:
            err['data'] = self.data
        return err
