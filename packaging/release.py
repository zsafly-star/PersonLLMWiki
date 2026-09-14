"""发布安装包到 GitHub Releases。

用法：
  python packaging/release.py <version> <installer_path>

环境变量：
  GITHUB_TOKEN    GitHub Personal Access Token（scope: repo；或 GH_TOKEN 等价）
  GITHUB_REPO     可选，形如 owner/repo；缺省从 `git remote get-url origin` 自动解析

GitHub 仓库 owner/repo 从 remote origin 自动解析（例如
https://github.com/zsafly-star/PersonLLMWiki.git -> zsafly-star/PersonLLMWiki），
也可用 GITHUB_REPO 环境变量覆盖。
"""

import json
import os
import re
import socket
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(THIS_DIR)

API_BASE = "https://api.github.com"
UPLOAD_BASE = "https://uploads.github.com"

# 大文件上传超时设置
socket.setdefaulttimeout(600)


def _token():
    return os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or ""


def _repo():
    """解析 GitHub 仓库 owner/repo：优先 GITHUB_REPO，其次 remote origin。"""
    env = os.getenv("GITHUB_REPO", "").strip()
    if env:
        return env
    try:
        out = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=PROJECT_DIR, capture_output=True, text=True, timeout=10,
        ).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        out = ""
    m = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", out)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    return ""


def _api_request(method, url, token, data=None, content_type=None, raw_body=None):
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "PersonLLMWiki-Release",
    }
    body = raw_body
    if raw_body is None and data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = content_type or "application/json"
    elif content_type:
        headers["Content-Type"] = content_type

    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()
        print(f"[release] API 错误 {e.code}: {err_body}")
        return e.code, None


def publish_release(version, installer_path):
    """推 tag + 创建 GitHub Release + 上传安装包。"""
    token = _token()
    if not token:
        print("[release] 错误: 缺少 GITHUB_TOKEN（或 GH_TOKEN）环境变量")
        print("[release] 获取方式: GitHub → Settings → Developer settings → "
              "Personal access tokens → 勾选 repo scope")
        return False

    repo = _repo()
    if not repo:
        print("[release] 错误: 无法解析 GitHub 仓库（owner/repo），请设置 GITHUB_REPO")
        return False

    if not os.path.isfile(installer_path):
        print(f"[release] 错误: 文件不存在: {installer_path}")
        return False

    tag = f"v{version}"
    filename = os.path.basename(installer_path)

    # 1. 推送当前分支 + tag（tag 缺失时先本地创建）
    print(f"[release] === 发布 {tag} 到 GitHub {repo} ===")

    branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=PROJECT_DIR, capture_output=True, text=True,
    ).stdout.strip()
    print(f"[release] 推送分支 {branch}...")
    result = subprocess.run(
        ["git", "push", "origin", branch],
        cwd=PROJECT_DIR, capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"[release] git push 分支失败: {result.stderr}")
        return False

    print(f"[release] 推送 tag {tag}...")
    subprocess.run(
        ["git", "tag", "-f", tag],
        cwd=PROJECT_DIR, capture_output=True, text=True,
    )
    result = subprocess.run(
        ["git", "push", "origin", tag],
        cwd=PROJECT_DIR, capture_output=True, text=True,
    )
    if result.returncode != 0 and "already exists" not in result.stderr:
        print(f"[release] git push tag 失败: {result.stderr}")
        return False

    # 2. 创建 Release（已存在则复用）
    print("[release] 创建 Release...")
    status, release = _api_request(
        "POST", f"{API_BASE}/repos/{repo}/releases", token,
        data={
            "tag_name": tag,
            "name": tag,
            "body": f"PersonLLMWiki 桌面版 {tag}",
            "draft": False,
            "prerelease": False,
        },
    )
    if status not in (200, 201) or not release:
        print("[release] Release 创建失败，尝试复用已存在的 Release...")
        status, release = _api_request(
            "GET", f"{API_BASE}/repos/{repo}/releases/tags/{tag}", token
        )
        if status != 200 or not release:
            print("[release] 无法找到 Release，退出")
            return False
    else:
        print("[release] Release 已创建")

    release_id = release.get("id")
    if not release_id:
        print("[release] 错误: 未获取到 release id")
        return False

    # 3. 上传安装包
    size_mb = os.path.getsize(installer_path) / 1024 / 1024
    print(f"[release] 上传 {filename} ({size_mb:.1f} MB)...")
    with open(installer_path, "rb") as f:
        raw = f.read()

    upload_url = release.get("upload_url", "").split("{")[0]
    status, asset = _api_request(
        "POST",
        f"{upload_url}?name={urllib.parse.quote(filename)}",
        token,
        content_type="application/octet-stream",
        raw_body=raw,
    )
    if status not in (200, 201) or not asset:
        print("[release] 安装包上传失败")
        return False

    print(f"[release] 上传成功: {asset.get('browser_download_url', '')}")
    release_page = f"https://github.com/{repo}/releases/tag/{tag}"
    print(f"\n[release] 完成！Release 页面: {release_page}")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python packaging/release.py <version> <installer_path>")
        print("示例: python packaging/release.py 1.2.2.002 "
              "release/installer/PersonLLMWiki-Setup-1.2.2.002.exe")
        sys.exit(1)

    version = sys.argv[1]
    installer = sys.argv[2]

    if not publish_release(version, installer):
        sys.exit(1)
