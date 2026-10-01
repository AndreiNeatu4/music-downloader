"""CustomTkinter window: link entry, settings, progress, download list."""

import os
import subprocess
import sys
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from app import config, paths
from app.downloader import (
    QUALITY_CHOICES,
    SOURCE_SPOTIFY,
    SOURCE_UNKNOWN,
    SOURCE_YOUTUBE,
    DownloadManager,
    detect_source,
)

SOURCE_LABELS = {
    SOURCE_YOUTUBE: ("Detected: YouTube", "#ff5252"),
    SOURCE_SPOTIFY: ("Detected: Spotify", "#1db954"),
}
STATUS_COLORS = {
    "queued": "gray60",
    "resolving": "#4a9eff",
    "downloading": "#4a9eff",
    "converting": "#ffb84a",
    "done": "#1db954",
    "error": "#ff5252",
    "cancelled": "gray60",
}


def _shorten_path(path: str, limit: int = 58) -> str:
    if len(path) <= limit:
        return path
    return path[:20] + " ... " + path[-(limit - 25):]


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.settings = config.load()
        self.manager = DownloadManager()
        self.rows: dict[int, JobRow] = {}

        self.title("Music Downloader - YouTube & Spotify")
        icon = paths.app_icon()
        if icon:
            try:
                self.iconbitmap(icon)
            except Exception:  # a bad icon must never stop the app from opening
                pass
        self.geometry("860x660")
        self.minsize(700, 560)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self._build_link_card()
        self._build_settings_card()
        self._build_progress_card()
        self._build_list()

        self._poll_events()

    # ------------------------------------------------------------- UI layout

    def _build_link_card(self):
        card = ctk.CTkFrame(self, corner_radius=12)
        card.grid(row=0, column=0, padx=16, pady=(16, 8), sticky="ew")
        card.grid_columnconfigure(0, weight=1)

        # No textvariable: CustomTkinter hides the placeholder when one is bound.
        self._last_url = ""
        self.url_entry = ctk.CTkEntry(
            card,
            height=44,
            font=ctk.CTkFont(size=14),
            placeholder_text="Paste a YouTube or Spotify link (track, playlist or album)",
        )
        self.url_entry.grid(row=0, column=0, padx=(16, 8), pady=(16, 6), sticky="ew")
        self.url_entry.bind("<Return>", lambda _: self._on_download())

        self.download_button = ctk.CTkButton(
            card, text="Download", width=130, height=44,
            font=ctk.CTkFont(size=14, weight="bold"), command=self._on_download,
        )
        self.download_button.grid(row=0, column=1, padx=(0, 16), pady=(16, 6))

        self.detect_label = ctk.CTkLabel(card, text="", font=ctk.CTkFont(size=12), anchor="w")
        self.detect_label.grid(row=1, column=0, columnspan=2, padx=18, pady=(0, 12), sticky="ew")

    def _build_settings_card(self):
        card = ctk.CTkFrame(self, corner_radius=12)
        card.grid(row=1, column=0, padx=16, pady=8, sticky="ew")
        card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(card, text="Save to", width=90, anchor="w").grid(
            row=0, column=0, padx=(16, 8), pady=(16, 8), sticky="w"
        )
        self.folder_label = ctk.CTkLabel(
            card, text=_shorten_path(self.settings["output_folder"]),
            anchor="w", text_color="gray70",
        )
        self.folder_label.grid(row=0, column=1, pady=(16, 8), sticky="ew")
        ctk.CTkButton(card, text="Change", width=90, command=self._pick_folder).grid(
            row=0, column=2, padx=4, pady=(16, 8)
        )
        ctk.CTkButton(
            card, text="Open", width=70, fg_color="transparent", border_width=1,
            command=self._open_folder,
        ).grid(row=0, column=3, padx=(4, 16), pady=(16, 8))

        ctk.CTkLabel(card, text="Quality", width=90, anchor="w").grid(
            row=1, column=0, padx=(16, 8), pady=(0, 6), sticky="w"
        )
        labels = [choice["label"] for choice in QUALITY_CHOICES.values()]
        self.quality_menu = ctk.CTkOptionMenu(
            card, values=labels, width=240, command=self._on_quality_change
        )
        self.quality_menu.set(QUALITY_CHOICES[self._quality_key()]["label"])
        self.quality_menu.grid(row=1, column=1, pady=(0, 6), sticky="w")

        self.quality_info = ctk.CTkLabel(
            card, text="", font=ctk.CTkFont(size=11), text_color="gray60",
            anchor="w", justify="left", wraplength=700,
        )
        self.quality_info.grid(row=2, column=0, columnspan=4, padx=18, pady=(0, 14), sticky="ew")
        self._refresh_quality_info()

    def _build_progress_card(self):
        card = ctk.CTkFrame(self, corner_radius=12)
        card.grid(row=2, column=0, padx=16, pady=8, sticky="ew")
        card.grid_columnconfigure(0, weight=1)

        self.progress = ctk.CTkProgressBar(card, height=12)
        self.progress.set(0)
        self.progress.grid(row=0, column=0, padx=(16, 8), pady=(16, 8), sticky="ew")

        self.cancel_button = ctk.CTkButton(
            card, text="Cancel", width=90, fg_color="transparent", border_width=1,
            state="disabled", command=self.manager.cancel_current,
        )
        self.cancel_button.grid(row=0, column=1, padx=(0, 16), pady=(16, 8))

        self.status_label = ctk.CTkLabel(
            card, text="Idle", anchor="w", font=ctk.CTkFont(size=12), text_color="gray70"
        )
        self.status_label.grid(row=1, column=0, columnspan=2, padx=18, pady=(0, 14), sticky="ew")

    def _build_list(self):
        self.list_frame = ctk.CTkScrollableFrame(self, corner_radius=12, label_text="Downloads")
        self.list_frame.grid(row=3, column=0, padx=16, pady=(8, 16), sticky="nsew")
        self.list_frame.grid_columnconfigure(0, weight=1)

        self.empty_label = ctk.CTkLabel(
            self.list_frame, text="Nothing downloaded yet.", text_color="gray50"
        )
        self.empty_label.grid(row=0, column=0, pady=20)

    # --------------------------------------------------------------- actions

    def _quality_key(self) -> str:
        key = self.settings.get("audio_quality")
        return key if key in QUALITY_CHOICES else "mp3_320"

    def _key_for_label(self, label: str) -> str:
        for key, choice in QUALITY_CHOICES.items():
            if choice["label"] == label:
                return key
        return "mp3_320"

    def _refresh_quality_info(self):
        self.quality_info.configure(text=QUALITY_CHOICES[self._quality_key()]["info"])

    def _on_quality_change(self, label: str):
        self.settings["audio_quality"] = self._key_for_label(label)
        config.save(self.settings)
        self._refresh_quality_info()

    def _refresh_detection(self):
        url = self.url_entry.get().strip()
        if url == self._last_url:
            return
        self._last_url = url
        if not url:
            self.detect_label.configure(text="")
            return
        source = detect_source(url)
        if source == SOURCE_UNKNOWN:
            self.detect_label.configure(
                text="Unsupported link - paste a youtube.com, youtu.be or open.spotify.com URL",
                text_color="#ff5252",
            )
        else:
            text, color = SOURCE_LABELS[source]
            self.detect_label.configure(text=text, text_color=color)

    def _pick_folder(self):
        chosen = filedialog.askdirectory(initialdir=self.settings["output_folder"])
        if chosen:
            self.settings["output_folder"] = os.path.normpath(chosen)
            config.save(self.settings)
            self.folder_label.configure(text=_shorten_path(self.settings["output_folder"]))

    def _open_folder(self):
        folder = Path(self.settings["output_folder"])
        folder.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(folder)  # noqa: S606 - opening the user's own folder
        else:
            subprocess.Popen(["xdg-open", str(folder)])

    def _on_download(self):
        url = self.url_entry.get().strip()
        if not url:
            return
        if detect_source(url) == SOURCE_UNKNOWN:
            self._refresh_detection()
            return
        self.manager.submit(url, self.settings["output_folder"], self._quality_key())
        self.url_entry.delete(0, "end")
        self._refresh_detection()

    # ---------------------------------------------------------------- events

    def _poll_events(self):
        self._refresh_detection()
        while True:
            try:
                kind, job = self.manager.events.get_nowait()
            except Exception:
                break
            if kind == "added":
                self._add_row(job)
            self._update_row(job)
            self._update_header(job)
        self.after(100, self._poll_events)

    def _add_row(self, job):
        self.empty_label.grid_remove()
        row = JobRow(self.list_frame, job)
        row.grid(row=len(self.rows), column=0, pady=4, sticky="ew")
        self.rows[job.job_id] = row

    def _update_row(self, job):
        row = self.rows.get(job.job_id)
        if row:
            row.refresh(job)

    def _update_header(self, job):
        active = job.status in ("queued", "resolving", "downloading", "converting")
        self.progress.set(job.progress if active else (1.0 if job.status == "done" else 0.0))
        self.cancel_button.configure(state="normal" if active else "disabled")

        detail = job.detail or job.status
        text = detail if job.title in detail else f"{job.title} - {detail}"
        self.status_label.configure(text=text)


class JobRow(ctk.CTkFrame):
    def __init__(self, master, job):
        super().__init__(master, corner_radius=8)
        self.grid_columnconfigure(1, weight=1)

        badge = "YouTube" if job.source == SOURCE_YOUTUBE else (
            "Spotify" if job.source == SOURCE_SPOTIFY else "?"
        )
        color = SOURCE_LABELS.get(job.source, ("", "gray60"))[1]
        ctk.CTkLabel(
            self, text=badge, width=66, font=ctk.CTkFont(size=11, weight="bold"),
            text_color=color,
        ).grid(row=0, column=0, rowspan=2, padx=(12, 8), pady=10)

        self.title_label = ctk.CTkLabel(
            self, text=job.title, anchor="w", font=ctk.CTkFont(size=13)
        )
        self.title_label.grid(row=0, column=1, sticky="ew", pady=(10, 0))

        self.detail_label = ctk.CTkLabel(
            self, text="", anchor="w", font=ctk.CTkFont(size=11), text_color="gray60"
        )
        self.detail_label.grid(row=1, column=1, sticky="ew", pady=(0, 10))

        self.status_label = ctk.CTkLabel(
            self, text="", width=100, font=ctk.CTkFont(size=12, weight="bold")
        )
        self.status_label.grid(row=0, column=2, rowspan=2, padx=(8, 12))

        self.refresh(job)

    def refresh(self, job):
        title = job.title if len(job.title) <= 80 else job.title[:77] + "..."
        self.title_label.configure(text=title)
        self.detail_label.configure(text=job.detail)
        self.status_label.configure(
            text=job.status.capitalize(),
            text_color=STATUS_COLORS.get(job.status, "gray60"),
        )


def run():
    ctk.set_appearance_mode("dark")
    App().mainloop()
