# PyInstaller spec - self-contained build with ffmpeg and QuickJS inside.
#
# Default is a single portable exe. Set BUILD_ONEDIR=1 for a folder build, which
# the MSI installs: it starts instantly instead of unpacking ~130 MB into temp on
# every launch.
import os

from PyInstaller.utils.hooks import collect_all, collect_data_files

ONEDIR = os.environ.get("BUILD_ONEDIR") == "1"

datas, binaries, hiddenimports = [], [], []
for package in ("spotdl", "yt_dlp", "yt_dlp_ejs", "customtkinter", "pykakasi", "ytmusicapi"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

datas += collect_data_files("certifi")
datas += [("installer/app.ico", ".")]  # window/taskbar icon, set at runtime

binaries += [
    ("tools/ffmpeg/ffmpeg.exe", "."),
    ("tools/ffmpeg/ffprobe.exe", "."),
    ("tools/qjs/qjs.exe", "."),
]

a = Analysis(
    ["app/main.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["matplotlib", "pandas", "numpy", "PyQt5", "PySide2", "tests"],
    noarchive=False,
)
pyz = PYZ(a.pure)

common = dict(
    name="MusicDownloader",
    icon="installer/app.ico",
    console=False,
    upx=False,
    strip=False,
    bootloader_ignore_signals=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

if ONEDIR:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **common)
    coll = COLLECT(exe, a.binaries, a.datas, upx=False, strip=False, name="MusicDownloader")
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], **common)
