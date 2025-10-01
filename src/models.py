"""Core data models and helper utilities for Forex calendar events."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Iterable, Mapping, MutableMapping, Optional, Sequence

from dateutil import parser as date_parser

try:
    from datetime import UTC  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - Python < 3.11 fallback
    UTC = timezone.utc


class ImpactLevel(str, Enum):
    """Known impact severities emitted by the calendar feed."""

    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    HOLIDAY = "Holiday"
    NONE = "None"
    UNKNOWN = "Unknown"

    @classmethod
    def from_value(cls, value: Optional[str]) -> "ImpactLevel":
        if not value:
            return cls.UNKNOWN
        normalized = value.strip().title()
        for member in cls:
            if member.value == normalized:
                return member
        return cls.UNKNOWN


IMPACT_SORT_WEIGHT: Mapping[ImpactLevel, int] = {
    ImpactLevel.HIGH: 0,
    ImpactLevel.MEDIUM: 1,
    ImpactLevel.LOW: 2,
    ImpactLevel.HOLIDAY: 3,
    ImpactLevel.NONE: 4,
    ImpactLevel.UNKNOWN: 5,
}


@dataclass(slots=True, frozen=True)
class CalendarEvent:
    """Canonical representation of a Forex Factory calendar entry."""

    uid: str
    title: str
    currency: str
    impact: ImpactLevel
    datetime_utc: datetime
    datetime_local: datetime
    forecast: Optional[str] = None
    previous: Optional[str] = None
    actual: Optional[str] = None
    raw: Mapping[str, object] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api_payload(
        cls, payload: Mapping[str, object], *, include_local: bool = True
    ) -> "CalendarEvent":
        date_value = _coerce_str(payload.get("date"))
        if not date_value:
            raise ValueError("Calendar event payload missing `date` string")
        parsed = date_parser.isoparse(date_value)
        datetime_utc = parsed.astimezone(UTC)
        datetime_local = parsed.astimezone() if include_local else datetime_utc

        title = _coerce_str(payload.get("title")) or "Untitled"
        currency = _coerce_str(payload.get("country")) or "N/A"
        impact = ImpactLevel.from_value(_coerce_str(payload.get("impact")))

        uid = cls._build_uid(currency, title, datetime_utc)

        return cls(
            uid=uid,
            title=title,
            currency=currency,
            impact=impact,
            datetime_utc=datetime_utc,
            datetime_local=datetime_local,
            forecast=_coerce_optional_str(payload.get("forecast")),
            previous=_coerce_optional_str(payload.get("previous")),
            actual=_coerce_optional_str(payload.get("actual")),
            raw=dict(payload),
        )

    @staticmethod
    def _build_uid(currency: str, title: str, when: datetime) -> str:
        return f"{currency}:{when.isoformat()}:{title}".lower()

    @property
    def sort_key(self) -> tuple[int, datetime]:
        return (IMPACT_SORT_WEIGHT.get(self.impact, 9), self.datetime_utc)


def build_events(payload: Iterable[Mapping[str, object]]) -> list[CalendarEvent]:
    events: list[CalendarEvent] = []
    for item in payload:
        events.append(CalendarEvent.from_api_payload(item))
    return events


def group_events_by_day(
    events: Iterable[CalendarEvent], *, use_local_time: bool = True
) -> dict[date, list[CalendarEvent]]:
    buckets: MutableMapping[date, list[CalendarEvent]] = defaultdict(list)
    for event in events:
        key_date = (event.datetime_local if use_local_time else event.datetime_utc).date()
        buckets[key_date].append(event)

    for day_events in buckets.values():
        day_events.sort(key=lambda event: ((event.datetime_local if use_local_time else event.datetime_utc), IMPACT_SORT_WEIGHT.get(event.impact, 9), event.title.lower()))

    return dict(sorted(buckets.items(), key=lambda item: item[0]))


def filter_by_impact(
    events: Iterable[CalendarEvent], impacts: Sequence[ImpactLevel]
) -> list[CalendarEvent]:
    allowed = set(impacts)
    return [event for event in events if event.impact in allowed]


def filter_by_currency(
    events: Iterable[CalendarEvent], currencies: Sequence[str]
) -> list[CalendarEvent]:
    normalized = {currency.upper() for currency in currencies}
    return [event for event in events if event.currency.upper() in normalized]


def filter_by_date_range(
    events: Iterable[CalendarEvent],
    start: date | None,
    end: date | None,
    *,
    use_local_time: bool = True,
) -> list[CalendarEvent]:
    if not start and not end:
        return list(events)

    results: list[CalendarEvent] = []
    for event in events:
        event_date = (
            event.datetime_local if use_local_time else event.datetime_utc
        ).date()
        if start and event_date < start:
            continue
        if end and event_date > end:
            continue
        results.append(event)
    return results


def search_events(events: Iterable[CalendarEvent], query: str) -> list[CalendarEvent]:
    if not query:
        return list(events)
    needle = query.lower()
    results: list[CalendarEvent] = []
    for event in events:
        if _match_event(event, needle):
            results.append(event)
    return results


def sort_events(
    events: Iterable[CalendarEvent], *, by_impact_first: bool = True
) -> list[CalendarEvent]:
    if by_impact_first:
        return sorted(events, key=lambda event: event.sort_key)
    return sorted(events, key=lambda event: event.datetime_utc)


def _match_event(event: CalendarEvent, needle: str) -> bool:
    haystacks = (
        event.title.lower(),
        event.currency.lower(),
        event.impact.value.lower(),
        _fallback_lower(event.forecast),
        _fallback_lower(event.previous),
        _fallback_lower(event.actual),
    )
    return any(needle in hay for hay in haystacks if hay)


def _coerce_str(value: object) -> Optional[str]:
    if isinstance(value, str):
        return value
    return None


def _coerce_optional_str(value: object) -> Optional[str]:
    text = _coerce_str(value)
    if not text:
        return None
    stripped = text.strip()
    return stripped or None


def _fallback_lower(value: Optional[str]) -> Optional[str]:
    return value.lower() if isinstance(value, str) else None


__all__ = [
    "ImpactLevel",
    "CalendarEvent",
    "build_events",
    "group_events_by_day",
    "filter_by_impact",
    "filter_by_currency",
    "filter_by_date_range",
    "search_events",
    "sort_events",
]
