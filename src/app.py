"""Tkinter + ttkbootstrap desktop application shell for forex news."""

from __future__ import annotations

import platform
import threading
import tkinter as tk
from datetime import date, datetime, timedelta
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Iterable, Sequence

from ttkbootstrap import Window
from ttkbootstrap.constants import BOTH, END, LEFT, RIGHT, X
from ttkbootstrap.dialogs import Messagebox
from ttkbootstrap.widgets import Button, Checkbutton, Entry, Frame, Label

from .api_client import CalendarAPIError, CalendarClient, DEFAULT_CALENDAR_URL
from .export_markdown import export_markdown, build_default_output_path
from .config import ConfigManager, AppPreferences, AlertPreferences
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

        self.config_manager = ConfigManager()
        preferences = self.config_manager.load()

        self.client = CalendarClient(base_url=preferences.api_url or DEFAULT_CALENDAR_URL)
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
        self.export_directory: Path | None = None

        self.alert_manager = AlertManager(self, preferences.alerts)

        self._build_styles()
        self._build_menu()
        self._build_layout()

        self._applying_preferences = True
        self._apply_preferences(preferences)
        self._applying_preferences = False

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
            label="Settings", command=self._show_settings_dialog
        )
        tools_menu.add_command(
            label="Alerts", command=self.alert_manager.show_settings_dialog
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

        Checkbutton(
            parent,
            text="Alerts",
            variable=self.alert_manager.enabled_var,
            bootstyle="round-toggle",
            command=self.alert_manager.toggle,
        ).pack(side=LEFT, padx=(16, 4))

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

    def _apply_preferences(self, prefs: AppPreferences) -> None:
        try:
            self.geometry(f"{prefs.window_width}x{prefs.window_height}")
        except Exception:
            pass

        for impact, var in self.impact_filters.items():
            var.set(impact.value in prefs.impacts)
        if not any(var.get() for var in self.impact_filters.values()):
            self.impact_filters[ImpactLevel.HIGH].set(True)

        self.currency_var.set(", ".join(prefs.currencies))
        self.search_var.set(prefs.search_text)
        self.auto_refresh_var.set(prefs.auto_refresh_enabled)
        self.auto_refresh_interval_var.set(str(prefs.auto_refresh_minutes))

        if prefs.export_directory:
            self.export_directory = Path(prefs.export_directory).expanduser()
        else:
            self.export_directory = None

        self.alert_manager.update_preferences(prefs.alerts)

        self._cancel_auto_refresh()
        if self.auto_refresh_var.get():
            self._schedule_auto_refresh(immediate=True)

    def _collect_preferences(self) -> AppPreferences:
        width = max(self.winfo_width(), 600)
        height = max(self.winfo_height(), 480)
        impacts = [impact.value for impact, var in self.impact_filters.items() if var.get()]
        if not impacts:
            impacts = [ImpactLevel.HIGH.value]
        currencies = self._parse_currencies(self.currency_var.get())
        alerts = self.alert_manager.get_preferences()
        return AppPreferences(
            window_width=width,
            window_height=height,
            impacts=impacts,
            currencies=currencies,
            search_text=self.search_var.get().strip(),
            auto_refresh_enabled=self.auto_refresh_var.get(),
            auto_refresh_minutes=self._get_auto_refresh_minutes(),
            export_directory=str(self.export_directory) if self.export_directory else None,
            api_url=self.client.base_url,
            alerts=alerts,
        )

    def save_preferences(self) -> None:
        if getattr(self, "_applying_preferences", False):
            return
        try:
            prefs = self._collect_preferences()
            self.config_manager.save(prefs)
        except Exception:
            pass

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
        self.alert_manager.reload_events(self.all_events)

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
        self.alert_manager.reload_events(self.all_events)

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
        self.save_preferences()

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
            export_dir = self.export_directory
            output_path = None
            if export_dir:
                export_dir.mkdir(parents=True, exist_ok=True)
                output_path = build_default_output_path(
                    impacts=[ImpactLevel.HIGH], export_dir=export_dir
                )
            output_path = export_markdown(
                impacts=[ImpactLevel.HIGH], output_path=output_path
            )
        except CalendarAPIError as exc:
            Messagebox.show_error("Export failed", str(exc), parent=self)
            return
        Messagebox.show_info("Export complete", f"Saved markdown to\n{output_path}", parent=self)

    def _show_settings_dialog(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Application Settings")
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)

        api_var = tk.StringVar(value=self.client.base_url)
        export_var = tk.StringVar(
            value=str(self.export_directory) if self.export_directory else ""
        )

        Frame(dialog, height=10).pack()

        Label(dialog, text="Calendar API URL").pack(anchor="w", padx=16)
        Entry(dialog, textvariable=api_var, width=48).pack(fill=X, padx=16)

        Label(dialog, text="Export directory").pack(anchor="w", padx=16, pady=(12, 0))
        export_frame = Frame(dialog)
        export_frame.pack(fill=X, padx=16)
        Entry(export_frame, textvariable=export_var, width=40).pack(side=LEFT, fill=X, expand=True)
        Button(
            export_frame,
            text="Browse",
            command=lambda: self._choose_export_directory(export_var),
        ).pack(side=LEFT, padx=(8, 0))
        Button(
            export_frame,
            text="Clear",
            command=lambda: export_var.set(""),
        ).pack(side=LEFT, padx=(4, 0))

        button_frame = Frame(dialog)
        button_frame.pack(fill=X, padx=16, pady=16)
        Button(button_frame, text="Cancel", command=dialog.destroy).pack(side=RIGHT)
        Button(
            button_frame,
            text="Save",
            bootstyle="primary",
            command=lambda: self._apply_general_settings(dialog, api_var.get(), export_var.get()),
        ).pack(side=RIGHT, padx=(0, 8))

        dialog.wait_window()

    def _choose_export_directory(self, var: tk.StringVar) -> None:
        path = filedialog.askdirectory(title="Select export directory")
        if path:
            var.set(path)

    def _apply_general_settings(self, dialog: tk.Toplevel, api_url: str, export_dir: str) -> None:
        api_value = api_url.strip()
        export_value = export_dir.strip()

        if api_value:
            self.client = CalendarClient(base_url=api_value)
        else:
            self.client = CalendarClient(base_url=DEFAULT_CALENDAR_URL)

        if export_value:
            path_obj = Path(export_value).expanduser()
            path_obj.mkdir(parents=True, exist_ok=True)
            self.export_directory = path_obj
        else:
            self.export_directory = None

        self.save_preferences()
        dialog.destroy()
        self.status_var.set(self._format_status("Settings updated"))

    def _on_exit(self) -> None:
        self._cancel_auto_refresh()
        self.alert_manager.cancel_all()
        self.save_preferences()
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
        self.save_preferences()

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


class AlertManager:
    """Manage scheduling and presentation of high-impact alerts."""

    def __init__(self, app: ForexNewsApp, prefs: AlertPreferences | None = None) -> None:
        self.app = app
        prefs = prefs or AlertPreferences()
        self.enabled_var = tk.BooleanVar(master=app, value=prefs.enabled)
        self.snooze_minutes = tk.IntVar(master=app, value=prefs.snooze_minutes)
        self.reminder_offsets: dict[ImpactLevel, list[int]] = {
            ImpactLevel.HIGH: list(prefs.offsets or [60, 30, 15, 5])
        }
        self.custom_sound_path: Path | None = (Path(prefs.sound_path) if prefs.sound_path else None)
        self._jobs: dict[tuple[str, str], str] = {}

    def update_preferences(self, prefs: AlertPreferences) -> None:
        self.enabled_var.set(prefs.enabled)
        self.snooze_minutes.set(prefs.snooze_minutes)
        self.reminder_offsets[ImpactLevel.HIGH] = list(prefs.offsets or [60, 30, 15, 5])
        self.custom_sound_path = Path(prefs.sound_path) if prefs.sound_path else None
        if self.enabled_var.get():
            self.reload_events(self.app.all_events)
        else:
            self.cancel_all()

    def get_preferences(self) -> AlertPreferences:
        offsets = self.reminder_offsets.get(ImpactLevel.HIGH, [])
        normalized = sorted({abs(value) for value in offsets}, reverse=True)
        return AlertPreferences(
            enabled=self.enabled_var.get(),
            offsets=normalized or [60, 30, 15, 5],
            snooze_minutes=max(1, self.snooze_minutes.get()),
            sound_path=str(self.custom_sound_path) if self.custom_sound_path else None,
        )

    def toggle(self) -> None:
        if self.enabled_var.get():
            self.reload_events(self.app.all_events)
        else:
            self.cancel_all()
        self.app.save_preferences()

    def reload_events(self, events: Iterable[CalendarEvent]) -> None:
        self.cancel_all()
        if not self.enabled_var.get():
            return
        for event in events:
            offsets = self.reminder_offsets.get(event.impact)
            if not offsets:
                continue
            for offset in offsets:
                self._schedule_event(event, offset)

    def cancel_all(self) -> None:
        for job_id in self._jobs.values():
            try:
                self.app.after_cancel(job_id)
            except Exception:
                pass
        self._jobs.clear()

    def show_settings_dialog(self) -> None:
        dialog = tk.Toplevel(self.app)
        dialog.title("Alert Settings")
        dialog.transient(self.app)
        dialog.grab_set()
        dialog.resizable(False, False)

        offsets_var = tk.StringVar(
            value=", ".join(str(value) for value in self.reminder_offsets[ImpactLevel.HIGH])
        )
        sound_var = tk.StringVar(
            value=str(self.custom_sound_path) if self.custom_sound_path else ""
        )
        snooze_var = tk.StringVar(value=str(self.snooze_minutes.get()))

        Frame(dialog, height=10).pack()
        Label(dialog, text="High impact reminder offsets (minutes)").pack(anchor="w", padx=16)
        Entry(dialog, textvariable=offsets_var, width=32).pack(fill=X, padx=16)

        Label(dialog, text="Snooze duration (minutes)").pack(anchor="w", padx=16, pady=(12, 0))
        Entry(dialog, textvariable=snooze_var, width=12).pack(fill=X, padx=16)

        sound_frame = Frame(dialog)
        sound_frame.pack(fill=X, padx=16, pady=(12, 0))
        Label(sound_frame, text="Alert sound (.wav)").pack(anchor="w")
        sound_entry = Entry(sound_frame, textvariable=sound_var, width=40)
        sound_entry.pack(side=LEFT, fill=X, expand=True, pady=(4, 0))
        Button(
            sound_frame,
            text="Browse",
            command=lambda: self._choose_sound(sound_var),
        ).pack(side=LEFT, padx=(8, 0))
        Button(
            sound_frame,
            text="Clear",
            command=lambda: sound_var.set(""),
        ).pack(side=LEFT, padx=(4, 0))

        button_frame = Frame(dialog)
        button_frame.pack(fill=X, padx=16, pady=16)
        Button(button_frame, text="Cancel", command=dialog.destroy).pack(side=RIGHT)
        Button(
            button_frame,
            text="Save",
            bootstyle="primary",
            command=lambda: self._apply_settings(dialog, offsets_var, snooze_var, sound_var),
        ).pack(side=RIGHT, padx=(0, 8))

        dialog.wait_window()

    def _apply_settings(
        self,
        dialog: tk.Toplevel,
        offsets_var: tk.StringVar,
        snooze_var: tk.StringVar,
        sound_var: tk.StringVar,
    ) -> None:
        try:
            offsets = [
                int(value)
                for value in offsets_var.get().split(",")
                if value.strip()
            ]
        except ValueError:
            Messagebox.show_error("Invalid offsets", "Offsets must be integers.", parent=self.app)
            return

        if not offsets:
            Messagebox.show_error("No offsets", "Provide at least one offset.", parent=self.app)
            return

        try:
            snooze_minutes = int(snooze_var.get())
        except ValueError:
            Messagebox.show_error(
                "Invalid snooze",
                "Snooze duration must be an integer.",
                parent=self.app,
            )
            return

        path_value = sound_var.get().strip()
        if path_value:
            candidate = Path(path_value)
            if not candidate.exists() or candidate.suffix.lower() != ".wav":
                Messagebox.show_error(
                    "Invalid sound",
                    "Select an existing .wav file.",
                    parent=self.app,
                )
                return
            self.custom_sound_path = candidate
        else:
            self.custom_sound_path = None

        self.reminder_offsets[ImpactLevel.HIGH] = sorted({abs(offset) for offset in offsets}, reverse=True)
        self.snooze_minutes.set(max(1, abs(snooze_minutes)))
        dialog.destroy()
        self.reload_events(self.app.all_events)
        self.app.save_preferences()

    def _choose_sound(self, sound_var: tk.StringVar) -> None:
        path = filedialog.askopenfilename(
            title="Select alert sound",
            filetypes=[("WAV files", "*.wav"), ("All files", "*.*")],
        )
        if path:
            sound_var.set(path)

    def _schedule_event(
        self,
        event: CalendarEvent,
        offset_minutes: int,
        *,
        label: str | None = None,
        absolute_time: datetime | None = None,
    ) -> None:
        if label is None:
            label = f"offset-{offset_minutes}"

        if absolute_time is None:
            reminder_time = event.datetime_local - timedelta(minutes=offset_minutes)
        else:
            reminder_time = absolute_time

        tz_now = datetime.now(event.datetime_local.tzinfo or datetime.now().astimezone().tzinfo)
        delay_seconds = (reminder_time - tz_now).total_seconds()
        if delay_seconds <= 1:
            return

        job_id = self.app.after(
            int(delay_seconds * 1000),
            lambda e=event, lbl=label: self._trigger_alert(e, lbl),
        )
        self._jobs[(event.uid, label)] = job_id

    def _schedule_snooze(self, event: CalendarEvent) -> None:
        minutes = max(1, self.snooze_minutes.get())
        tz_now = datetime.now(event.datetime_local.tzinfo or datetime.now().astimezone().tzinfo)
        label = f"snooze-{datetime.now().timestamp()}"
        reminder_time = tz_now + timedelta(minutes=minutes)
        self._schedule_event(event, minutes, label=label, absolute_time=reminder_time)

    def _trigger_alert(self, event: CalendarEvent, label: str) -> None:
        job = self._jobs.pop((event.uid, label), None)
        if job is None or not self.enabled_var.get():
            return

        self._play_sound()
        self._show_alert_popup(event)

    def _show_alert_popup(self, event: CalendarEvent) -> None:
        popup = tk.Toplevel(self.app)
        popup.title("High Impact Reminder")
        popup.transient(self.app)
        popup.grab_set()
        popup.resizable(False, False)
        popup.attributes("-topmost", True)

        Frame(popup, height=10).pack()
        Label(
            popup,
            text=f"{event.title} ({event.currency})",
            font=("Segoe UI", 12, "bold"),
        ).pack(padx=16, pady=(0, 6))

        local_time = event.datetime_local.strftime("%Y-%m-%d %I:%M %p %Z").lstrip("0")
        Label(popup, text=f"Scheduled for {local_time}").pack(padx=16)

        Frame(popup, height=12).pack()
        button_frame = Frame(popup)
        button_frame.pack(fill=X, padx=16, pady=(0, 16))

        Button(
            button_frame,
            text="Snooze",
            command=lambda: self._on_snooze(event, popup),
            bootstyle="secondary",
        ).pack(side=LEFT)

        Button(
            button_frame,
            text="Dismiss",
            command=popup.destroy,
            bootstyle="primary",
        ).pack(side=RIGHT)

        # After forcing topmost, allow focus to return to app later
        popup.after(3000, lambda: popup.attributes("-topmost", False))

    def _on_snooze(self, event: CalendarEvent, popup: tk.Toplevel) -> None:
        popup.destroy()
        self._schedule_snooze(event)

    def _play_sound(self) -> None:
        if self.custom_sound_path:
            try:
                if platform.system() == "Windows":
                    import winsound

                    winsound.PlaySound(
                        str(self.custom_sound_path),
                        winsound.SND_FILENAME | winsound.SND_ASYNC,
                    )
                    return
            except Exception:
                pass
        try:
            if platform.system() == "Windows":
                import winsound

                winsound.MessageBeep()
            else:
                self.app.bell()
        except Exception:
            pass


def run() -> None:
    app = ForexNewsApp()
    app.mainloop()


__all__ = ["ForexNewsApp", "run"]

