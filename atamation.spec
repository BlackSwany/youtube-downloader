# -*- mode: python ; coding: utf-8 -*-
"""Atamation Media Downloader — tek dosya (onefile) PyInstaller speki."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH)
VENDOR_FFMPEG = ROOT / "vendor" / "ffmpeg"

datas = [
    ("templates", "templates"),
    ("static", "static"),
    ("LICENSE.txt", "."),
    ("assets/app.ico", "assets"),
]
binaries = []
hiddenimports = [
    "services",
    "services.youtube_service",
    "services.export_jobs",
    "services.job_store",
    "webview",
    "webview.platforms.edgechromium",
    "clr_loader",
    "pythonnet",
]

# Essentials FFmpeg + ffprobe (küçük build)
if (VENDOR_FFMPEG / "ffmpeg.exe").is_file():
    binaries.append((str(VENDOR_FFMPEG / "ffmpeg.exe"), "ffmpeg"))
if (VENDOR_FFMPEG / "ffprobe.exe").is_file():
    binaries.append((str(VENDOR_FFMPEG / "ffprobe.exe"), "ffmpeg"))

for package in ("yt_dlp", "webview"):
    collected = collect_all(package)
    datas += collected[0]
    binaries += collected[1]
    hiddenimports += collected[2]

a = Analysis(
    ["desktop_app.py"],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "numpy",
        "pandas",
        "scipy",
        "PIL",
        "pytest",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="AtamationDownloader",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=["ffmpeg.exe", "ffprobe.exe"],
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/app.ico",
    version="file_version_info.txt",
)
