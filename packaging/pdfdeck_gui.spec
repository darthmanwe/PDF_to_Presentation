# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the pdfdeck desktop app.

One-DIR, windowed build. One-dir (not one-file) is deliberate: one-file
re-extracts the whole ~300 MB payload to a temp dir on every launch (slow cold
starts, and the classic antivirus false-positive shape), whereas one-dir starts
fast, is scanned once, and updates are just "replace the folder".

Build:   python -m PyInstaller packaging/pdfdeck_gui.spec --noconfirm \
                 --distpath packaging/dist --workpath packaging/build
Console diagnostic build (shows a terminal + traceback):
         set PDFDECK_CONSOLE=1  before building.
"""

import os

from PyInstaller.utils.hooks import (
    collect_all,
    collect_data_files,
    collect_submodules,
    copy_metadata,
)

REPO_ROOT = os.path.dirname(SPECPATH)          # packaging/ -> repo root
ENTRY = os.path.join(SPECPATH, "gui_entry.py")

datas = []
binaries = []
hiddenimports = []

# Hazard #1: DeckBuilder calls bare Presentation(), which loads python-pptx's
# bundled default template from the pptx package's data files.
datas += collect_data_files("pptx")

# Hazard #2: almost every third-party import in pdfdeck is deferred inside
# functions (to keep tests offline), so PyInstaller's static analysis misses
# them. Pull whole trees for the packages that are imported dynamically.
for pkg in (
    "pdfdeck",
    "langgraph",
    "langchain_core",
    "langchain_anthropic",
    "anthropic",
    "pydantic",
    "pydantic_settings",
    "pymupdf4llm",
):
    hiddenimports += collect_submodules(pkg)

hiddenimports += [
    "fitz",
    "pymupdf",
    "scipy.ndimage",
    "PIL.Image",
    "PIL.ImageDraw",
    "requests",
    "dotenv",
    "typer",
]

# Hazard #4: pymupdf4llm activates pymupdf.layout at import (see its __init__),
# which needs the layout subpackage's Python modules AND its ~47 MB of ONNX
# model data under pymupdf/layout/resources/. collect_submodules('pymupdf4llm')
# does not reach the separate 'pymupdf' namespace, so pull the whole layout
# subpackage explicitly. onnxruntime is collected by its own contrib hook.
_lay_datas, _lay_bins, _lay_hidden = collect_all("pymupdf.layout")
datas += _lay_datas
binaries += _lay_bins
hiddenimports += _lay_hidden

# Hazard #3: langchain / langgraph / anthropic / pydantic inspect installed
# package metadata via importlib.metadata at import time; frozen apps need the
# .dist-info copied in or they raise PackageNotFoundError. Defensive loop:
# skip any distribution that is not installed in this environment.
for dist in (
    "langchain-core",
    "langchain-anthropic",
    "langgraph",
    "langgraph-checkpoint",
    "langgraph-prebuilt",
    "langgraph-sdk",
    "langchain-protocol",
    "anthropic",
    "pydantic",
    "pydantic-core",
    "pydantic-settings",
    "numpy",
    "requests",
):
    try:
        datas += copy_metadata(dist)
    except Exception:
        pass

# Dev-only / heavy transitive weight we never call from the GUI.
excludes = [
    "streamlit",
    "pytest",
    "IPython",
    "jupyter",
    "matplotlib",
    "pandas",
    "altair",
    "pyarrow",
]

block_cipher = None

a = Analysis(
    [ENTRY],
    pathex=[REPO_ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
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
    name="PDFDeck",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                                   # UPX packing is an AV magnet
    console=bool(os.environ.get("PDFDECK_CONSOLE")),
    disable_windowed_traceback=False,
    argv_emulation=False,
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
    upx=False,
    upx_exclude=[],
    name="pdfdeck-2.0.0",                        # top-level folder inside the zip
)
