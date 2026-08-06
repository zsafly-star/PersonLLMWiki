"""桌面版打包编排脚本。

用法：
  python packaging/build_desktop.py 1.0.0

流程：
  1. 调用 PyInstaller（用 desktop.spec）打 EXE
  2. 调用 Inno Setup（ISCC.exe）打安装包
  3. 产出 PersonLLMWiki-Setup-{version}.exe
"""

import os
import shutil
import subprocess
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(THIS_DIR)
PACKAGING_DIR = THIS_DIR


def run_pyinstaller():
    """调用 PyInstaller 打包"""
    print("[build] === PyInstaller 打包 ===")
    spec = os.path.join(PACKAGING_DIR, "desktop.spec")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        spec,
        "--noconfirm",
        "--distpath", os.path.join(PACKAGING_DIR, "dist"),
        "--workpath", os.path.join(PACKAGING_DIR, "build"),
    ]
    print(f"[build] 运行: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=SRC_DIR)
    if result.returncode != 0:
        print("[build] PyInstaller 失败！")
        sys.exit(1)

    exe_path = os.path.join(PACKAGING_DIR, "dist", "PersonLLMWiki", "PersonLLMWiki.exe")
    if not os.path.isfile(exe_path):
        print(f"[build] 未找到产出 EXE: {exe_path}")
        sys.exit(1)
    print(f"[build] EXE 已生成: {exe_path}")


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
    output_dir = os.path.join(PACKAGING_DIR, "installer_output")
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
    installer_path = run_inno_setup(version)

    print(f"\n[build] 完成！安装包: {installer_path}")
