# Future Enhancements Backlog

This document tracks feature ideas that extend beyond the current release. Each item includes a short rationale and suggested implementation notes.

## Desktop/Email Notifications
- **Goal:** Notify the user when high-impact events are approaching within configurable lead times.
- **Approach:**
  - Reuse the existing `AlertManager` scheduling layer and add integrations for Windows toast notifications (e.g., via `win10toast` or `plyer`) and/or SMTP email.
  - Expose lead-time configuration in the alerts dialog alongside the existing reminder offsets and snooze controls.
  - Add preference flags to `data/config.json` to enable/disable notification channels.

## Theme Toggle & Custom Styling
- **Goal:** Allow switching between ttkbootstrap themes (cyborg, flatly, etc.) and overriding fonts/colors.
- **Approach:**
  - Expose a theme selector in Settings and persist the selection via `ConfigManager`.
  - Apply theme changes using `self.style.theme_use(new_theme)` and refresh widget styles for Treeview tags.
  - Optional: provide a lightweight CSS-like overrides file for advanced customization.

## Analytics Dashboard
- **Goal:** Summarize event counts by currency and impact to highlight busy periods.
- **Approach:**
  - Add a new tab/panel using ttkbootstrap Notebook with charts (matplotlib or plotly) and summary tables.
  - Derive aggregations from cached events; support timeframe filters (current week, next week, custom range).
  - Persist chart preferences (selected metrics, timeframe) in `data/config.json`.

## Export Enhancements
- **Goal:** Support additional export formats (CSV, ICS calendar) for integration with external tools.
- **Approach:**
  - Convert `CalendarEvent` dataclasses to dictionaries and feed `pandas` (already optional dependency) for CSV.
  - Use `icalendar` or `ics` library to build `.ics` files with event reminders.
  - Extend `tasks.py` with commands to produce each format.

## Localization & Multi-language Support
- **Goal:** Make the interface translatable and format dates/times per locale.
- **Approach:**
  - Extract all user-facing strings into a localization dictionary or `gettext` catalogs.
  - Use `babel` or Python's `locale` module for formatting dates/times and numbers.
  - Persist the selected language in `config.json` and provide a selector in Settings.
