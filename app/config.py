"""User settings, persisted as JSON under %APPDATA%."""

import json

from app import paths

DEFAULTS = {
    "output_folder": str(paths.default_output_folder()),
    "audio_quality": "mp3_320",
}


def load() -> dict:
    settings = dict(DEFAULTS)
    path = paths.config_file()
    if path.is_file():
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return settings
        for key in DEFAULTS:
            if key in stored:
                settings[key] = stored[key]
    return settings


def save(settings: dict) -> None:
    path = paths.config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {key: settings.get(key, DEFAULTS[key]) for key in DEFAULTS}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
