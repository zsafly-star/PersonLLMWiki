"""桌面版打包编排脚本。

用法：
  python packaging/build_desktop.py 1.0.0

流程：
  1. 调用 PyInstaller（用 desktop.spec）打 EXE
  2. 调用 Inno Setup（ISCC.exe）打安装包
  3. 产出到 release/ 目录
"""

import os
import shutil
import subprocess
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(THIS_DIR)
SRC_DIR = os.path.join(PROJECT_DIR, 'src')
PACKAGING_DIR = THIS_DIR
RELEASE_DIR = os.path.join(PROJECT_DIR, 'release')


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


def copy_bin_to_output():
    """将 bin/ 复制到输出目录（EXE 同级，而非 _internal 内）"""
    print("[build] === 复制 bin/ 到输出目录 ===")
    bin_src = os.path.join(SRC_DIR, 'bin')
    bin_dst = os.path.join(RELEASE_DIR, "dist", "PersonLLMWiki", "bin")

    if not os.path.isdir(bin_src):
        print(f"[build] 警告: 未找到 bin 目录: {bin_src}")
        return

    if os.path.isdir(bin_dst):
        print(f"[build] 移除旧 bin: {bin_dst}")
        shutil.rmtree(bin_dst)

    shutil.copytree(bin_src, bin_dst)
    print(f"[build] bin/ 已复制到: {bin_dst}")


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
    if len(sys.argv) < 2:
        print("用法: python build_desktop.py <version>")
        print("示例: python build_desktop.py 1.0.0")
        sys.exit(1)

    version = sys.argv[1]

    print(f"PersonLLMWiki 桌面版打包工具")
    print(f"版本: {version}")
    print()

    run_pyinstaller()
    copy_bin_to_output()
    installer_path = run_inno_setup(version)

    print(f"\n[build] 完成！安装包: {installer_path}")
