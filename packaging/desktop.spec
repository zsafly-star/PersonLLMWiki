# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置 — PersonLLMWiki 桌面版

用法：
  cd src
  pyinstaller packaging/desktop.spec --noconfirm
"""

import os
from PyInstaller.building.datastruct import Tree
from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)

block_cipher = None
# spec 位置：packaging/desktop.spec → 项目根 PersonLLMWiki/
# 源码在 src/ 子目录
project_dir = os.path.dirname(os.path.dirname(os.path.abspath(SPEC)))
src_dir = os.path.join(project_dir, 'src')

# F8: 安装版版本标识 app_version.txt（build_desktop.py 打包前写入完整构建号）
_app_version_txt = os.path.join(project_dir, 'app_version.txt')
if not os.path.isfile(_app_version_txt):
    # 直接跑 pyinstaller 时兜底：用 VERSION 内容
    _v = '1.0.0'
    _vf = os.path.join(project_dir, 'VERSION')
    if os.path.isfile(_vf):
        with open(_vf, 'r', encoding='utf-8') as _f:
            _v = _f.read().strip()
    with open(_app_version_txt, 'w', encoding='utf-8') as _f:
        _f.write(_v + '\n')

# 包内数据（1.2.3.005 实测缺两处，安装版会直接崩）：
#  1) jsonschema_specifications/schemas/*.json —— jsonschema（经 fastmcp/mcp）import 时会
#     用 referencing 读这批 metaschema；缺目录 → mcp-launcher 子进程 FileNotFoundError，
#     pdf-mcp / websearch 起不来。
#  2) tzdata —— Windows 没有系统 tz 库，zoneinfo 依赖这个包；缺失时报
#     "No time zone found with key Asia/Shanghai"，定时任务调度器起不来。
_extra_datas = []
for _pkg in ('jsonschema_specifications', 'tzdata'):
    try:
        _extra_datas += collect_data_files(_pkg)
    except Exception as _e:      # 未安装时不要阻断打包
        print(f'[desktop.spec] collect_data_files({_pkg}) 跳过: {_e}')

a = Analysis(
    [os.path.join(src_dir, 'desktop.pyw')],
    pathex=[src_dir],
    binaries=[
        # clr_loader 的 netfx 原生宿主 ClrLoader.dll（clr_loader.ffi.load_netfx 用
        # ffi.dlopen 动态加载，静态分析看不到）。缺失时 PYTHONNET_RUNTIME=netfx 的
        # import clr 会失败，pywebview 的 winforms/edgechromium 后端 except 分支会回退
        # coreclr，而本机无 WindowsDesktop 共享框架 → System.Windows.Forms
        # FileNotFoundException（1.2.3.008 实测）。
        *collect_dynamic_libs('clr_loader'),
    ],
    datas=[
        # 打包 static 和 templates（Flask 渲染需要）
        (os.path.join(src_dir, 'static'), 'static'),
        (os.path.join(src_dir, 'templates'), 'templates'),
        # 模块级模板目录（Flask blueprint template_folder）
        (os.path.join(src_dir, 'modules'), 'modules'),
        # 图标文件（desktop.pyw 托盘/窗口图标）
        (os.path.join(src_dir, 'static', 'img', 'app.ico'), 'static/img'),
        # 安装版版本标识（完整构建号，打进 _internal/app_version.txt）
        (_app_version_txt, '.'),
        # 运行时数据包（见上面 _extra_datas 注释）
        *_extra_datas,
    ],
    hiddenimports=[
        'flask',
        'flask_sqlalchemy',
        'flask_cors',
        'openai',
        'fitz',
        'fastembed',
        'fastmcp',
        'uvicorn',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.http.httptools_impl',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'starlette',
        'sse_starlette',
        'pymupdf',
        'webview',
        'webview.platforms.edgechromium',
        'pystray',
        'PIL',
        'PIL._tkinter_finder',
        # desktop.pyw 依赖
        'common.port_utils',
        'common.tray_manager',
        'common.desktop_prefs',
        # fastmcp 用 __getattr__ 懒加载 FastMCP（fastmcp.server.server），
        # 且 pdf-mcp 子进程通过 runpy.run_path 动态导入，PyInstaller 静态分析看不到，
        # 因此显式收集 fastmcp 全部子模块及其运行时依赖，避免打包后 ImportError。
        *collect_submodules('fastmcp'),
        'packaging',
        'httpx',
        'mcp',
        'pydantic',
        'jsonschema_specifications',
        'referencing',
        # anyio 的 asyncio 后端是"运行时按名字 import"的（anyio._backends._asyncio），
        # 静态分析看不到；漏了会让 MCP 子进程报
        # LookupError: Backend 'asyncio' is not available（1.2.3.005 实测）
        *collect_submodules('anyio'),
        # rich 的 unicode 数据模块是运行时按版本动态 import 的
        # （rich._unicode_data.unicode17-0-0），静态分析看不到；漏了会让 rich
        # 渲染时报 ModuleNotFoundError（1.2.3.008 实测）。
        *collect_submodules('rich._unicode_data'),
    ],
    hookspath=[],
    hooksconfig={},
    # pythonnet 的 .NET Framework 固定在 src/desktop.pyw 顶部设置（setdefault），
    # 不放 runtime hook：实测 runtime hook 未生效（PYZ 缓存命中时不重新编译）。
    runtime_hooks=[],
    excludes=['torch', 'transformers', 'hf_xet'],
    cipher=block_cipher,
    noarchive=False,
)

# 补充 fastmcp 包元数据（importlib.metadata.version 需要）
import site as _site
_sp = _site.getsitepackages()[1]
_tree_fastmcp = Tree(os.path.join(_sp, 'fastmcp-3.4.5.dist-info'), prefix='fastmcp-3.4.5.dist-info')
_tree_fastmcp_slim = Tree(os.path.join(_sp, 'fastmcp_slim-3.4.5.dist-info'), prefix='fastmcp_slim-3.4.5.dist-info')
# 将 Tree 的 TOC 合并到 a.datas
a.datas += _tree_fastmcp
a.datas += _tree_fastmcp_slim

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PersonLLMWiki',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # 无控制台窗口
    icon=os.path.join(src_dir, 'static', 'img', 'app.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='PersonLLMWiki',
)
