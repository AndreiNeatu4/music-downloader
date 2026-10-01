"""Filesystem locations that differ between a dev checkout and a frozen exe."""

import os
import shutil
import sys
from pathlib import Path

APP_NAME = "YTSpotifyDownloader"


def _bundle_dir() -> Path | None:
    meipass = getattr(sys, "_MEIPASS", None)
    return Path(meipass) if meipass else None


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _tool_path(exe: str, dev_subdir: str) -> str | None:
    """Locate a bundled helper binary: frozen bundle, then dev checkout, then PATH."""
    candidates = []
    bundle = _bundle_dir()
    if bundle:
        candidates.append(bundle / exe)
    candidates.append(project_root() / "tools" / dev_subdir / exe)

    for candidate in candidates:
        if candidate.is_file():
            return str(candidate.resolve())
    return shutil.which(Path(exe).stem)


def ffmpeg_path() -> str:
    return _tool_path("ffmpeg.exe", "ffmpeg") or "ffmpeg"


def ffmpeg_dir() -> str:
    return str(Path(ffmpeg_path()).parent)


def app_icon() -> str | None:
    """Window icon. Tk draws its own default unless we hand it this."""
    bundle = _bundle_dir()
    candidates = []
    if bundle:
        candidates.append(bundle / "app.ico")
    candidates.append(project_root() / "installer" / "app.ico")
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


def qjs_path() -> str | None:
    """QuickJS binary. yt-dlp needs a JS runtime to solve YouTube's challenges."""
    return _tool_path("qjs.exe", "qjs")


def config_file() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / APP_NAME / "config.json"


def default_output_folder() -> Path:
    music = Path.home() / "Music"
    return music if music.is_dir() else Path.home()
