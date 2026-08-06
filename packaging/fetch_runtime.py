"""Python Embedded 运行时下载与引导。

功能：
1. 下载官方 Python embeddable zip（带缓存）
2. 解压到目标目录
3. 启用 site-packages（取消 _pth 注释）
4. 引导 pip（get-pip.py）
5. 安装项目依赖
"""

import os
import sys
import shutil
import zipfile
import subprocess
import urllib.request

PYTHON_VERSION = "3.12.8"
PYTHON_EMBED_URL = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip"
GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"


def _cache_dir():
    """获取下载缓存目录"""
    d = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")), "personllmwiki_build_cache")
    os.makedirs(d, exist_ok=True)
    return d


def fetch_python_embedded(target_dir):
    """下载并解压 Python embeddable 到 target_dir"""
    cache_zip = os.path.join(_cache_dir(), f"python-{PYTHON_VERSION}-embed-amd64.zip")

    if not os.path.isfile(cache_zip):
        print(f"[fetch_runtime] 下载 Python {PYTHON_VERSION} Embedded...")
        urllib.request.urlretrieve(PYTHON_EMBED_URL, cache_zip)
        print(f"[fetch_runtime] 下载完成: {cache_zip}")
    else:
        print(f"[fetch_runtime] 使用缓存: {cache_zip}")

    os.makedirs(target_dir, exist_ok=True)
    with zipfile.ZipFile(cache_zip) as z:
        z.extractall(target_dir)
    print(f"[fetch_runtime] 已解压到 {target_dir}")


def enable_site_packages(runtime_dir):
    """取消 python312._pth 中 import site 的注释，启用 site-packages"""
    pth_file = None
    for f in os.listdir(runtime_dir):
        if f.endswith("._pth"):
            pth_file = os.path.join(runtime_dir, f)
            break
    if not pth_file:
        print("[fetch_runtime] 未找到 ._pth 文件，跳过")
        return

    with open(pth_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    modified = False
    with open(pth_file, "w", encoding="utf-8") as f:
        for line in lines:
            if line.strip() == "#import site":
                f.write("import site\n")
                modified = True
            else:
                f.write(line)

    if modified:
        print(f"[fetch_runtime] 已启用 site-packages: {pth_file}")
    else:
        print(f"[fetch_runtime] site-packages 已启用或格式不符: {pth_file}")


def bootstrap_pip(runtime_dir):
    """用 get-pip.py 引导 pip"""
    python_exe = os.path.join(runtime_dir, "python.exe")
    if not os.path.isfile(python_exe):
        print(f"[fetch_runtime] python.exe 不存在: {python_exe}")
        return False

    # 检测 pip 是否已存在
    result = subprocess.run(
        [python_exe, "-m", "pip", "--version"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print("[fetch_runtime] pip 已存在，跳过引导")
        return True

    get_pip_path = os.path.join(runtime_dir, "get-pip.py")
    print("[fetch_runtime] 下载 get-pip.py...")
    urllib.request.urlretrieve(GET_PIP_URL, get_pip_path)

    print("[fetch_runtime] 引导 pip...")
    result = subprocess.run(
        [python_exe, get_pip_path, "--no-warn-script-location"],
        capture_output=True, text=True
    )
    os.remove(get_pip_path)

    if result.returncode == 0:
        print("[fetch_runtime] pip 引导完成")
        return True
    else:
        print(f"[fetch_runtime] pip 引导失败: {result.stderr}")
        return False


def install_requirements(runtime_dir, requirements_path):
    """安装项目依赖到 runtime 的 site-packages"""
    python_exe = os.path.join(runtime_dir, "python.exe")
    if not os.path.isfile(requirements_path):
        print(f"[fetch_runtime] requirements.txt 不存在: {requirements_path}")
        return False

    print(f"[fetch_runtime] 安装依赖: {requirements_path}")
    result = subprocess.run(
        [python_exe, "-m", "pip", "install",
         "-r", requirements_path,
         "--no-warn-script-location"],
        capture_output=True, text=True
    )

    if result.returncode == 0:
        print("[fetch_runtime] 依赖安装完成")
        return True
    else:
        print(f"[fetch_runtime] 依赖安装失败: {result.stderr[:500]}")
        return False


def build_runtime(target_dir, requirements_path=None):
    """一站式构建：下载 → 解压 → 启用site → 引导pip → 装依赖"""
    fetch_python_embedded(target_dir)
    enable_site_packages(target_dir)
    if not bootstrap_pip(target_dir):
        return False
    if requirements_path:
        if not install_requirements(target_dir, requirements_path):
            return False
    # 验证
    python_exe = os.path.join(target_dir, "python.exe")
    result = subprocess.run([python_exe, "--version"], capture_output=True, text=True)
    print(f"[fetch_runtime] 验证: {result.stdout.strip()}")
    return True


if __name__ == "__main__":
    # 用法: python fetch_runtime.py <target_dir> [requirements.txt]
    if len(sys.argv) < 2:
        print("用法: python fetch_runtime.py <target_dir> [requirements.txt]")
        sys.exit(1)
    target = sys.argv[1]
    req = sys.argv[2] if len(sys.argv) > 2 else None
    ok = build_runtime(target, req)
    sys.exit(0 if ok else 1)
