"""发布安装包到 GitLab Releases。

用法：
  python packaging/release.py 1.0.0 release/installer/PersonLLMWiki-Setup-1.0.0.exe

环境变量：
  GITLAB_TOKEN    GitLab Personal Access Token（scope: api）
"""

import json
import os
import socket
import subprocess
import sys
import urllib.error
import urllib.request

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(THIS_DIR)

GITLAB_HOST = "gitlab.xiangyuniot.com"
GITLAB_PROJECT = "AiTeam/personllmwiki"

# 大文件上传超时设置
socket.setdefaulttimeout(600)


def _api_request(method, path, token, data=None, files=None):
    """GitLab API 请求"""
    url = f"http://{GITLAB_HOST}/api/v4{path}"
    body = None
    boundary = None

    if files:
        boundary = "----PyReleaseBoundary"
        body = b""
        for field, value in (data or {}).items():
            body += f"--{boundary}\r\n".encode()
            body += f'Content-Disposition: form-data; name="{field}"\r\n\r\n'.encode()
            body += str(value).encode() + b"\r\n"
        for filename, filepath in files.items():
            body += f"--{boundary}\r\n".encode()
            body += f'Content-Disposition: form-data; name="{filename}"; filename="{os.path.basename(filepath)}"\r\n'.encode()
            body += b"Content-Type: application/octet-stream\r\n\r\n"
            with open(filepath, "rb") as f:
                body += f.read()
            body += b"\r\n"
        body += f"--{boundary}--\r\n".encode()
    elif data:
        body = json.dumps(data).encode()

    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("PRIVATE-TOKEN", token)
    if files:
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    elif data:
        req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()
        print(f"[release] API 错误 {e.code}: {err_body}")
        return None


def publish_release(version, installer_path, zip_path=None):
    """推 tag + 创建 GitLab Release + 上传安装包 + 资源包"""
    token = os.getenv("GITLAB_TOKEN", "")
    if not token:
        print("[release] 错误: 缺少 GITLAB_TOKEN 环境变量")
        print("[release] 获取方式: GitLab → Settings → Access Tokens → 勾选 api scope")
        return False

    if not os.path.isfile(installer_path):
        print(f"[release] 错误: 文件不存在: {installer_path}")
        return False

    tag = f"v{version}"
    project_id = urllib.request.quote(GITLAB_PROJECT, safe="")
    filename = os.path.basename(installer_path)

    # 1. 推送 tag
    print(f"[release] === 发布 {tag} 到 GitLab ===")
    print(f"[release] 推送 tag {tag}...")
    result = subprocess.run(
        ["git", "push", "origin", tag],
        cwd=PROJECT_DIR,
        capture_output=True, text=True,
    )
    if result.returncode != 0 and "already exists" not in result.stderr:
        print(f"[release] git push tag 失败: {result.stderr}")
        return False

    # 2. 创建 Release
    print("[release] 创建 Release...")
    release = _api_request("POST", f"/projects/{project_id}/releases", token, data={
        "tag_name": tag,
        "name": tag,
        "description": f"PersonLLMWiki 桌面版 {tag}",
        "ref": "main",
    })
    if not release:
        print("[release] Release 可能已存在，跳过创建")
    else:
        print("[release] Release 已创建")

    # 3. 上传安装包
    size_mb = os.path.getsize(installer_path) / 1024 / 1024
    print(f"[release] 上传 {filename} ({size_mb:.1f} MB)...")
    upload = _api_request("POST", f"/projects/{project_id}/uploads", token,
        files={"file": installer_path},
    )
    if not upload or "url" not in upload:
        print("[release] 文件上传失败")
        return False

    full_url = f"http://{GITLAB_HOST}{upload['url']}"
    print(f"[release] 上传成功: {full_url}")

    # 4. 关联文件到 Release
    print("[release] 关联安装包到 Release...")
    link = _api_request("POST", f"/projects/{project_id}/releases/{tag}/assets/links", token, data={
        "name": filename,
        "url": full_url,
        "link_type": "package",
    })
    if link:
        print("[release] 安装包已关联到 Release")
    else:
        print("[release] 关联失败（可能已存在）")

    release_page = f"http://{GITLAB_HOST}/{GITLAB_PROJECT}/-/releases/{tag}"
    print(f"\n[release] 完成！Release 页面: {release_page}")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python packaging/release.py <version> <installer_path>")
        print("示例: python packaging/release.py 1.0.0 release/installer/PersonLLMWiki-Setup-1.0.0.exe")
        sys.exit(1)

    version = sys.argv[1]
    installer = sys.argv[2]

    if not publish_release(version, installer):
        sys.exit(1)
