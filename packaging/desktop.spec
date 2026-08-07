# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置 — PersonLLMWiki 桌面版

用法：
  cd src
  pyinstaller packaging/desktop.spec --noconfirm
"""

import os
from PyInstaller.building.datastruct import Tree

block_cipher = None
# spec 位置：packaging/desktop.spec → 项目根 PersonLLMWiki/
# 源码在 src/ 子目录
project_dir = os.path.dirname(os.path.dirname(os.path.abspath(SPEC)))
src_dir = os.path.join(project_dir, 'src')

a = Analysis(
    [os.path.join(src_dir, 'desktop.pyw')],
    pathex=[src_dir],
    binaries=[],
    datas=[
        # 打包 static 和 templates（Flask 渲染需要）
        (os.path.join(src_dir, 'static'), 'static'),
        (os.path.join(src_dir, 'templates'), 'templates'),
        # 模块级模板目录（Flask blueprint template_folder）
        (os.path.join(src_dir, 'modules'), 'modules'),
        # 图标文件（desktop.pyw 托盘/窗口图标）
        (os.path.join(src_dir, 'static', 'img', 'app.ico'), 'static/img'),
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
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
