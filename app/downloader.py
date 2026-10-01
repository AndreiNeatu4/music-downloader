"""Link detection and the worker thread that runs yt-dlp / spotdl jobs."""

import logging
import queue
import shlex
import threading
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from app import paths

SOURCE_YOUTUBE = "youtube"
SOURCE_SPOTIFY = "spotify"
SOURCE_UNKNOWN = "unknown"

QUALITY_CHOICES = {
    "mp3_320": {
        "label": "MP3 320 kbps",
        "info": "Best MP3 quality. Plays on literally everything - phones, cars, old devices.",
    },
    "flac": {
        "label": "FLAC (lossless container)",
        "info": "Lossless container, but the source is already lossy - bigger files, no real quality gain.",
    },
    "original": {
        "label": "Original codec (Opus/M4A)",
        "info": "No re-encoding, so no extra quality loss and smallest files. Some older players can't read Opus.",
    },
}

_YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtu.be",
}
_SPOTIFY_HOSTS = {"open.spotify.com", "play.spotify.com"}


_spotify_lock = threading.Lock()


def _init_spotify_client() -> None:
    """Spotify's client is a process-wide singleton that refuses a second init."""
    from spotdl.utils.config import SPOTIFY_OPTIONS
    from spotdl.utils.spotify import SpotifyClient

    with _spotify_lock:
        if SpotifyClient._instance is None:  # noqa: SLF001 - no public accessor exists
            SpotifyClient.init(
                client_id=SPOTIFY_OPTIONS["client_id"],
                client_secret=SPOTIFY_OPTIONS["client_secret"],
                no_cache=True,
            )


def js_runtimes() -> dict:
    """Enable a system Deno/Node if present, else fall back to the bundled QuickJS.

    Without a JS runtime yt-dlp cannot solve YouTube's "n challenge" and every
    media URL comes back as HTTP 403.
    """
    runtimes: dict[str, dict] = {"deno": {}, "node": {}, "quickjs": {}}
    qjs = paths.qjs_path()
    if qjs:
        runtimes["quickjs"] = {"path": qjs}
    return runtimes


def detect_source(url: str) -> str:
    """Classify a pasted link as YouTube, Spotify, or unsupported."""
    url = url.strip()
    if not url:
        return SOURCE_UNKNOWN
    if "://" not in url:
        url = "https://" + url
    host = (urlparse(url).hostname or "").lower()
    if host in _YOUTUBE_HOSTS:
        return SOURCE_YOUTUBE
    if host in _SPOTIFY_HOSTS:
        return SOURCE_SPOTIFY
    return SOURCE_UNKNOWN


def is_spotify_collection(url: str) -> bool:
    path = urlparse(url.strip()).path
    return "/playlist/" in path or "/album/" in path


@dataclass
class Job:
    url: str
    source: str
    output_folder: str
    quality: str
    job_id: int = 0
    title: str = ""
    status: str = "queued"
    detail: str = ""
    progress: float = 0.0
    tracks_done: int = 0
    tracks_total: int = 0
    cancelled: bool = field(default=False, repr=False)


class DownloadManager:
    """Runs jobs one at a time on a background thread and reports status via a queue."""

    def __init__(self):
        self._jobs: queue.Queue[Job | None] = queue.Queue()
        self.events: queue.Queue[tuple[str, Job]] = queue.Queue()
        self._next_id = 1
        self._current: Job | None = None
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def submit(self, url: str, output_folder: str, quality: str) -> Job:
        job = Job(
            url=url.strip(),
            source=detect_source(url),
            output_folder=output_folder,
            quality=quality,
            job_id=self._next_id,
            title=url.strip(),
        )
        self._next_id += 1
        self._jobs.put(job)
        self._emit("added", job)
        return job

    def cancel_current(self) -> None:
        with self._lock:
            if self._current:
                self._current.cancelled = True

    def _emit(self, kind: str, job: Job) -> None:
        self.events.put((kind, job))

    def _update(self, job: Job, **changes) -> None:
        for key, value in changes.items():
            setattr(job, key, value)
        self._emit("updated", job)

    def _run(self) -> None:
        while True:
            job = self._jobs.get()
            if job is None:
                return
            with self._lock:
                self._current = job
            try:
                self._process(job)
            except Exception as exc:  # a failed job must not kill the worker
                logging.exception("job failed")
                self._update(job, status="error", detail=str(exc), progress=0.0)
            finally:
                with self._lock:
                    self._current = None
                self._jobs.task_done()

    def _process(self, job: Job) -> None:
        Path(job.output_folder).mkdir(parents=True, exist_ok=True)
        if job.source == SOURCE_YOUTUBE:
            self._download_youtube(job)
        elif job.source == SOURCE_SPOTIFY:
            self._download_spotify(job)
        else:
            self._update(job, status="error", detail="Unsupported link")

    # ---------------------------------------------------------------- YouTube

    def _download_youtube(self, job: Job) -> None:
        from yt_dlp import YoutubeDL
        from yt_dlp.utils import DownloadCancelled

        self._update(job, status="resolving", detail="Reading link...")

        probe_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": "in_playlist",
            "noprogress": True,
            "js_runtimes": js_runtimes(),
        }
        with YoutubeDL(probe_opts) as ydl:
            info = ydl.extract_info(job.url, download=False)

        is_playlist = info.get("_type") == "playlist"
        if is_playlist:
            entries = [e for e in (info.get("entries") or []) if e]
            playlist_title = info.get("title") or "Playlist"
            self._update(
                job,
                title=playlist_title,
                tracks_total=len(entries),
                detail=f"{len(entries)} tracks",
            )
            name_template = "%(playlist_title)s/%(track,title)s - %(artist,uploader)s.%(ext)s"
        else:
            self._update(job, title=info.get("title") or job.url, tracks_total=1)
            name_template = "%(track,title)s - %(artist,uploader)s.%(ext)s"

        def hook(data: dict) -> None:
            if job.cancelled:
                raise DownloadCancelled("Cancelled")
            if data.get("status") == "downloading":
                total = data.get("total_bytes") or data.get("total_bytes_estimate")
                fraction = data["downloaded_bytes"] / total if total else 0.0
                name = Path(data.get("filename") or "").stem or job.title
                self._update(
                    job,
                    status="downloading",
                    progress=fraction,
                    detail=self._track_detail(job, name),
                )
            elif data.get("status") == "finished":
                self._update(
                    job,
                    status="converting",
                    progress=1.0,
                    tracks_done=min(job.tracks_done + 1, max(job.tracks_total, 1)),
                    detail="Converting audio...",
                )

        opts = {
            "outtmpl": str(Path(job.output_folder) / name_template),
            "ffmpeg_location": paths.ffmpeg_dir(),
            "js_runtimes": js_runtimes(),
            "windowsfilenames": True,
            "format": "bestaudio/best",
            "ignoreerrors": "only_download",
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "progress_hooks": [hook],
            "postprocessors": self._ytdlp_postprocessors(job.quality),
        }

        try:
            with YoutubeDL(opts) as ydl:
                ydl.download([job.url])
        except DownloadCancelled:
            self._update(job, status="cancelled", detail="Cancelled", progress=0.0)
            return

        saved = job.tracks_done
        if saved == 0:
            self._update(
                job,
                status="error",
                progress=0.0,
                detail="Download failed - YouTube refused the media request",
            )
            return

        if job.tracks_total > 1:
            detail = f"Saved {saved} of {job.tracks_total} tracks"
            if saved < job.tracks_total:
                detail += f" ({job.tracks_total - saved} failed)"
        else:
            detail = "Saved"
        self._update(job, status="done", progress=1.0, detail=detail)

    @staticmethod
    def _ytdlp_postprocessors(quality: str) -> list[dict]:
        if quality == "mp3_320":
            extract = {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "320",
            }
        elif quality == "flac":
            extract = {"key": "FFmpegExtractAudio", "preferredcodec": "flac"}
        else:
            extract = {"key": "FFmpegExtractAudio", "preferredcodec": "best"}
        return [extract, {"key": "FFmpegMetadata", "add_metadata": True}]

    @staticmethod
    def _track_detail(job: Job, name: str) -> str:
        if job.tracks_total > 1:
            return f"({job.tracks_done + 1}/{job.tracks_total}) {name}"
        return name

    # ---------------------------------------------------------------- Spotify

    def _download_spotify(self, job: Job) -> None:
        from spotdl.download.downloader import Downloader
        from spotdl.download.progress_handler import ProgressHandler
        from spotdl.utils.config import DOWNLOADER_OPTIONS
        from spotdl.utils.search import parse_query

        self._update(job, status="resolving", detail="Reading Spotify metadata...")
        _init_spotify_client()

        collection = is_spotify_collection(job.url)
        name_template = (
            "{list-name}/{title} - {artist}.{output-ext}"
            if collection
            else "{title} - {artist}.{output-ext}"
        )

        if job.quality == "mp3_320":
            audio_format, bitrate = "mp3", "320k"
        elif job.quality == "flac":
            audio_format, bitrate = "flac", None
        else:
            audio_format, bitrate = "opus", None

        settings = dict(DOWNLOADER_OPTIONS)
        settings.update(
            {
                "output": str(Path(job.output_folder) / name_template),
                "format": audio_format,
                "ffmpeg": paths.ffmpeg_path(),
                "simple_tui": True,
                "threads": 1,
                "print_errors": False,
                "log_level": "CRITICAL",
                "load_config": False,
            }
        )
        settings["bitrate"] = bitrate
        qjs = paths.qjs_path()
        if qjs:
            # spotdl re-parses this with shlex, so quote the Windows path.
            settings["yt_dlp_args"] = (
                f"--js-runtimes {shlex.quote('quickjs:' + qjs)}"
            )

        def on_progress(tracker, message: str) -> None:
            if job.cancelled:
                return
            total = max(tracker.parent.song_count, 1)
            done = tracker.parent.overall_completed_tasks
            label = f"({min(done + 1, total)}/{total}) {tracker.song_name}" if total > 1 else tracker.song_name
            self._update(
                job,
                status="downloading",
                tracks_done=done,
                tracks_total=total,
                progress=tracker.progress / 100,
                detail=f"{label} - {message.lower()}" if message else label,
            )

        downloader = Downloader(settings=settings)
        downloader.search = lambda song: self._find_playable(downloader, song)
        downloader.progress_handler = ProgressHandler(
            simple_tui=True, update_callback=on_progress
        )

        try:
            songs = parse_query(query=[job.url], threads=1)
            if not songs:
                self._update(job, status="error", detail="Nothing found at that link")
                return

            self._update(
                job,
                title=songs[0].list_name if collection and songs[0].list_name else songs[0].display_name,
                tracks_total=len(songs),
                detail=f"{len(songs)} tracks",
            )

            if job.cancelled:
                self._update(job, status="cancelled", detail="Cancelled")
                return

            results = downloader.download_multiple_songs(songs)
        finally:
            try:
                downloader.progress_handler.close()
                downloader.loop.close()
            except Exception:
                pass

        failed = [song for song, path in results if path is None]
        saved = len(results) - len(failed)
        if saved == 0:
            self._update(
                job,
                status="error",
                detail=self._spotify_error(downloader.errors),
                progress=0.0,
            )
        else:
            detail = f"Saved {saved} of {len(results)} tracks" if len(results) > 1 else "Saved"
            if failed:
                detail += f" ({len(failed)} not found)"
            self._update(job, status="done", progress=1.0, tracks_done=saved, detail=detail)

    @staticmethod
    def _find_playable(downloader, song) -> str:
        """Pick the best YouTube match that can actually be downloaded.

        spotdl commits to its single best match, so one age-restricted or
        region-blocked video fails the whole song even when other uploads of
        the same track (lyric videos, audio uploads) would work fine.
        """
        from spotdl.download.downloader import Downloader

        probe = downloader.audio_providers[0].get_download_metadata
        tried: set[str] = set()
        last_error: Exception | None = None

        try:
            best = Downloader.search(downloader, song)  # spotdl's own pick
        except Exception as exc:  # its ranking can itself trip over a blocked video
            last_error = exc.__cause__ or exc
            best = None
        candidates = [best] if best else []

        def ranked_alternatives():
            yield from candidates
            yield from _ranked_matches(downloader, song)

        for url in ranked_alternatives():
            if url in tried:
                continue
            if len(tried) >= _MAX_CANDIDATES:
                break
            tried.add(url)
            try:
                probe(url)
                return url
            except Exception as exc:
                last_error = exc.__cause__ or exc
                logging.info("skipping %s for %s: %s", url, song.display_name, last_error)

        if last_error is not None:
            raise LookupError(_friendly_ytdlp_error(str(last_error)))
        raise LookupError(f"No results found for song: {song.display_name}")

    @staticmethod
    def _spotify_error(errors: list[str]) -> str:
        if not errors:
            return "No track could be matched on YouTube"
        # spotdl formats these as "<spotify url> - <ExceptionClass>: <message>"
        message = errors[-1].split(" - ", 1)[-1]
        return _friendly_ytdlp_error(message.split(": ", 1)[-1])


_MAX_CANDIDATES = 8


def _ranked_matches(downloader, song):
    """Every provider's search results for the song, best match first."""
    from spotdl.utils.matching import order_results

    query = f"{', '.join(song.artists)} - {song.name}".lower()
    only_verified = downloader.settings["only_verified_results"]
    for provider in downloader.audio_providers:
        scored: dict = {}
        for options in provider.GET_RESULTS_OPTS:
            try:
                results = provider.get_results(query, **options)
            except Exception:
                logging.debug("search failed on %s", provider.name, exc_info=True)
                continue
            if only_verified:
                results = [r for r in results if r.verified]
            scored.update(order_results(results, song))
        for result, _score in sorted(scored.items(), key=lambda kv: kv[1], reverse=True):
            yield result.url


def _friendly_ytdlp_error(message: str) -> str:
    lowered = message.lower()
    if "confirm your age" in lowered or "age-restricted" in lowered:
        return "Only age-restricted uploads found - YouTube requires sign-in for those"
    if "not available in your country" in lowered or "geo-restrict" in lowered:
        return "Only region-blocked uploads found"
    if "no results found" in lowered:
        return "No track could be matched on YouTube"
    return message.removeprefix("ERROR: ").strip()
