"""模拟 WorkBuddy 的 4002 fetch failed 错误场景复现。

测试多种可能导致 WorkBuddy 端报 4002 的场景：
1. 正常 payload（应该成功）
2. 超大 payload（接近 16MB 限制）
3. 超大 base64 内联图片
4. 响应超时场景
5. 网络中断模拟
"""
import base64
import json
import time
import urllib.request
import urllib.error

BASE = 'http://127.0.0.1:5000/mcp'


def rpc(method, params=None, sid=None, timeout=30):
    body = {'jsonrpc': '2.0', 'id': 1, 'method': method}
    if params is not None:
        body['params'] = params
    headers = {'Content-Type': 'application/json'}
    if sid:
        headers['Mcp-Session-Id'] = sid
    req = urllib.request.Request(BASE, data=json.dumps(body).encode('utf-8'),
                                  headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()
    except Exception as e:
        return -1, {}, str(e).encode('utf-8')


def check(condition, msg):
    status = "OK" if condition else "FAIL"
    print(f'  [{status}] {msg}')
    return condition


def main():
    print('=== 4002 fetch failed 场景复现测试 ===\n')

    # Step 1: 基础连接测试
    print('[1] 基础连接测试')
    status, headers, raw = rpc('initialize', {
        'protocolVersion': '2025-06-18',
        'capabilities': {},
        'clientInfo': {'name': 'debug-4002', 'version': '1.0'},
    })
    sid = headers.get('Mcp-Session-Id')
    check(status == 200, f'initialize: HTTP {status}')
    check(bool(sid), f'Session ID: {sid[:8] if sid else "None"}...')

    # Step 2: 正常 payload（应该成功）
    print('\n[2] 正常 payload 测试')
    normal_content = '# 正常笔记\n\n这是正常的 Markdown 内容。\n'
    status, _, raw = rpc('tools/call', {
        'name': 'write_note',
        'arguments': {'path': '调试测试/正常.md', 'content': normal_content},
    }, sid=sid)
    check(status == 200, f'正常 payload: HTTP {status}')

    # Step 3: 大 payload（1MB 文本，无图片）
    print('\n[3] 大 payload 测试（1MB 文本）')
    large_text = '# 大文档\n\n' + 'A' * (1024 * 1024) + '\n'
    start = time.time()
    status, _, raw = rpc('tools/call', {
        'name': 'write_note',
        'arguments': {'path': '调试测试/大文档.md', 'content': large_text},
    }, sid=sid, timeout=60)
    elapsed = time.time() - start
    check(status == 200, f'1MB 文本: HTTP {status}, 耗时 {elapsed:.2f}s')

    # Step 4: 超大 base64 内联图片（模拟 AI 生成的图片）
    print('\n[4] 超大 base64 内联图片测试（~5MB）')
    # 创建一个 ~5MB 的伪图片
    raw_img = b'\x89PNG\r\n\x1a\n' + b'\x00' * (5 * 1024 * 1024)
    b64_img = base64.b64encode(raw_img).decode('ascii')
    content_with_img = f'# 带图\n\n![大图](data:image/png;base64,{b64_img})\n\n正文\n'

    # 计算 payload 大小
    payload_size = len(content_with_img.encode('utf-8'))
    print(f'  Payload 大小: {payload_size / 1024 / 1024:.2f} MB')

    start = time.time()
    status, _, raw = rpc('tools/call', {
        'name': 'write_note',
        'arguments': {'path': '调试测试/带大图.md', 'content': content_with_img},
    }, sid=sid, timeout=120)
    elapsed = time.time() - start
    check(status == 200, f'5MB 图片: HTTP {status}, 耗时 {elapsed:.2f}s')

    if status == 200:
        data = json.loads(raw)
        result = json.loads(data['result']['content'][0]['text'])
        check(result.get('images_extracted', 0) == 1, f'图片提取: {result.get("images_extracted", 0)} 张')
    else:
        print(f'  响应内容: {raw[:500]}')

    # Step 5: 超大 payload（接近 16MB 限制）
    print('\n[5] 超大 payload 测试（~15MB）')
    huge_text = '# 超大\n\n' + 'B' * (15 * 1024 * 1024) + '\n'
    payload_size = len(huge_text.encode('utf-8'))
    print(f'  Payload 大小: {payload_size / 1024 / 1024:.2f} MB')

    start = time.time()
    status, _, raw = rpc('tools/call', {
        'name': 'write_note',
        'arguments': {'path': '调试测试/超大.md', 'content': huge_text},
    }, sid=sid, timeout=120)
    elapsed = time.time() - start

    if status == 413:
        print(f'  [预期] Flask 返回 413 Request Entity Too Large')
        print(f'  这就是 WorkBuddy 的 4002 错误原因！')
    elif status == -1:
        print(f'  [连接失败] {raw}')
    else:
        check(status == 200, f'15MB 文本: HTTP {status}, 耗时 {elapsed:.2f}s')

    # Step 6: 响应体过大测试
    print('\n[6] 响应体过大测试（读取超大文件）')
    # 先写入一个大文件
    huge_content = '# 响应测试\n\n' + 'C' * (2 * 1024 * 1024) + '\n'
    rpc('tools/call', {
        'name': 'write_note',
        'arguments': {'path': '调试测试/响应大.md', 'content': huge_content},
    }, sid=sid)

    # 读取它
    status, _, raw = rpc('tools/call', {
        'name': 'read_note',
        'arguments': {'path': '调试测试/响应大.md', 'full': True},
    }, sid=sid, timeout=60)
    response_size = len(raw)
    check(status == 200, f'读取大文件: HTTP {status}, 响应 {response_size / 1024:.1f} KB')

    # Step 7: 网络超时测试
    print('\n[7] 网络超时测试（短超时）')
    status, _, raw = rpc('tools/call', {
        'name': 'write_note',
        'arguments': {'path': '调试测试/超时.md', 'content': 'D' * (1024 * 1024)},
    }, sid=sid, timeout=0.001)  # 极短超时
    check(status == -1, f'短超时: HTTP {status} (预期 -1)')

    print('\n=== 测试完成 ===')
    print('\n结论分析：')
    print('- 如果 [4] 失败（5MB 图片），说明图片提取导致响应异常')
    print('- 如果 [5] 返回 413，说明 Flask 的 MAX_CONTENT_LENGTH 限制')
    print('- 如果 [7] 超时但服务器正常，说明是网络问题')


if __name__ == '__main__':
    main()
