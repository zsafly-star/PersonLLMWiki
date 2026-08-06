# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置 — PersonLLMWiki 桌面版

用法：
  cd src
  pyinstaller packaging/desktop.spec --noconfirm
"""

import os

block_cipher = None
# src 目录（spec 文件的上两级：packaging/desktop.spec → src/）
src_dir = os.path.dirname(os.path.dirname(os.path.abspath(SPEC)))

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
        (os.path.join(src_dir, 'static', 'img', 'AIChat.png'), 'static/img'),
    ],
    hiddenimports=[
        'flask',
        'flask_sqlalchemy',
        'flask_cors',
        'openai',
        'fitz',
        'fastembed',
        'fastmcp',
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
    icon=os.path.join(src_dir, 'static', 'img', 'AIChat.png'),
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
