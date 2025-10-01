"""Configuration helpers for the Forex news application."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

CONFIG_PATH = Path(__file__).resolve().parent.parent / "data" / "config.json"
MEDIA_PATH = Path(__file__).resolve().parent.parent / "media"
DEFAULT_ALERT_SOUND = MEDIA_PATH / "Cyber_News_mp3.wav"
DEFAULT_ALERT_SOUND_STR = (
    str(DEFAULT_ALERT_SOUND) if DEFAULT_ALERT_SOUND.exists() else None
)


@dataclass
class AlertPreferences:
    enabled: bool = True
    offsets: list[int] = field(default_factory=lambda: [60, 30, 15, 5])
    snooze_minutes: int = 5
    sound_path: str | None = DEFAULT_ALERT_SOUND_STR


def _clean_optional_str(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            return stripped
    return None


@dataclass
class AppPreferences:
    window_width: int = 1200
    window_height: int = 760
    impacts: list[str] = field(default_factory=lambda: ["High"])
    currencies: list[str] = field(default_factory=list)
    search_text: str = ""
    start_date: str | None = None
    end_date: str | None = None
    auto_refresh_enabled: bool = False
    auto_refresh_minutes: int = 30
    export_directory: str | None = None
    api_url: str | None = None
    alerts: AlertPreferences = field(default_factory=AlertPreferences)


class ConfigManager:
    """Persist and restore user preferences."""

    def __init__(self, path: Path = CONFIG_PATH) -> None:
        self.path = path
        self.preferences = AppPreferences()

    def load(self) -> AppPreferences:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return self.preferences
        except ValueError:
            return self.preferences

        prefs = AppPreferences()
        prefs.window_width = int(data.get("window_width", prefs.window_width))
        prefs.window_height = int(data.get("window_height", prefs.window_height))
        prefs.impacts = list(data.get("impacts", prefs.impacts))
        prefs.currencies = list(data.get("currencies", prefs.currencies))
        prefs.search_text = str(data.get("search_text", prefs.search_text)).strip()
        prefs.start_date = _clean_optional_str(data.get("start_date"))
        prefs.end_date = _clean_optional_str(data.get("end_date"))
        prefs.auto_refresh_enabled = bool(
            data.get("auto_refresh_enabled", prefs.auto_refresh_enabled)
        )
        prefs.auto_refresh_minutes = int(
            data.get("auto_refresh_minutes", prefs.auto_refresh_minutes)
        )

        export_dir = data.get("export_directory")
        prefs.export_directory = str(export_dir).strip() if export_dir else None

        api_url = data.get("api_url")
        prefs.api_url = str(api_url).strip() if api_url else None

        alert_data: Dict[str, Any] = data.get("alerts", {})
        prefs.alerts.enabled = bool(alert_data.get("enabled", prefs.alerts.enabled))
        prefs.alerts.offsets = [
            int(value) for value in alert_data.get("offsets", prefs.alerts.offsets)
        ]
        prefs.alerts.snooze_minutes = int(
            alert_data.get("snooze_minutes", prefs.alerts.snooze_minutes)
        )
        sound_value = _clean_optional_str(alert_data.get("sound_path"))
        if sound_value:
            prefs.alerts.sound_path = sound_value
        elif DEFAULT_ALERT_SOUND_STR:
            prefs.alerts.sound_path = DEFAULT_ALERT_SOUND_STR
        else:
            prefs.alerts.sound_path = None

        self.preferences = prefs
        return prefs

    def save(self, prefs: AppPreferences | None = None) -> None:
        prefs = prefs or self.preferences
        self.preferences = prefs
        payload = {
            "window_width": prefs.window_width,
            "window_height": prefs.window_height,
            "impacts": prefs.impacts,
            "currencies": prefs.currencies,
            "search_text": prefs.search_text,
            "start_date": prefs.start_date,
            "end_date": prefs.end_date,
            "auto_refresh_enabled": prefs.auto_refresh_enabled,
            "auto_refresh_minutes": prefs.auto_refresh_minutes,
            "export_directory": prefs.export_directory,
            "api_url": prefs.api_url,
            "alerts": {
                "enabled": prefs.alerts.enabled,
                "offsets": prefs.alerts.offsets,
                "snooze_minutes": prefs.alerts.snooze_minutes,
                "sound_path": prefs.alerts.sound_path,
            },
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )


__all__ = [
    "ConfigManager",
    "AppPreferences",
    "AlertPreferences",
    "CONFIG_PATH",
    "DEFAULT_ALERT_SOUND",
]
