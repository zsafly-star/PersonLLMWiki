"""在线升级检查与执行模块。

用法（命令行）：
  python upgrade_check.py --app-dir <path> --version-file <path> [--versions-url <url>]

退出码：
  0 = 升级成功（或已下载并应用）
  1 = 错误（网络/解压/回滚）
  2 = 已是最新版本
"""

import argparse
import json
import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile

DEFAULT_VERSIONS_URL = "https://raw.githubusercontent.com/your-org/PersonLLMWiki/main/versions.json"
TIMEOUT = 15


def get_current_version(version_file):
    """读取本地版本号"""
    if os.path.isfile(version_file):
        with open(version_file, "r") as f:
            return f.read().strip()
    return "0.0.0"


def fetch_remote_versions(versions_url):
    """获取远程版本清单"""
    try:
        req = urllib.request.Request(versions_url, headers={"User-Agent": "PersonLLMWiki-Updater"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"[Upgrade] 获取版本信息失败: {e}")
        return None


def compare_versions(a, b):
    """比较版本号。返回 1(a>b) / 0(a==b) / -1(a<b)"""
    pa = [int(x) for x in a.split(".")]
    pb = [int(x) for x in b.split(".")]
    for i in range(max(len(pa), len(pb))):
        va = pa[i] if i < len(pa) else 0
        vb = pb[i] if i < len(pb) else 0
        if va > vb:
            return 1
        if va < vb:
            return -1
    return 0


def download_update(url, dest_path):
    """下载更新包"""
    print(f"[Upgrade] 下载 {url}...")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PersonLLMWiki-Updater"})
        with urllib.request.urlopen(req, timeout=300) as resp:
            with open(dest_path, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
        print(f"[Upgrade] 下载完成: {dest_path}")
        return True
    except Exception as e:
        print(f"[Upgrade] 下载失败: {e}")
        return False


def apply_update(zip_path, app_dir, version_file, new_version):
    """应用更新：备份 → 解压 → 清理"""
    backup_dir = app_dir + "_backup"

    # Step 1: 备份
    print(f"[Upgrade] 备份 {app_dir} → {backup_dir}...")
    if os.path.isdir(app_dir):
        if os.path.isdir(backup_dir):
            shutil.rmtree(backup_dir)
        shutil.copytree(app_dir, backup_dir)

    # Step 2: 清空 app_dir 并解压
    try:
        print(f"[Upgrade] 解压更新...")
        if os.path.isdir(app_dir):
            shutil.rmtree(app_dir)
        os.makedirs(app_dir)

        with zipfile.ZipFile(zip_path) as z:
            # 处理 zip 内可能有的顶层目录
            names = z.namelist()
            top_dirs = set(n.split("/")[0] for n in names if "/" in n)

            for name in z.namelist():
                if name.endswith("/"):
                    continue
                # 去掉可能的顶层目录前缀（app/ 或 PersonLLMWiki/）
                rel = name
                for prefix in top_dirs:
                    if name.startswith(prefix + "/"):
                        rel = name[len(prefix) + 1:]
                        break
                if not rel:
                    continue
                dest = os.path.join(app_dir, rel)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with z.open(name) as src, open(dest, "wb") as dst:
                    dst.write(src.read())

        # Step 3: 更新 VERSION
        with open(version_file, "w") as f:
            f.write(new_version)
        print(f"[Upgrade] 版本更新为 {new_version}")

        # Step 4: 清理备份和临时文件
        if os.path.isdir(backup_dir):
            shutil.rmtree(backup_dir)
        os.remove(zip_path)
        print("[Upgrade] 升级完成")
        return True

    except Exception as e:
        print(f"[Upgrade] 升级失败: {e}")
        # 回滚
        print("[Upgrade] 正在回滚...")
        if os.path.isdir(app_dir):
            shutil.rmtree(app_dir)
        if os.path.isdir(backup_dir):
            shutil.move(backup_dir, app_dir)
        print("[Upgrade] 已回滚到旧版本")
        return False


def main():
    parser = argparse.ArgumentParser(description="PersonLLMWiki 在线升级")
    parser.add_argument("--app-dir", required=True, help="app 代码目录路径")
    parser.add_argument("--version-file", required=True, help="VERSION 文件路径")
    parser.add_argument("--versions-url", default=DEFAULT_VERSIONS_URL, help="版本清单 URL")
    args = parser.parse_args()

    current = get_current_version(args.version_file)
    print(f"[Upgrade] 当前版本: {current}")

    data = fetch_remote_versions(args.versions_url)
    if not data:
        sys.exit(1)

    latest = data.get("latest", "0.0.0")
    print(f"[Upgrade] 最新版本: {latest}")

    if compare_versions(latest, current) <= 0:
        print("[Upgrade] 已是最新版本")
        sys.exit(2)

    info = data.get("versions", {}).get(latest)
    if not info:
        print(f"[Upgrade] 版本清单中无 {latest} 的详细信息")
        sys.exit(1)

    print(f"[Upgrade] 更新内容: {info.get('notes', '')}")
    print(f"[Upgrade] 包大小: {info.get('size_mb', '?')}MB")

    # 下载
    tmp_dir = tempfile.mkdtemp(prefix="personllmwiki_update_")
    zip_path = os.path.join(tmp_dir, f"update-{latest}.zip")
    if not download_update(info["url"], zip_path):
        shutil.rmtree(tmp_dir, ignore_errors=True)
        sys.exit(1)

    # 应用
    if not apply_update(zip_path, args.app_dir, args.version_file, latest):
        shutil.rmtree(tmp_dir, ignore_errors=True)
        sys.exit(1)

    shutil.rmtree(tmp_dir, ignore_errors=True)
    sys.exit(0)


if __name__ == "__main__":
    main()
