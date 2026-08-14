"""构建发布包。

用法：
  python build_release.py 1.0.0            # 全量包（含 runtime）
  python build_release.py 1.0.0 --update   # 增量包（仅 app 代码）

产出：dist/PersonLLMWiki-{version}[-update].zip
"""

import os
import shutil
import sys

# 确保能导入 fetch_runtime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_runtime import build_runtime

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(THIS_DIR)      # PersonLLMWiki/
SRC_DIR = os.path.join(PROJECT_DIR, "src")    # PersonLLMWiki/src/
BUILD_DIR = os.path.join(THIS_DIR, "build")
DIST_DIR = os.path.join(THIS_DIR, "dist")

EXCLUDE_PATTERNS = {
    "__pycache__", "resource", "build", "dist", "bin",
    ".env", ".env.local", ".env.example"
}


def _ignore_patterns(directory, contents):
    """shutil.copytree 的 ignore 回调"""
    ignored = set()
    for item in contents:
        if item in EXCLUDE_PATTERNS:
            ignored.add(item)
        elif item.endswith(".pyc"):
            ignored.add(item)
        elif item.startswith(".") and item not in (".gitignore",):
            ignored.add(item)
    return ignored


def copy_app_code(src_root, target_app_dir):
    """复制应用代码到 target_app_dir"""
    print(f"[build] 复制代码: {src_root} → {target_app_dir}")
    shutil.copytree(src_root, target_app_dir, ignore=_ignore_patterns)


def copy_bat_scripts(target_root):
    """复制 bat 脚本"""
    scripts_dir = os.path.join(THIS_DIR, "scripts")
    for f in os.listdir(scripts_dir):
        if f.endswith(".bat"):
            shutil.copy2(os.path.join(scripts_dir, f), target_root)
    print(f"[build] 已复制 bat 脚本")


def copy_env_example(target_root):
    """复制 .env.example"""
    src = os.path.join(SRC_DIR, ".env.example")
    if os.path.isfile(src):
        shutil.copy2(src, target_root)


def build_full(version):
    """构建全量包（含 Python 运行时）"""
    target_name = f"PersonLLMWiki-{version}"
    target = os.path.join(BUILD_DIR, target_name)

    # 清理旧构建
    if os.path.isdir(target):
        shutil.rmtree(target)
    os.makedirs(target)

    # 1. Python 运行时
    print(f"\n[build] === 构建 Python 运行时 ===")
    runtime_dir = os.path.join(target, "runtime")
    req_path = os.path.join(SRC_DIR, "requirements.txt")
    ok = build_runtime(runtime_dir, req_path)
    if not ok:
        print("[build] Python 运行时构建失败！")
        sys.exit(1)

    # 2. 应用代码（bin/ 被 EXCLUDE_PATTERNS 排除，单独复制到 app/bin）
    print(f"\n[build] === 复制应用代码 ===")
    copy_app_code(SRC_DIR, os.path.join(target, "app"))

    # 2b. 复制 bin/（MCP 二进制服务，体积较大，但全量包需要）
    bin_src = os.path.join(SRC_DIR, "bin")
    bin_dst = os.path.join(target, "app", "bin")
    if os.path.isdir(bin_src):
        print(f"[build] 复制 bin/ (MCP 二进制)...")
        shutil.copytree(bin_src, bin_dst)

    # 2c. 复制 seed/（首次播种数据，包含 Skills 和 MCP 配置）
    seed_src = os.path.join(PROJECT_DIR, "seed")
    seed_dst = os.path.join(target, "seed")
    if os.path.isdir(seed_src):
        print(f"[build] 复制 seed/ (播种数据: skills + mcp)...")
        shutil.copytree(seed_src, seed_dst,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    else:
        print(f"[build] ⚠ seed/ 目录不存在，跳过: {seed_src}")

    # 3. bat 脚本
    copy_bat_scripts(target)

    # 4. .env.example
    copy_env_example(target)

    # 5. VERSION
    with open(os.path.join(target, "VERSION"), "w") as f:
        f.write(version)

    # 6. 用户指南
    guide_src = os.path.join(SRC_DIR, "doc", "用户使用指南.md")
    if os.path.isfile(guide_src):
        shutil.copy2(guide_src, os.path.join(target, "README-用户指南.md"))

    # 7. 创建空目录占位
    for d in ["resource", os.path.join("resource", "article"),
              os.path.join("resource", "img"),
              os.path.join("resource", "attachments"),
              os.path.join("resource", "wiki"), "logs"]:
        os.makedirs(os.path.join(target, d), exist_ok=True)

    # 8. 打包 zip
    print(f"\n[build] === 打包 zip ===")
    os.makedirs(DIST_DIR, exist_ok=True)
    zip_base = os.path.join(DIST_DIR, target_name)
    shutil.make_archive(zip_base, "zip", BUILD_DIR, target_name)
    zip_path = zip_base + ".zip"

    # 统计大小
    size_mb = os.path.getsize(zip_path) / 1024 / 1024
    print(f"\n[build] 全量包已生成:")
    print(f"  路径: {zip_path}")
    print(f"  大小: {size_mb:.1f} MB")
    return zip_path


def build_update(version):
    """构建增量包（app/ 代码 + seed/ 播种数据）。

    解压到安装根目录后覆盖 app/ 和 seed/，用户数据（resource/）不受影响。
    """
    target_name = f"PersonLLMWiki-{version}-update"
    target = os.path.join(BUILD_DIR, target_name)

    if os.path.isdir(target):
        shutil.rmtree(target)
    os.makedirs(target)

    # app/ 代码
    copy_app_code(SRC_DIR, os.path.join(target, "app"))

    # seed/ 播种数据（增量包也需更新 Skills 和 MCP 配置）
    seed_src = os.path.join(PROJECT_DIR, "seed")
    seed_dst = os.path.join(target, "seed")
    if os.path.isdir(seed_src):
        shutil.copytree(seed_src, seed_dst,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        print(f"[build] 已包含 seed/ 播种数据")

    # VERSION
    with open(os.path.join(target, "VERSION"), "w") as f:
        f.write(version)

    # 打包 zip
    os.makedirs(DIST_DIR, exist_ok=True)
    zip_base = os.path.join(DIST_DIR, target_name)
    shutil.make_archive(zip_base, "zip", BUILD_DIR, target_name)

    # 统计大小
    size_mb = os.path.getsize(zip_base + ".zip") / 1024 / 1024
    print(f"\n[build] 增量包已生成:")
    print(f"  路径: {zip_base}.zip")
    print(f"  大小: {size_mb:.1f} MB")
    return zip_base + ".zip"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python build_release.py <version> [--update]")
        print("  无 --update: 全量包（含 Python 运行时）")
        print("  有 --update: 增量包（仅 app 代码）")
        sys.exit(1)

    version = sys.argv[1]
    is_update = "--update" in sys.argv

    print(f"PersonLLMWiki 打包工具")
    print(f"版本: {version}")
    print(f"类型: {'增量包' if is_update else '全量包'}")
    print()

    if is_update:
        build_update(version)
    else:
        build_full(version)
