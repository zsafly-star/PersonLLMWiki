"""pdf-mcp HTTP 启动器。

pdf-mcp 源码自包含在 pdf_mcp/ 子目录下，无需 pip install。
由 builtin_mcp_manager 通过 bin/mcp/pdf-mcp/service.json 配置调用。
"""
import os
import sys

# 自包含：从本目录下的 pdf_mcp/ 加载，不依赖 pip install
_launcher_dir = os.path.dirname(os.path.abspath(__file__))
if _launcher_dir not in sys.path:
    sys.path.insert(0, _launcher_dir)

from pdf_mcp.server import mcp

host = os.environ.get('PDF_MCP_HTTP_HOST', '127.0.0.1')
port = int(os.environ.get('PDF_MCP_HTTP_PORT', '17654'))

if __name__ == '__main__':
    mcp.run(transport='streamable-http', host=host, port=port)
