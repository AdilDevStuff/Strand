# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification file for building Strand desktop client."""

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collect all submodules and dynamic data for core packages
hidden_imports = [
    "_cffi_backend",
    "cffi",
    "pygit2",
    "PySide6",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "unidiff",
    "pygments",
    "pygments.lexers",
    "pygments.formatters",
    "core",
    "services",
    "ui",
]
hidden_imports += collect_submodules("pygit2")
hidden_imports += collect_submodules("pygments.lexers")
hidden_imports += collect_submodules("pygments.styles")

datas = []
datas += collect_data_files("pygit2")
datas += collect_data_files("pygments")
if os.path.isdir("resources"):
    datas.append(("resources", "resources"))
if os.path.isfile("/etc/ssl/certs/ca-certificates.crt"):
    datas.append(("/etc/ssl/certs/ca-certificates.crt", "resources"))

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=["resources/pygit2_ssl.py"],
    excludes=["tkinter", "matplotlib", "scipy"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="strand",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Strand",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Strand.app",
        icon=None,
        bundle_identifier="com.strand.gitclient",
    )
