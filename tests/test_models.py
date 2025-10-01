
import datetime

import pytest

from src.models import (
    CalendarEvent,
    ImpactLevel,
    build_events,
    filter_by_currency,
    filter_by_date_range,
    filter_by_impact,
    search_events,
    sort_events,
)


@pytest.fixture
def sample_payload():
    return [
        {
            "date": "2025-10-01T12:30:00Z",
            "impact": "High",
            "country": "USD",
            "title": "GDP",
            "actual": "2.9%",
            "forecast": "3.0%",
            "previous": "2.8%",
        },
        {
            "date": "2025-10-02T07:45:00Z",
            "impact": "Medium",
            "country": "EUR",
            "title": "CPI",
            "forecast": "2.1%",
        },
    ]


def test_build_events_creates_calendar_events(sample_payload):
    events = build_events(sample_payload)
    assert len(events) == 2
    assert all(isinstance(event, CalendarEvent) for event in events)
    assert events[0].impact is ImpactLevel.HIGH
    assert events[0].datetime_utc.tzinfo is not None


def test_filter_by_impact(sample_payload):
    events = build_events(sample_payload)
    filtered = filter_by_impact(events, [ImpactLevel.HIGH])
    assert len(filtered) == 1
    assert filtered[0].title == "GDP"


def test_filter_by_currency_case_insensitive(sample_payload):
    events = build_events(sample_payload)
    filtered = filter_by_currency(events, ["usd"])
    assert [event.currency for event in filtered] == ["USD"]


def test_filter_by_date_range_limits_results(sample_payload):
    events = build_events(sample_payload)
    start = datetime.date(2025, 10, 2)
    end = datetime.date(2025, 10, 2)
    filtered = filter_by_date_range(events, start, end)
    assert len(filtered) == 1
    assert filtered[0].currency == "EUR"

    before = datetime.date(2025, 10, 1)
    filtered_before = filter_by_date_range(events, None, before)
    assert len(filtered_before) == 1
    assert filtered_before[0].currency == "USD"


def test_search_events_matches_title(sample_payload):
    events = build_events(sample_payload)
    results = search_events(events, "gdp")
    assert len(results) == 1
    assert results[0].title == "GDP"


def test_sort_events_by_impact_then_time(sample_payload):
    events = build_events(sample_payload)
    sorted_by_time = sort_events(events, by_impact_first=False)
    assert sorted_by_time[0].datetime_utc <= sorted_by_time[1].datetime_utc
    high_first = sort_events(events, by_impact_first=True)
    assert high_first[0].impact is ImpactLevel.HIGH
