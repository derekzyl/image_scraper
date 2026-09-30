# -*- mode: python ; coding: utf-8 -*-
"""Bundle the receipt app so it can be opened without installing Python."""

from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = [
    "app",
    "extractor",
    "csv_export",
    "PIL",
    "numpy",
    "yaml",
    "shapely",
    "pyclipper",
    "openpyxl",
]

for package in (
    "customtkinter",
    "tkinterdnd2",
    "rapidocr_onnxruntime",
    "onnxruntime",
    "cv2",
    "shapely",
):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ReceiptExtractor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ReceiptExtractor",
)
