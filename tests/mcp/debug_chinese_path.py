"""模拟中文路径调用 write_note，验证是否引发 WinError 123。"""
import json
import urllib.request
import urllib.error

BASE = 'http://127.0.0.1:5000/mcp'

def rpc(method, params=None, sid=None):
    body = {'jsonrpc': '2.0', 'id': 1, 'method': method}
    if params is not None:
        body['params'] = params
    headers = {'Content-Type': 'application/json'}
    if sid:
        headers['Mcp-Session-Id'] = sid
    req = urllib.request.Request(BASE, data=json.dumps(body).encode('utf-8'),
                                  headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()

def main():
    # 1. 建立会话
    status, headers, raw = rpc('initialize', {
        'protocolVersion': '2025-06-18',
        'capabilities': {},
        'clientInfo': {'name': 'chinese-debug', 'version': '1.0'},
    })
    sid = headers.get('Mcp-Session-Id')
    if status != 200:
        print(f'initialize failed: {status}')
        return
    print(f'Session: {sid[:8]}...')

    # 2. 发送中文路径请求
    print('\n--- 测试 1: 纯中文路径 ---')
    status, _, raw = rpc('tools/call', {
        'name': 'write_note',
        'arguments': {
            'path': '工作/会议记录.md',
            'content': '# 周一会议\n\n工作安排：完成 MCP 调试。'
        }
    }, sid=sid)
    data = json.loads(raw)
    print(f'HTTP: {status}')
    print(f'Response: {data["result"]["content"][0]["text"]}')

    # 3. 发送复杂路径请求
    print('\n--- 测试 2: 复杂中文路径 ---')
    status, _, raw = rpc('tools/call', {
        'name': 'write_note',
        'arguments': {
            'path': '项目资料/2025年度/研发部/进度报告.md',
            'content': '# 进度\n\n完成率 100%。'
        }
    }, sid=sid)
    data = json.loads(raw)
    print(f'HTTP: {status}')
    print(f'Response: {data["result"]["content"][0]["text"]}')

if __name__ == '__main__':
    main()
