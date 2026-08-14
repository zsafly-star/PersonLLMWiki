"""桌面版打包编排脚本。

用法：
  python packaging/build_desktop.py              # 自动递增版本号
  python packaging/build_desktop.py 1.0.0.007    # 指定版本号

流程：
  1. 调用 PyInstaller（用 desktop.spec）打 EXE
  2. 复制 seed/ 到输出目录
  3. 调用 Inno Setup（ISCC.exe）打安装包
  4. 产出到 release/ 目录
"""

import glob
import os
import re
import shutil
import subprocess
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(THIS_DIR)
SRC_DIR = os.path.join(PROJECT_DIR, 'src')
PACKAGING_DIR = THIS_DIR
RELEASE_DIR = os.path.join(PROJECT_DIR, 'release')


def _get_base_version():
    """读取 VERSION 文件获取基础版本号"""
    version_file = os.path.join(PROJECT_DIR, 'VERSION')
    if os.path.isfile(version_file):
        with open(version_file, 'r') as f:
            return f.read().strip()
    return '1.0.0'


def _get_next_build_number(base_version):
    """扫描 installer 目录，返回下一个 build 号（3 位补零）"""
    installer_dir = os.path.join(RELEASE_DIR, 'installer')
    os.makedirs(installer_dir, exist_ok=True)
    
    pattern = re.compile(
        re.escape(f'PersonLLMWiki-Setup-{base_version}.') + r'(\d+)\.exe$')
    max_n = 0
    for f in os.listdir(installer_dir):
        m = pattern.match(f)
        if m:
            n = int(m.group(1))
            if n > max_n:
                max_n = n
    return f'{max_n + 1:03d}'


def auto_version():
    """自动生成下一个版本号"""
    base = _get_base_version()
    build = _get_next_build_number(base)
    return f'{base}.{build}'


def run_pyinstaller():
    """调用 PyInstaller 打包"""
    print("[build] === PyInstaller 打包 ===")
    spec = os.path.join(PACKAGING_DIR, "desktop.spec")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        spec,
        "--noconfirm",
        "--distpath", os.path.join(RELEASE_DIR, "dist"),
        "--workpath", os.path.join(PACKAGING_DIR, "build"),
    ]
    print(f"[build] 运行: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=SRC_DIR)
    if result.returncode != 0:
        print("[build] PyInstaller 失败！")
        sys.exit(1)

    exe_path = os.path.join(RELEASE_DIR, "dist", "PersonLLMWiki", "PersonLLMWiki.exe")
    if not os.path.isfile(exe_path):
        print(f"[build] 未找到产出 EXE: {exe_path}")
        sys.exit(1)
    print(f"[build] EXE 已生成: {exe_path}")


def copy_seed_to_output():
    """将 seed/ 复制到输出目录（EXE 同级，用于首次播种）"""
    print("[build] === 复制 seed/ 到输出目录 ===")
    seed_src = os.path.join(PROJECT_DIR, 'seed')
    seed_dst = os.path.join(RELEASE_DIR, "dist", "PersonLLMWiki", "seed")

    if not os.path.isdir(seed_src):
        print(f"[build] 警告: 未找到 seed 目录: {seed_src}")
        return

    if os.path.isdir(seed_dst):
        print(f"[build] 移除旧 seed: {seed_dst}")
        shutil.rmtree(seed_dst)

    shutil.copytree(seed_src, seed_dst,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    print(f"[build] seed/ 已复制到: {seed_dst}")


def find_iscc():
    """查找 Inno Setup 编译器 ISCC.exe"""
    # 常见安装路径
    candidates = [
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    # 尝试 PATH
    found = shutil.which("ISCC")
    if found:
        return found
    return None


def run_inno_setup(version):
    """调用 Inno Setup 编译安装包"""
    print("[build] === Inno Setup 打包 ===")
    iscc = find_iscc()
    if not iscc:
        print("[build] 错误: 未找到 ISCC.exe，请安装 Inno Setup 6")
        print("[build] 下载地址: https://jrsoftware.org/isdl.php")
        sys.exit(1)

    iss = os.path.join(PACKAGING_DIR, "installer.iss")
    output_dir = os.path.join(RELEASE_DIR, "installer")
    os.makedirs(output_dir, exist_ok=True)

    cmd = [iscc, f"/DAppVersion={version}", iss]
    print(f"[build] 运行: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=PACKAGING_DIR)
    if result.returncode != 0:
        print("[build] Inno Setup 失败！")
        sys.exit(1)

    installer = os.path.join(output_dir, f"PersonLLMWiki-Setup-{version}.exe")
    if not os.path.isfile(installer):
        print(f"[build] 未找到安装包: {installer}")
        sys.exit(1)

    size_mb = os.path.getsize(installer) / 1024 / 1024
    print(f"\n[build] 安装包已生成:")
    print(f"  路径: {installer}")
    print(f"  大小: {size_mb:.1f} MB")
    return installer


if __name__ == "__main__":
    if len(sys.argv) >= 2:
        version = sys.argv[1]
    else:
        version = auto_version()

    print(f"PersonLLMWiki 桌面版打包工具")
    print(f"版本: {version}")
    print()

    run_pyinstaller()
    copy_seed_to_output()
    installer_path = run_inno_setup(version)

    print(f"\n[build] 完成！安装包: {installer_path}")
