"""Tkinter + ttkbootstrap desktop application shell for forex news."""

from __future__ import annotations

import threading
import tkinter as tk
from datetime import date, datetime
from tkinter import ttk
from typing import Iterable, Sequence

from ttkbootstrap import Window
from ttkbootstrap.constants import BOTH, END, LEFT, RIGHT, X
from ttkbootstrap.dialogs import Messagebox
from ttkbootstrap.widgets import Button, Checkbutton, Entry, Frame, Label

from .api_client import CalendarAPIError, CalendarClient
from .export_markdown import export_markdown
from .models import (
    CalendarEvent,
    ImpactLevel,
    build_events,
    filter_by_currency,
    filter_by_impact,
    search_events,
    sort_events,
)

TREE_COLUMNS = (
    "date",
    "time",
    "currency",
    "impact",
    "event",
    "actual",
    "forecast",
    "previous",
)

DEFAULT_GEOMETRY = "1200x760"
DEFAULT_IMPACT_ORDER = (
    ImpactLevel.HIGH,
    ImpactLevel.MEDIUM,
    ImpactLevel.LOW,
    ImpactLevel.HOLIDAY,
)
DEFAULT_AUTO_REFRESH_MINUTES = 30
AUTO_REFRESH_CHOICES = ("15", "30", "45", "60")


class ForexNewsApp(Window):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__(title="Forex Impact Monitor", themename="cyborg")
        self.geometry(DEFAULT_GEOMETRY)
        self.minsize(980, 620)

        style = self.style
        self.colors = style.colors

        self.client = CalendarClient()
        self._fetch_thread: threading.Thread | None = None

        self.all_events: list[CalendarEvent] = []
        self.filtered_events: list[CalendarEvent] = []
        self.latest_event_date: date | None = None
        self.last_fetch_source: str | None = None
        self.last_fetch_timestamp: datetime | None = None

        self.previous_events_by_uid: dict[str, CalendarEvent] = {}
        self._new_event_uids: set[str] = set()
        self._changed_event_uids: set[str] = set()

        self.impact_filters: dict[ImpactLevel, tk.BooleanVar] = {
            impact: tk.BooleanVar(value=(impact is ImpactLevel.HIGH))
            for impact in DEFAULT_IMPACT_ORDER
        }
        self.currency_var = tk.StringVar()
        self.search_var = tk.StringVar()
        self.auto_refresh_var = tk.BooleanVar(value=False)
        self.auto_refresh_interval_var = tk.StringVar(
            value=str(DEFAULT_AUTO_REFRESH_MINUTES)
        )
        self.status_var = tk.StringVar(value="Ready")
        self.last_updated_var = tk.StringVar(
            value="Last updated: waiting for data (no cache loaded)"
        )

        self._tree_event_map: dict[str, CalendarEvent] = {}
        self._auto_refresh_job: str | None = None

        self._build_styles()
        self._build_menu()
        self._build_layout()

        self.protocol("WM_DELETE_WINDOW", self._on_exit)
        self._load_cache_on_startup()

    def _build_styles(self) -> None:
        base = self.style
        base.configure("Treeview", rowheight=28, font=("Segoe UI", 10))
        base.configure("Treeview.Heading", font=("Segoe UI", 11, "bold"))

    def _build_menu(self) -> None:
        menubar = tk.Menu(self)

        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(
            label="Refresh Data", command=lambda: self.refresh_data(force=True)
        )
        file_menu.add_command(
            label="Export High Impact Markdown",
            command=self.export_high_impact,
        )
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_exit)
        menubar.add_cascade(label="File", menu=file_menu)

        tools_menu = tk.Menu(menubar, tearoff=False)
        tools_menu.add_command(
            label="Settings", command=self._show_settings_placeholder
        )
        tools_menu.add_command(
            label="Alerts", command=self._show_alerts_placeholder
        )
        menubar.add_cascade(label="Tools", menu=tools_menu)

        self.config(menu=menubar)

    def _build_layout(self) -> None:
        container = Frame(self, padding=10)
        container.pack(fill=BOTH, expand=True)

        header = Frame(container)
        header.pack(fill=X, padx=5, pady=(0, 10))
        self._build_header(header)

        content_frame = Frame(container)
        content_frame.pack(fill=BOTH, expand=True)
        self._build_tree(content_frame)

        footer = Frame(container)
        footer.pack(fill=X, pady=(10, 0))
        self._build_footer(footer)

    def _build_header(self, parent: Frame) -> None:
        Label(parent, text="Impact filters:").pack(side=LEFT, padx=(0, 6))
        for impact in DEFAULT_IMPACT_ORDER:
            Checkbutton(
                parent,
                text=impact.value,
                variable=self.impact_filters[impact],
                bootstyle="toolbutton",
                command=self.apply_filters,
            ).pack(side=LEFT, padx=2)

        Button(
            parent,
            text="High Impact Only",
            command=self._apply_high_impact_shortcut,
            bootstyle="secondary",
        ).pack(side=LEFT, padx=(12, 0))

        Button(
            parent,
            text="Export High Impact",
            command=self.export_high_impact,
            bootstyle="warning",
        ).pack(side=LEFT, padx=(4, 0))

        Label(parent, text="Currency (comma-separated):").pack(side=LEFT, padx=(16, 6))
        currency_entry = Entry(parent, textvariable=self.currency_var, width=18)
        currency_entry.pack(side=LEFT)
        currency_entry.bind("<Return>", lambda _event: self.apply_filters())

        Label(parent, text="Search:").pack(side=LEFT, padx=(16, 6))
        search_entry = Entry(parent, textvariable=self.search_var, width=24)
        search_entry.pack(side=LEFT)
        search_entry.bind("<Return>", lambda _event: self.apply_filters())

        Checkbutton(
            parent,
            text="Auto Refresh",
            variable=self.auto_refresh_var,
            bootstyle="round-toggle",
            command=self._update_auto_refresh_state,
        ).pack(side=LEFT, padx=(16, 4))

        interval_combo = ttk.Combobox(
            parent,
            textvariable=self.auto_refresh_interval_var,
            values=AUTO_REFRESH_CHOICES,
            width=5,
            state="readonly",
        )
        interval_combo.pack(side=LEFT)
        interval_combo.bind("<<ComboboxSelected>>", lambda _event: self._update_auto_refresh_state())

        Button(parent, text="Reset Filters", command=self._reset_filters).pack(
            side=LEFT, padx=(16, 0)
        )
        Button(
            parent,
            text="Refresh",
            command=lambda: self.refresh_data(force=True),
            bootstyle="primary",
        ).pack(side=RIGHT)

    def _build_tree(self, parent: Frame) -> None:
        self.tree = ttk.Treeview(parent, columns=TREE_COLUMNS, show="headings", height=18)

        headings = {
            "date": "Date",
            "time": "Time",
            "currency": "Currency",
            "impact": "Impact",
            "event": "Event",
            "actual": "Actual",
            "forecast": "Forecast",
            "previous": "Previous",
        }
        widths = {
            "date": 120,
            "time": 100,
            "currency": 90,
            "impact": 120,
            "event": 360,
            "actual": 110,
            "forecast": 110,
            "previous": 110,
        }
        for column in TREE_COLUMNS:
            self.tree.heading(column, text=headings[column])
            anchor = "e" if column in {"time", "actual", "forecast", "previous"} else "w"
            self.tree.column(column, width=widths[column], anchor=anchor)

        self.tree.tag_configure(
            "impact-high", background=self.colors.danger, foreground=self.colors.light
        )
        self.tree.tag_configure(
            "impact-medium",
            background=self.colors.warning,
            foreground=self.colors.dark,
        )
        self.tree.tag_configure(
            "impact-low", background=self.colors.info, foreground=self.colors.dark
        )
        self.tree.tag_configure("odd-row", background=self.colors.secondary)
        self.tree.tag_configure(
            "event-new", background=self.colors.success, foreground=self.colors.light
        )
        self.tree.tag_configure(
            "event-updated", background=self.colors.primary, foreground=self.colors.light
        )

        y_scroll = ttk.Scrollbar(parent, orient="vertical", command=self.tree.yview)
        x_scroll = ttk.Scrollbar(parent, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")

        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        self.tree.bind("<Double-1>", self._on_tree_double_click)

    def _build_footer(self, parent: Frame) -> None:
        Label(parent, textvariable=self.status_var, anchor="w").pack(fill=X)
        Label(parent, textvariable=self.last_updated_var, anchor="w").pack(fill=X)
        self.progress = ttk.Progressbar(parent, mode="indeterminate")

    def _show_spinner(self, active: bool) -> None:
        if active:
            if not self.progress.winfo_ismapped():
                self.progress.pack(fill=X, pady=(4, 0))
            self.progress.start(12)
        else:
            if self.progress.winfo_manager():
                self.progress.stop()
                self.progress.pack_forget()

    def _load_cache_on_startup(self) -> None:
        cached = self.client.load_cache()
        if not cached:
            self.status_var.set("No cached data found; fetching latest calendar...")
            self.last_updated_var.set(
                "Last updated: awaiting first download (no cache detected)"
            )
            self.after(200, lambda: self.refresh_data(force=True))
            return

        events = sort_events(build_events(cached.events), by_impact_first=False)
        if not events:
            self.status_var.set("Cached data empty; fetching latest calendar...")
            self.last_updated_var.set(
                "Last updated: awaiting first download (empty cache)"
            )
            self.after(200, lambda: self.refresh_data(force=True))
            return

        self.all_events = events
        self.latest_event_date = self._latest_event_date(events)
        self.previous_events_by_uid = {event.uid: event for event in events}
        self._new_event_uids.clear()
        self._changed_event_uids.clear()

        self.apply_filters(status_prefix="Loaded cached calendar")
        self._update_last_updated(
            source=cached.source,
            fetched_at=cached.fetched_at,
            from_cache=cached.from_cache,
        )

        if not self.latest_event_date or date.today() > self.latest_event_date:
            self.status_var.set(
                self._format_status("Cached data is stale; refreshing latest calendar")
            )
            self.after(200, lambda: self.refresh_data(force=True))

    def refresh_data(self, force: bool = False) -> None:
        if self._fetch_thread and self._fetch_thread.is_alive():
            return

        if (
            not force
            and self.latest_event_date is not None
            and date.today() <= self.latest_event_date
        ):
            self.apply_filters(status_prefix="Cached calendar already up to date")
            return

        self._show_spinner(True)
        self.status_var.set("Refreshing data...")
        self._fetch_thread = threading.Thread(target=self._fetch_data, daemon=True)
        self._fetch_thread.start()

    def _fetch_data(self) -> None:
        try:
            result = self.client.fetch()
        except CalendarAPIError as exc:
            self.after(0, lambda: self._handle_error(str(exc)))
            return

        events = build_events(result.events)
        self.after(0, lambda: self._handle_fetch_success(events, result))

    def _handle_fetch_success(
        self, events: list[CalendarEvent], fetch_result
    ) -> None:
        self._fetch_thread = None
        self._show_spinner(False)

        previous_map = self.previous_events_by_uid
        current_map = {event.uid: event for event in events}

        self._new_event_uids = set(current_map) - set(previous_map)
        self._changed_event_uids = {
            uid
            for uid, event in current_map.items()
            if uid in previous_map and self._event_changed(previous_map[uid], event)
        }
        self.previous_events_by_uid = current_map

        self.all_events = sort_events(events, by_impact_first=False)
        self.latest_event_date = self._latest_event_date(self.all_events)
        self.apply_filters(status_prefix="Fetched latest calendar from API")
        self._update_last_updated(
            source=fetch_result.source,
            fetched_at=fetch_result.fetched_at,
            from_cache=fetch_result.from_cache,
        )

    def _handle_error(self, message: str) -> None:
        self._fetch_thread = None
        self._show_spinner(False)
        Messagebox.show_error("Unable to refresh data", message, parent=self)
        self.status_var.set("Failed to refresh data")

    def apply_filters(self, *, status_prefix: str | None = None) -> None:
        events = list(self.all_events)

        active_impacts = [
            impact for impact, var in self.impact_filters.items() if var.get()
        ]
        if active_impacts and len(active_impacts) < len(self.impact_filters):
            events = filter_by_impact(events, active_impacts)

        currencies = self._parse_currencies(self.currency_var.get())
        if currencies:
            events = filter_by_currency(events, currencies)

        query = self.search_var.get().strip()
        if query:
            events = search_events(events, query)

        self.filtered_events = sort_events(events, by_impact_first=False)
        self._populate_tree(self.filtered_events)

        prefix = status_prefix or "Filters applied"
        self.status_var.set(self._format_status(prefix))

    def _populate_tree(self, events: Iterable[CalendarEvent]) -> None:
        self.tree.delete(*self.tree.get_children())
        self._tree_event_map.clear()

        for index, event in enumerate(events):
            tags: list[str] = []
            if event.impact is ImpactLevel.HIGH:
                tags.append("impact-high")
            elif event.impact is ImpactLevel.MEDIUM:
                tags.append("impact-medium")
            elif event.impact is ImpactLevel.LOW:
                tags.append("impact-low")
            if index % 2:
                tags.append("odd-row")
            if event.uid in self._new_event_uids:
                tags.append("event-new")
            elif event.uid in self._changed_event_uids:
                tags.append("event-updated")

            local_dt = event.datetime_local
            item_id = self.tree.insert(
                "",
                END,
                values=(
                    local_dt.strftime("%Y-%m-%d"),
                    local_dt.strftime("%I:%M %p").lstrip("0"),
                    event.currency,
                    event.impact.value,
                    event.title,
                    event.actual or "n/a",
                    event.forecast or "n/a",
                    event.previous or "n/a",
                ),
                tags=tags,
            )
            self._tree_event_map[item_id] = event

    def _on_tree_double_click(self, _event: object) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        item_id = selection[0]
        event = self._tree_event_map.get(item_id)
        if not event:
            return

        Messagebox.show_info(
            "Event Details",
            self._format_event_details(event),
            parent=self,
        )

    def _reset_filters(self) -> None:
        for impact, var in self.impact_filters.items():
            var.set(impact is ImpactLevel.HIGH)
        self.currency_var.set("")
        self.search_var.set("")
        self.apply_filters(status_prefix="Filters reset")

    def _apply_high_impact_shortcut(self) -> None:
        for impact, var in self.impact_filters.items():
            var.set(impact is ImpactLevel.HIGH)
        self.currency_var.set("")
        self.search_var.set("")
        self.apply_filters(status_prefix="High impact spotlight")

    def export_high_impact(self) -> None:
        try:
            output_path = export_markdown(impacts=[ImpactLevel.HIGH])
        except CalendarAPIError as exc:
            Messagebox.show_error("Export failed", str(exc), parent=self)
            return
        Messagebox.show_info("Export complete", f"Saved markdown to\n{output_path}", parent=self)

    def _show_settings_placeholder(self) -> None:
        Messagebox.show_info(
            "Settings",
            "Settings dialog coming soon. Preferences will cover themes, alerts, and export options.",
            parent=self,
        )

    def _show_alerts_placeholder(self) -> None:
        Messagebox.show_info(
            "Alerts",
            "Alert scheduler UI will live here, including custom wav uploads and reminder cadence.",
            parent=self,
        )

    def _on_exit(self) -> None:
        self._cancel_auto_refresh()
        self.destroy()

    def _latest_event_date(self, events: Iterable[CalendarEvent]) -> date | None:
        try:
            return max(event.datetime_local.date() for event in events)
        except ValueError:
            return None

    def _format_status(self, prefix: str) -> str:
        count = len(self.filtered_events)
        plural = "s" if count != 1 else ""
        return f"{prefix} - {count} event{plural} visible"

    def _update_last_updated(
        self, *, source: str, fetched_at: datetime | None, from_cache: bool
    ) -> None:
        self.last_fetch_source = source
        self.last_fetch_timestamp = fetched_at

        origin = "cache" if from_cache else "API"
        if fetched_at:
            display_time = fetched_at.astimezone().strftime("%Y-%m-%d %H:%M %Z")
        else:
            display_time = "unknown"

        self.last_updated_var.set(
            f"Last updated: {display_time} ({origin}) - Source: {source}"
        )

    def _format_event_details(self, event: CalendarEvent) -> str:
        local_time = event.datetime_local.strftime("%Y-%m-%d %I:%M %p %Z").lstrip("0")
        utc_time = event.datetime_utc.strftime("%Y-%m-%d %H:%M UTC")
        lines = [
            event.title,
            "",
            f"Impact: {event.impact.value}",
            f"Currency: {event.currency}",
            f"Local Time: {local_time}",
            f"UTC Time: {utc_time}",
            "",
            f"Actual: {event.actual or 'n/a'}",
            f"Forecast: {event.forecast or 'n/a'}",
            f"Previous: {event.previous or 'n/a'}",
        ]
        return "\n".join(lines)

    def _parse_currencies(self, raw: str) -> Sequence[str]:
        tokens = [token.strip().upper() for token in raw.split(",")]
        return [token for token in tokens if token]

    def _event_changed(
        self, previous: CalendarEvent, current: CalendarEvent
    ) -> bool:
        fields = ("impact", "actual", "forecast", "previous")
        return any(getattr(previous, field) != getattr(current, field) for field in fields)

    def _update_auto_refresh_state(self) -> None:
        if self.auto_refresh_var.get():
            self._schedule_auto_refresh(immediate=True)
        else:
            self._cancel_auto_refresh()

    def _schedule_auto_refresh(self, *, immediate: bool) -> None:
        self._cancel_auto_refresh()
        minutes = self._get_auto_refresh_minutes()
        if minutes <= 0:
            return
        delay_ms = 1000 if immediate else minutes * 60 * 1000
        self._auto_refresh_job = self.after(delay_ms, self._auto_refresh_tick)

    def _auto_refresh_tick(self) -> None:
        self._auto_refresh_job = None
        if not self.auto_refresh_var.get():
            return
        self.refresh_data(force=False)
        self._schedule_auto_refresh(immediate=True)

    def _cancel_auto_refresh(self) -> None:
        if self._auto_refresh_job is not None:
            self.after_cancel(self._auto_refresh_job)
            self._auto_refresh_job = None

    def _get_auto_refresh_minutes(self) -> int:
        try:
            minutes = int(self.auto_refresh_interval_var.get())
        except (TypeError, ValueError):
            minutes = DEFAULT_AUTO_REFRESH_MINUTES
            self.auto_refresh_interval_var.set(str(minutes))
        return max(minutes, 0)


def run() -> None:
    app = ForexNewsApp()
    app.mainloop()


__all__ = ["ForexNewsApp", "run"]
