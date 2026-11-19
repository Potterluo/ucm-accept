# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller one-dir 打包配置。

构建机需先安装 ucm-accept[gui] 与 evalscope[perf,service(,agentx)]。
PyInstaller 不能交叉编译：Windows 产物请在 Windows 构建机生成，ARM64 请在 ARM64 构建机生成。
"""

from pathlib import Path
import importlib.util

from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).resolve().parent.parent  # noqa: F821

datas = [(str(ROOT / "ucm_accept" / "resources"), "ucm_accept/resources")]
binaries = []
hiddenimports = ["yaml", "ucm_accept.cli", "ucm_accept.gui", "ucm_accept.service"]

for package in ("gradio", "gradio_client", "safehttpx"):
    if importlib.util.find_spec(package):
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
        datas += pkg_datas
        binaries += pkg_binaries
        hiddenimports += pkg_hidden

if importlib.util.find_spec("evalscope"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all("evalscope")
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

a = Analysis(  # noqa: F821
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib.tests", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ucm-accept",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ucm-accept",
)
