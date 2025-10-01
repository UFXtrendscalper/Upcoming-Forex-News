"""Markdown export helpers for Forex calendar data."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence

from .api_client import CalendarClient, CalendarFetchResult, CalendarAPIError
from .models import (
    CalendarEvent,
    ImpactLevel,
    build_events,
    filter_by_currency,
    filter_by_impact,
    group_events_by_day,
    search_events,
    sort_events,
)

DEFAULT_TITLE = "Upcoming News"
DEFAULT_EXPORT_DIR = Path(__file__).resolve().parent.parent / "exports"
TABLE_HEADER = "| Time | Currency | Event | Actual | Forecast | Previous |"
TABLE_DIVIDER = "|------|----------|-------|--------|----------|----------|"


def render_markdown(
    *,
    all_events: Sequence[CalendarEvent],
    filtered_events: Sequence[CalendarEvent] | None = None,
    title: str = DEFAULT_TITLE,
    use_local_time: bool = True,
) -> str:
    """Return markdown text mirroring the Upcoming_News layout."""

    filtered_events = filtered_events if filtered_events is not None else all_events

    day_groups = group_events_by_day(all_events, use_local_time=use_local_time)
    filtered_groups = group_events_by_day(filtered_events, use_local_time=use_local_time)

    lines: list[str] = [f"# {title}", ""]

    if not day_groups:
        lines.append("No scheduled events.")
        return "\n".join(lines) + "\n"

    for day, _ in day_groups.items():
        day_label = day.strftime("%a %b %d")
        day_events = filtered_groups.get(day, [])

        lines.append(f"## {day_label}")
        if not day_events:
            lines.append("No scheduled events.")
            lines.append("")
            continue

        lines.append(TABLE_HEADER)
        lines.append(TABLE_DIVIDER)
        for event in sort_events(day_events, by_impact_first=False):
            lines.append(_format_event_row(event, use_local_time=use_local_time))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _format_event_row(event: CalendarEvent, *, use_local_time: bool) -> str:
    dt = event.datetime_local if use_local_time else event.datetime_utc
    time_value = _format_time(dt)
    actual = _safe_value(event.actual)
    forecast = _safe_value(event.forecast)
    previous = _safe_value(event.previous)
    return (
        f"| {time_value} | {event.currency} | {event.title} | "
        f"{actual} | {forecast} | {previous} |"
    )


def _format_time(dt: datetime) -> str:
    rendered = dt.strftime("%I:%M%p").lower()
    # Remove leading zero while keeping midnight as "12".
    if rendered.startswith("0"):
        rendered = rendered[1:]
    return rendered


def _safe_value(value: str | None) -> str:
    return value if value else "n/a"


def write_markdown(markdown: str, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    return output_path


def build_default_output_path(
    *,
    impacts: Sequence[ImpactLevel],
    export_dir: Path = DEFAULT_EXPORT_DIR,
    timestamp: datetime | None = None,
) -> Path:
    timestamp = timestamp or datetime.now()
    slug = "-".join(sorted({impact.value.lower() for impact in impacts})) or "all"
    filename = f"{slug}_impact_news_{timestamp.strftime('%Y%m%d_%H%M')}.md"
    return export_dir / filename


def fetch_events(
    *,
    client: CalendarClient | None = None,
    impacts: Sequence[ImpactLevel] | None = None,
    currencies: Sequence[str] | None = None,
    search: str | None = None,
    use_local_time: bool = True,
) -> tuple[list[CalendarEvent], list[CalendarEvent], CalendarFetchResult]:
    client = client or CalendarClient()
    fetch_result = client.fetch()
    all_events = build_events(fetch_result.events)

    working = list(all_events)
    if impacts:
        working = filter_by_impact(working, impacts)
    if currencies:
        working = filter_by_currency(working, currencies)
    if search:
        working = search_events(working, search)

    return all_events, working, fetch_result


def export_markdown(
    *,
    impacts: Sequence[ImpactLevel] | None = None,
    currencies: Sequence[str] | None = None,
    search: str | None = None,
    title: str = DEFAULT_TITLE,
    use_local_time: bool = True,
    output_path: Path | None = None,
    timestamped: bool = True,
    client: CalendarClient | None = None,
) -> Path:
    all_events, filtered_events, fetch_result = fetch_events(
        client=client,
        impacts=impacts,
        currencies=currencies,
        search=search,
        use_local_time=use_local_time,
    )

    if not output_path:
        impacts_for_slug = impacts or [impact for impact in ImpactLevel if impact not in {ImpactLevel.UNKNOWN}]
        ts = fetch_result.fetched_at if (fetch_result.fetched_at and timestamped) else None
        output_path = build_default_output_path(impacts=impacts_for_slug, timestamp=ts)

    markdown = render_markdown(
        all_events=all_events,
        filtered_events=filtered_events,
        title=title,
        use_local_time=use_local_time,
    )

    return write_markdown(markdown, output_path)


def _parse_impact_args(values: list[str] | None) -> list[ImpactLevel]:
    if not values:
        return [ImpactLevel.HIGH]
    impacts: list[ImpactLevel] = []
    for value in values:
        impact = ImpactLevel.from_value(value)
        if impact is ImpactLevel.UNKNOWN:
            raise ValueError(f"Unsupported impact level: {value}")
        impacts.append(impact)
    return impacts


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export Forex calendar data to markdown")
    parser.add_argument(
        "--impact",
        action="append",
        help="Impact level to include (can be repeated). Defaults to High.",
    )
    parser.add_argument(
        "--currency",
        action="append",
        help="Restrict results to specific currency codes (can be repeated).",
    )
    parser.add_argument("--search", help="Case-insensitive text query to filter events.")
    parser.add_argument(
        "--utc",
        action="store_true",
        help="Render event times in UTC instead of local timezone.",
    )
    parser.add_argument("--title", default=DEFAULT_TITLE, help="Markdown document title.")
    parser.add_argument(
        "--output",
        type=Path,
        help="File path for the exported markdown. Defaults to timestamped file in exports/.",
    )
    parser.add_argument(
        "--no-timestamp",
        action="store_true",
        help="Disable timestamped filenames when using the default output location.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    try:
        impacts = _parse_impact_args(args.impact)
        currencies = [value.upper() for value in args.currency] if args.currency else None

        output_path = export_markdown(
            impacts=impacts,
            currencies=currencies,
            search=args.search,
            title=args.title,
            use_local_time=not args.utc,
            output_path=args.output,
            timestamped=not args.no_timestamp,
        )
    except (CalendarAPIError, ValueError) as exc:
        parser.error(str(exc))
        return 2

    print(f"Markdown saved to {output_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())


__all__ = [
    "render_markdown",
    "write_markdown",
    "build_default_output_path",
    "fetch_events",
    "export_markdown",
    "main",
]
