# Music Downloader

One window for downloading music from YouTube and Spotify. Paste a link, press
Download. Files are always named `Song - Artist`.

- Paste a YouTube or Spotify link - the app works out which is which by itself.
- Single tracks land directly in your output folder; playlists and albums get
  their own subfolder named after the playlist.
- Three quality options, each explained in the window:
  - **MP3 320 kbps** - plays on everything.
  - **FLAC** - lossless container; the source is already lossy, so this only
    makes bigger files.
  - **Original codec (Opus/M4A)** - no re-encoding, smallest files, slightly
    less universal playback.
- Output folder and quality are remembered between runs.

Spotify has no public download API, so Spotify links are resolved through
`spotdl`: it reads the track metadata from Spotify and fetches the matching
audio from YouTube.

## Installing

Double-click `MusicDownloader-1.0.0.msi`. It installs for the current user only,
so Windows never asks for an administrator password, and it adds a Start Menu
and a Desktop shortcut. Removing it works the usual way, through Settings ->
Apps.

Nothing else needs to be installed - ffmpeg, QuickJS and Python all travel
inside the package. The only requirement is 64-bit Windows 10 or 11.

## Running from source

```powershell
python -m pip install -r requirements.txt
.\scripts\fetch_tools.ps1      # one-time: downloads ffmpeg, QuickJS and WiX into tools\
python -m app.main
```

## Building

```powershell
.\scripts\build_msi.ps1        # dist\MusicDownloader-1.0.0.msi - the installer
.\scripts\build_exe.ps1        # dist\MusicDownloader.exe - a portable single file
```

Pass `-Version 1.0.1` to `build_msi.ps1` to stamp a new version.

The installer ships a folder build, which starts in well under a second. The
portable exe packs the same thing into one file for carrying on a USB stick, at
the cost of unpacking ~130 MB into temp on every launch.

## Why ffmpeg and QuickJS are bundled

- **ffmpeg** extracts and converts the audio.
- **QuickJS** is a JavaScript runtime. yt-dlp has to solve a JavaScript
  challenge that YouTube serves with every video; without a runtime available
  every media request comes back as `HTTP 403 Forbidden`. QuickJS is ~2 MB,
  which is why it is bundled instead of Deno (~100 MB). If Deno or Node is
  already installed on the machine, those are used instead.

## Layout

| Path | Purpose |
| --- | --- |
| `app/gui.py` | The window: link entry, settings, progress, download list |
| `app/downloader.py` | Link detection and the worker thread running yt-dlp / spotdl |
| `app/config.py` | Settings stored in `%APPDATA%\YTSpotifyDownloader\config.json` |
| `app/paths.py` | Finds ffmpeg, QuickJS and the icon in the bundle or in `tools\` |
| `installer/Product.wxs` | WiX definition of the per-user installer |
| `scripts/fetch_tools.ps1` | Downloads ffmpeg, QuickJS and the WiX toolset |
| `scripts/build_msi.ps1` | Builds the installer |
| `scripts/build_exe.ps1` | Builds the portable exe |
