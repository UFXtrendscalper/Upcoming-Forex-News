"""Utilities for downloading and caching the Forex Factory calendar feed."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import requests
from dateutil import parser as date_parser
from requests import Response, Session
from requests.exceptions import RequestException

DEFAULT_CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
DEFAULT_TIMEOUT = 15
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF_SECONDS = 2.0
CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "latest_calendar.json"
EXPECTED_MINIMUM_KEYS = {"country", "date", "impact", "title"}

logger = logging.getLogger(__name__)


class CalendarAPIError(RuntimeError):
    """Raised when the calendar feed cannot be downloaded or parsed."""


@dataclass(slots=True)
class CalendarFetchResult:
    """Container describing the outcome of a calendar fetch."""

    events: list[dict[str, Any]]
    from_cache: bool
    source: str
    fetched_at: Optional[datetime]


class CalendarClient:
    """Download helper with retry logic and on-disk caching for calendar data."""

    def __init__(
        self,
        base_url: str = DEFAULT_CALENDAR_URL,
        cache_path: Path | None = None,
        *,
        session: Session | None = None,
        timeout: int = DEFAULT_TIMEOUT,
        retries: int = DEFAULT_RETRIES,
        backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
    ) -> None:
        if retries < 1:
            raise ValueError("retries must be >= 1")
        if timeout <= 0:
            raise ValueError("timeout must be > 0")

        self.base_url = base_url
        self.cache_path = cache_path or CACHE_PATH
        self.session = session or requests.Session()
        self.timeout = timeout
        self.retries = retries
        self.backoff_seconds = backoff_seconds

    def fetch(  # noqa: D401 - short docstring for clarity
        self,
        *,
        use_cache_on_fail: bool = True,
        persist_cache: bool = True,
    ) -> CalendarFetchResult:
        """Fetch events from the API, falling back to the cached payload when needed."""

        last_error: Optional[Exception] = None

        for attempt in range(1, self.retries + 1):
            try:
                events = self._download()
                if persist_cache:
                    self._write_cache(events)
                return CalendarFetchResult(
                    events=events,
                    from_cache=False,
                    source=self.base_url,
                    fetched_at=datetime.now(timezone.utc),
                )
            except (CalendarAPIError, RequestException) as exc:
                last_error = exc
                wait_time = self.backoff_seconds * attempt
                logger.warning(
                    "Calendar fetch attempt %s/%s failed: %s", attempt, self.retries, exc
                )
                if attempt < self.retries and wait_time > 0:
                    time.sleep(wait_time)

        if use_cache_on_fail:
            cached = self.load_cache()
            if cached is not None:
                logger.info("Using cached calendar payload from %s", self.cache_path)
                return cached

        message = "Failed to download calendar feed and no cached data was available"
        raise CalendarAPIError(message) from last_error

    def _download(self) -> list[dict[str, Any]]:
        response = self.session.get(self.base_url, timeout=self.timeout)
        self._raise_for_status(response)
        payload = self._parse_json(response)
        return self._validate_events(payload)

    def _raise_for_status(self, response: Response) -> None:
        try:
            response.raise_for_status()
        except RequestException as exc:  # pragma: no cover - thin wrapper
            raise CalendarAPIError(f"Calendar request failed: {exc}") from exc

    def _parse_json(self, response: Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise CalendarAPIError("Received invalid JSON from calendar feed") from exc

    def _validate_events(self, payload: Any) -> list[dict[str, Any]]:
        if not isinstance(payload, list):
            raise CalendarAPIError("Expected top-level JSON array from calendar feed")

        validated: list[dict[str, Any]] = []
        for index, item in enumerate(payload):
            if not isinstance(item, dict):
                raise CalendarAPIError(
                    f"Calendar event at index {index} is not an object: {type(item)!r}"
                )
            missing = EXPECTED_MINIMUM_KEYS - item.keys()
            if missing:
                raise CalendarAPIError(
                    "Calendar event missing required fields: "
                    + ", ".join(sorted(missing))
                )

            date_value = item.get("date")
            if not isinstance(date_value, str):
                raise CalendarAPIError("Calendar event date must be an ISO 8601 string")
            try:
                # Validate the timestamp is parseable without storing the datetime yet.
                date_parser.isoparse(date_value)
            except (TypeError, ValueError) as exc:
                raise CalendarAPIError(
                    f"Invalid calendar event date value: {date_value!r}"
                ) from exc

            validated.append(dict(item))

        return validated

    def _write_cache(self, events: Iterable[dict[str, Any]]) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(list(events), ensure_ascii=False, indent=2)
        self.cache_path.write_text(serialized, encoding="utf-8")

    def load_cache(self) -> Optional[CalendarFetchResult]:
        if not self.cache_path.exists():
            return None

        try:
            raw = self.cache_path.read_text(encoding="utf-8")
            payload = json.loads(raw)
            events = self._validate_events(payload)
        except (OSError, ValueError, CalendarAPIError) as exc:
            logger.warning("Failed to read cached calendar data: %s", exc)
            return None

        fetched_at = self._cache_timestamp()
        return CalendarFetchResult(
            events=events,
            from_cache=True,
            source=str(self.cache_path),
            fetched_at=fetched_at,
        )

    def _cache_timestamp(self) -> Optional[datetime]:
        try:
            stat = self.cache_path.stat()
        except OSError:
            return None
        return datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)


def normalize_event_datetimes(
    events: Iterable[dict[str, Any]], *, include_local: bool = True
) -> list[dict[str, Any]]:
    """Return copies of events with datetime objects attached.

    Parameters
    ----------
    events:
        Iterable of calendar event dictionaries. Each event must contain a
        parseable ISO 8601 string under the ``date`` key.
    include_local:
        When ``True`` (default) a ``datetime_local`` key is added alongside
        ``datetime_utc`` to preserve the system-local timezone conversion.
    """

    normalized: list[dict[str, Any]] = []
    for event in events:
        date_value = event.get("date")
        if not isinstance(date_value, str):
            raise CalendarAPIError("Cannot normalize event without a date string")

        parsed = date_parser.isoparse(date_value)
        event_copy = dict(event)
        event_copy["datetime_utc"] = parsed.astimezone(timezone.utc)
        if include_local:
            event_copy["datetime_local"] = parsed.astimezone()
        normalized.append(event_copy)

    return normalized


def load_default_client() -> CalendarClient:
    """Convenience helper returning a client with default configuration."""

    return CalendarClient()


__all__ = [
    "CalendarAPIError",
    "CalendarClient",
    "CalendarFetchResult",
    "load_default_client",
    "normalize_event_datetimes",
]
