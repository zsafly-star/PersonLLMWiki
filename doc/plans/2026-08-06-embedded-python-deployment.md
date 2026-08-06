# Embedded Python 免安装分发 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 PersonLLMWiki 打包为非技术人员可"解压即用、双击启动、一键升级"的 Windows 分发包

**Architecture:** 使用 Python Embedded 运行时（官方免安装版）随项目分发，通过 bat 脚本控制启动/停止/升级，`runtime/`（Python）与 `app/`（代码）与 `resource/`（数据）三层目录分离，升级时仅覆盖 `app/`。

**Tech Stack:** Python 3.12 Embedded (Windows x64)、pip、batch scripts、Flask

---

## File Structure

实施完成后的目录结构：

```
PersonLLMWiki/src/
├── packaging/                          ← 新增：开发者打包工具
│   ├── fetch_runtime.py                ← Python 运行时下载与引导
│   ├── build_release.py                ← 打包脚本（全量/增量）
│   └── scripts/                        ← 用户侧 bat 脚本模板
│       ├── 启动.bat
│       ├── 停止.bat
│       ├── 首次安装.bat
│       └── 升级.bat
├── common/
│   ├── self_update.py                  ← 修改：适配 embedded 模式
│   └── upgrade_check.py                ← 新增：在线升级检查模块
├── config.py                           ← 修改：.env 路径适配
├── app.py                              ← 修改：端口/启动模式从环境变量读取
├── .env.example                        ← 新增：环境变量示例
└── VERSION                             ← 新增：版本文件
```

分发包产出（用户拿到的东西）：

```
PersonLLMWiki-v1.0.0/
├── runtime/             ← Python 运行时（~30MB）
├── app/                 ← 应用代码（升级时覆盖）
├── resource/            ← 用户数据（升级时保留）
├── logs/                ← 日志目录
├── .env                 ← 用户配置
├── VERSION
├── 启动.bat
├── 停止.bat
├── 首次安装.bat
├── 升级.bat
└── README-用户指南.txt
```

---

## Task 1: 创建 packaging 目录结构与 fetch_runtime.py

**Files:**
- Create: `packaging/__init__.py`
- Create: `packaging/fetch_runtime.py`

- [ ] **Step 1: 创建 packaging 包**

创建 `packaging/__init__.py`（空文件，使其成为 Python 包）。

- [ ] **Step 2: 编写 fetch_runtime.py**

```python
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
```

- [ ] **Step 3: 验证 fetch_runtime.py 可独立运行**

Run: `python packaging/fetch_runtime.py /tmp/test_runtime requirements.txt`
Expected: 下载 Python → 解压 → 启用 site → 引导 pip → 装依赖，最终打印 Python 版本

- [ ] **Step 4: Commit**

```bash
git add packaging/__init__.py packaging/fetch_runtime.py
git commit -m "feat: add Python Embedded runtime fetcher for packaging"
```

---

## Task 2: 创建用户侧 bat 脚本模板

**Files:**
- Create: `packaging/scripts/启动.bat`
- Create: `packaging/scripts/停止.bat`
- Create: `packaging/scripts/首次安装.bat`
- Create: `packaging/scripts/升级.bat`

- [ ] **Step 1: 编写 启动.bat**

```bat
@echo off
chcp 65001 >nul
title PersonLLMWiki
cd /d "%~dp0"

set PORT=5000
if defined PERSONLLMWIKI_PORT set PORT=%PERSONLLMWIKI_PORT%

REM 端口检测：已运行则直接打开浏览器
netstat -ano | findstr ":%PORT% " | findstr "LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo PersonLLMWiki 已在运行，正在打开浏览器...
    start http://127.0.0.1:%PORT%
    timeout /t 3 /nobreak >nul
    exit /b 0
)

echo ════════════════════════════════════════
echo   PersonLLMWiki 启动中...
echo   浏览器将自动打开 http://127.0.0.1:%PORT%
echo   关闭此窗口即可停止服务
echo ════════════════════════════════════════
echo.

REM 设置环境变量
set RESOURCE_BASE_PATH=%CD%\resource
set PYTHONPATH=%CD%\app
set PORT=%PORT%

REM 创建日志目录
if not exist "logs" mkdir "logs"

REM 延迟打开浏览器
start /b cmd /c "timeout /t 3 /nobreak >nul && start http://127.0.0.1:%PORT%"

REM 启动 Flask（日志同时输出到控制台和文件）
cd /d "%~dp0\app"
"%~dp0\runtime\python.exe" app.py 2>&1
```

- [ ] **Step 2: 编写 停止.bat**

```bat
@echo off
chcp 65001 >nul
title 停止 PersonLLMWiki
cd /d "%~dp0"

set PORT=5000
if defined PERSONLLMWIKI_PORT set PORT=%PERSONLLMWIKI_PORT%

echo 正在停止 PersonLLMWiki (端口 %PORT%)...
set FOUND=0
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do (
    echo 停止进程 PID: %%a
    taskkill /PID %%a /F >nul 2>&1
    set FOUND=1
)
if "%FOUND%"=="0" (
    echo 未发现正在运行的 PersonLLMWiki。
) else (
    echo PersonLLMWiki 已停止。
)
timeout /t 2 /nobreak >nul
```

- [ ] **Step 3: 编写 首次安装.bat**

```bat
@echo off
chcp 65001 >nul
title PersonLLMWiki 首次安装
cd /d "%~dp0"

echo ════════════════════════════════════════
echo   PersonLLMWiki 首次安装
echo ════════════════════════════════════════
echo.

REM Step 1: 检测 runtime
echo [1/5] 检查 Python 运行时...
if not exist "runtime\python.exe" (
    echo.
    echo [错误] 未找到 runtime\python.exe
    echo 请确保完整下载了安装包，或联系提供者。
    echo.
    pause
    exit /b 1
)
echo       OK

REM Step 2: 检测依赖完整性
echo [2/5] 检查依赖...
runtime\python.exe -c "import flask, openai, fitz, fastembed" 2>nul
if errorlevel 1 (
    echo       依赖缺失，正在安装...
    runtime\python.exe -m pip install -r app\requirements.txt --no-warn-script-location
    if errorlevel 1 (
        echo       [错误] 依赖安装失败，请检查网络连接。
        pause
        exit /b 1
    )
) else (
    echo       OK
)

REM Step 3: 创建数据目录
echo [3/5] 创建数据目录...
for %%d in (resource\instance resource\article resource\img resource\attachments resource\wiki logs) do (
    if not exist "%%d" mkdir "%%d"
)
echo       OK

REM Step 4: 创建 .env（如不存在）
echo [4/5] 检查配置文件...
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo       已从模板创建 .env
    ) else (
        echo RESOURCE_BASE_PATH=%CD%\resource> .env
        echo       已创建默认 .env
    )
) else (
    echo       .env 已存在
)

REM Step 5: 创建桌面快捷方式
echo [5/5] 创建桌面快捷方式...
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $desktop = [Environment]::GetFolderPath('Desktop'); $s = $ws.CreateShortcut(\"$desktop\PersonLLMWiki.lnk\"); $s.TargetPath = '%CD%\启动.bat'; $s.WorkingDirectory = '%CD%'; $s.IconLocation = '%CD%\app\static\img\AIChat.png'; $s.Description = 'PersonLLMWiki 个人知识管理'; $s.Save()"
echo       OK

echo.
echo ════════════════════════════════════════
echo   ✓ 安装完成！
echo   双击桌面 "PersonLLMWiki" 图标即可启动
echo ════════════════════════════════════════
echo.
pause
```

- [ ] **Step 4: 编写 升级.bat**

```bat
@echo off
chcp 65001 >nul
title PersonLLMWiki 升级
cd /d "%~dp0"

set VERSIONS_URL=https://raw.githubusercontent.com/your-org/PersonLLMWiki/main/versions.json

echo ════════════════════════════════════════
echo   PersonLLMWiki 在线升级
echo ════════════════════════════════════════
echo.

REM Step 1: 停止服务
echo [1/4] 停止服务...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5000 " ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)
timeout /t 2 /nobreak >nul

REM Step 2: 检查并执行升级（Python 脚本返回 exit code）
echo [2/4] 检查并下载更新...
runtime\python.exe "%~dp0\app\common\upgrade_check.py" --versions-url "%VERSIONS_URL%" --app-dir "%~dp0\app" --version-file "%~dp0\VERSION"
if errorlevel 2 (
    echo.
    echo 已是最新版本，无需升级。
    pause
    exit /b 0
)
if errorlevel 1 (
    echo.
    echo 升级失败，请检查网络连接或稍后重试。
    pause
    exit /b 1
)

REM Step 3: 依赖更新（如有变化）
echo [3/4] 检查依赖...
runtime\python.exe -m pip install -r app\requirements.txt --quiet --no-warn-script-location 2>nul
echo       依赖检查完成

REM Step 4: 完成
echo [4/4] 完成！
echo.
echo ════════════════════════════════════════
echo   ✓ 升级完成！双击"启动.bat"开始使用
echo ════════════════════════════════════════
pause
```

- [ ] **Step 5: Commit**

```bash
git add packaging/scripts/
git commit -m "feat: add user-facing bat scripts (start/stop/install/upgrade)"
```

---

## Task 3: 适配 config.py 支持 .env 路径

**Files:**
- Modify: `config.py:1-8`
- Create: `.env.example`

- [ ] **Step 1: 修改 config.py 的 .env 加载逻辑**

当前 `config.py` 第 4 行 `load_dotenv()` 只从当前工作目录查找 `.env`。修改为从项目根目录和上级目录查找，适配 embedded 部署时 `.env` 在 `app/` 外层的情况。

将 `config.py` 开头改为：

```python
import os
from dotenv import load_dotenv

# 查找 .env：依次检查 app 同级目录（embedded 部署）、app 上级、当前目录
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
_DEFAULT_RESOURCE_PATH = os.path.join(_PROJECT_ROOT, 'resource')

# 尝试多个位置的 .env
for _env_candidate in [
    os.path.join(_PROJECT_ROOT, '.env'),          # embedded: app/../.env
    os.path.join(_THIS_DIR, '.env'),               # 开发模式: src/.env
    os.path.join(os.getcwd(), '.env'),             # 当前目录
]:
    if os.path.isfile(_env_candidate):
        load_dotenv(_env_candidate)
        break
```

- [ ] **Step 2: 创建 .env.example**

```ini
# PersonLLMWiki 环境变量配置
# 首次安装时会自动复制为 .env，通常无需手动修改

# 数据存储路径（留空使用默认值 ../resource）
# RESOURCE_BASE_PATH=

# 服务端口（默认 5000）
# PORT=5000

# 实例模式：single（单机）/ personal（个人版可同步公共库）/ public（公共版）
INSTANCE_MODE=single

# --- 以下为可选配置，也可在设置页 UI 中配置 ---

# OpenAI API
# OPENAI_API_KEY=sk-xxx
# OPENAI_BASE_URL=https://api.openai.com/v1

# 公共库同步（personal 模式）
# COMMON_GIT_REPO=
# AUTHOR_NAME=
```

- [ ] **Step 3: 验证 config.py 开发模式仍正常**

Run: `python -c "from config import Config; print(Config.RESOURCE_BASE_PATH)"`
Expected: 打印 resource 路径，不报错

- [ ] **Step 4: Commit**

```bash
git add config.py .env.example
git commit -m "fix: config.py .env path resolution for embedded deployment"
```

---

## Task 4: 适配 app.py 启动参数

**Files:**
- Modify: `app.py:211-212`

- [ ] **Step 1: 修改 app.py 的 `__main__` 启动块**

当前 `app.py` 第 211-212 行：

```python
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
```

修改为从环境变量读取，并默认关闭 debug 模式（embedded 部署不需要 reloader）：

```python
if __name__ == '__main__':
    import os
    port = int(os.getenv('PORT', '5000'))
    debug = os.getenv('FLASK_DEBUG', '0') == '1'
    host = os.getenv('FLASK_HOST', '127.0.0.1')
    app.run(host=host, port=port, debug=debug, threaded=True)
```

注意：
- `host` 默认改为 `127.0.0.1`（仅本机访问，更安全）
- `debug` 默认关闭（生产模式），开发时可通过 `.env` 中 `FLASK_DEBUG=1` 开启

- [ ] **Step 2: 验证开发模式正常**

Run: `set FLASK_DEBUG=1 && python app.py`
Expected: Flask 以 debug 模式启动，端口 5000

Run: `python app.py`
Expected: Flask 以非 debug 模式启动

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "fix: app.py startup params from env vars (port/host/debug)"
```

---

## Task 5: 创建 common/upgrade_check.py 在线升级模块

**Files:**
- Create: `common/upgrade_check.py`

- [ ] **Step 1: 编写 upgrade_check.py**

```python
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
```

- [ ] **Step 2: 验证脚本可执行（版本检查）**

Run: `python common/upgrade_check.py --app-dir . --version-file VERSION --versions-url https://example.com/test.json`
Expected: 打印版本信息，因 URL 不可达而 exit 1（网络错误），不崩溃

- [ ] **Step 3: Commit**

```bash
git add common/upgrade_check.py
git commit -m "feat: add online upgrade check module (download/backup/apply/rollback)"
```

---

## Task 6: 适配 self_update.py 支持 embedded 模式

**Files:**
- Modify: `common/self_update.py`

- [ ] **Step 1: 修改 self_update.py**

当前 `self_update.py` 使用系统 `git` 和 `pip`，embedded 模式下需要使用 runtime 内的 pip。增加 embedded 模式检测：

在 `self_update.py` 中，修改 `_check_and_install_deps()` 函数，在 pip 调用前检测 embedded python：

```python
def _get_pip_command(req_path):
    """获取 pip 安装命令，优先使用当前 Python 的 -m pip"""
    return [sys.executable, "-m", "pip", "install", "-r", req_path, "--no-warn-script-location"]


def _is_embedded_mode():
    """检测是否运行在 embedded 模式（通过检查 sys.executable 路径是否含 runtime）"""
    return "runtime" in os.path.dirname(sys.executable).lower()
```

然后在 `self_update()` 函数中，embedded 模式下跳过 git pull（embedded 部署不包含 .git 目录）：

```python
def self_update():
    """执行自更新（启动时调用）"""
    logs = []

    # Step 1: git pull 代码（仅非 embedded 模式）
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if os.path.isdir(os.path.join(project_root, '.git')) and not _is_embedded_mode():
        rc, out, err = _run_git(['pull', '--ff-only'], project_root)
        if rc == 0:
            if 'Already up to date' in out or '已经是最新的' in out:
                logs.append('代码：已是最新')
            else:
                logs.append(f'代码：已更新 ({out[:100]})')
        else:
            logs.append(f'代码：git pull 失败 ({err[:100]})')
    else:
        logs.append('代码：Embedded 模式或非 Git 仓库，跳过 git pull')

    # Step 2: 检测并安装依赖
    ok, msg = _check_and_install_deps()
    logs.append(f'依赖：{msg}')

    return logs
```

同时修改 `_check_and_install_deps()` 中的 pip 调用，将 `['pip', 'install', ...]` 改为 `_get_pip_command(req_path)`。

需要在文件头添加 `import sys`（如果尚未导入）。

- [ ] **Step 2: 验证开发模式 git pull 仍工作**

Run: `python -c "from common.self_update import self_update; print(self_update())"`
Expected: 打印 `['代码：...'（git pull 结果）, '依赖：...']`

- [ ] **Step 3: Commit**

```bash
git add common/self_update.py
git commit -m "fix: self_update.py supports embedded mode (skip git, use sys.executable pip)"
```

---

## Task 7: 创建 build_release.py 打包脚本

**Files:**
- Create: `packaging/build_release.py`

- [ ] **Step 1: 编写 build_release.py**

```python
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
SRC_DIR = os.path.dirname(THIS_DIR)          # PersonLLMWiki/src/
BUILD_DIR = os.path.join(THIS_DIR, "build")
DIST_DIR = os.path.join(THIS_DIR, "dist")

EXCLUDE_PATTERNS = {
    ".git", "__pycache__", ".vscode", "node_modules",
    "resource", "build", "dist", "packaging",
    ".env", "dev.ps1", ".env.local"
}


def _ignore_patterns(directory, contents):
    """shutil.copytree 的 ignore 回调"""
    ignored = set()
    for item in contents:
        if item in EXCLUDE_PATTERNS:
            ignored.add(item)
        elif item.endswith(".pyc"):
            ignored.add(item)
        elif item.startswith("."):
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

    # 2. 应用代码
    print(f"\n[build] === 复制应用代码 ===")
    copy_app_code(SRC_DIR, os.path.join(target, "app"))

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
    for d in ["resource", "resource\\instance", "resource\\article",
              "resource\\img", "resource\\attachments", "resource\\wiki", "logs"]:
        os.makedirs(os.path.join(target, d), exist_ok=True)

    # 8. 打包 zip
    print(f"\n[build] === 打包 zip ===")
    os.makedirs(DIST_DIR, exist_ok=True)
    zip_base = os.path.join(DIST_DIR, target_name)
    shutil.make_archive(zip_base, "zip", BUILD_DIR, target_name)
    zip_path = zip_base + ".zip"

    # 统计大小
    size_mb = os.path.getsize(zip_path) / 1024 / 1024
    print(f"\n[build] ✓ 全量包已生成:")
    print(f"  路径: {zip_path}")
    print(f"  大小: {size_mb:.1f} MB")
    return zip_path


def build_update(version):
    """构建增量包（仅 app 代码）"""
    target_name = f"PersonLLMWiki-{version}-update"
    target = os.path.join(BUILD_DIR, target_name)

    if os.path.isdir(target):
        shutil.rmtree(target)
    os.makedirs(target)

    # 仅 app 代码
    copy_app_code(SRC_DIR, target)

    # VERSION
    with open(os.path.join(target, "VERSION"), "w") as f:
        f.write(version)

    # 打包 zip
    os.makedirs(DIST_DIR, exist_ok=True)
    zip_base = os.path.join(DIST_DIR, target_name)
    shutil.make_archive(zip_base, "zip", target, ".")

    # 清理临时目录
    shutil.rmtree(target)

    zip_path = zip_base + ".zip"
    size_mb = os.path.getsize(zip_path) / 1024 / 1024
    print(f"\n[build] ✓ 增量包已生成:")
    print(f"  路径: {zip_path}")
    print(f"  大小: {size_mb:.1f} MB")
    return zip_path


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
```

- [ ] **Step 2: 验证脚本 dry-run**

Run: `python packaging/build_release.py 0.0.1-test --update`
Expected: 生成 `dist/PersonLLMWiki-0.0.1-test-update.zip`（仅含 app 代码，约几 MB）

- [ ] **Step 3: Commit**

```bash
git add packaging/build_release.py
git commit -m "feat: add build_release.py for full/update package creation"
```

---

## Task 8: 创建 VERSION 文件

**Files:**
- Create: `VERSION`

- [ ] **Step 1: 创建 VERSION 文件**

```
1.0.0
```

- [ ] **Step 2: Commit**

```bash
git add VERSION
git commit -m "feat: add VERSION file for upgrade tracking"
```

---

## Task 9: 创建 versions.json 版本清单模板

**Files:**
- Create: `packaging/versions.json.template`

- [ ] **Step 1: 编写版本清单模板**

```json
{
    "latest": "1.0.0",
    "versions": {
        "1.0.0": {
            "url": "https://your-server.com/personllmwiki/PersonLLMWiki-1.0.0-update.zip",
            "date": "2026-08-06",
            "notes": "首个正式发布版本",
            "min_runtime": "1.0.0",
            "size_mb": 15
        }
    }
}
```

- [ ] **Step 2: Commit**

```bash
git add packaging/versions.json.template
git commit -m "docs: add versions.json template for upgrade server"
```

---

## Task 10: 端到端验证

**Files:**
- 无新文件，仅验证

- [ ] **Step 1: 执行全量打包**

Run: `python packaging/build_release.py 1.0.0`
Expected: 生成 `dist/PersonLLMWiki-1.0.0.zip`（含 runtime + app + bat 脚本）

- [ ] **Step 2: 解压并模拟首次安装**

将 `dist/PersonLLMWiki-1.0.0.zip` 解压到临时目录，双击 `首次安装.bat`
Expected: 创建数据目录、桌面快捷方式

- [ ] **Step 3: 启动验证**

双击桌面快捷方式或 `启动.bat`
Expected: 浏览器自动打开 http://127.0.0.1:5000，页面正常加载

- [ ] **Step 4: 执行增量升级包**

Run: `python packaging/build_release.py 1.0.1 --update`
Expected: 生成增量包 zip

将增量包上传到测试服务器，更新 `versions.json`，然后双击 `升级.bat`
Expected: 自动下载、备份、更新代码，VERSION 变为 1.0.1

- [ ] **Step 5: 验证升级后启动正常**

双击 `启动.bat`
Expected: 浏览器打开，功能正常，数据未丢失

- [ ] **Step 6: Commit 所有验证通过的改动**

```bash
git add -A
git commit -m "test: end-to-end verification of embedded deployment"
```

---

## Self-Review

### Spec coverage 检查

| 方案文档章节 | 对应 Task | 状态 |
|-------------|----------|------|
| §3 目标目录结构 | Task 2, 7 | ✅ |
| §4 安装流程（fetch_runtime + 首次安装.bat） | Task 1, 2 | ✅ |
| §5 启动流程（启动.bat / 停止.bat） | Task 2, 4 | ✅ |
| §6 升级流程（upgrade_check.py + 升级.bat） | Task 2, 5 | ✅ |
| §7 .env 配置 | Task 3 | ✅ |
| §8 config.py 适配 | Task 3 | ✅ |
| §9 打包脚本 | Task 7 | ✅ |
| self_update.py 适配 | Task 6 | ✅ |
| VERSION 机制 | Task 8 | ✅ |
| 版本清单 | Task 9 | ✅ |
| 端到端验证 | Task 10 | ✅ |

### Placeholder 检查

- `versions.json.template` 中的 URL 需替换为实际服务器地址 → 已在文档中注明
- `build_release.py` 中排除的 `.env` 是正确的（用户配置不打包）
- 所有 bat 脚本均使用 `%~dp0` 确保路径无关

### Type consistency 检查

- `build_runtime()` 在 `fetch_runtime.py` 和 `build_release.py` 中签名一致
- `upgrade_check.py` 的 exit code 与 `升级.bat` 中的 `errorlevel` 判断一致（0=成功, 1=失败, 2=已最新）
- `VERSION` 文件格式为纯版本号字符串，`get_current_version()` 和 `compare_versions()` 一致
