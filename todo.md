# Tkinter Forex Calendar App TODO

## 1. Environment & Project Setup
- ✅ Create project structure: `src/`, `data/`, `exports/`, `tests/`, `docs/`.
- ✅ Initialize git repository if needed and add `.gitignore` entries for `env/`, `__pycache__/`, and export artifacts.
- ✅ Create virtual environment `env` with `python -m venv env`.
- ✅ Activate venv (`env\Scripts\Activate.ps1`) and upgrade pip/setuptools.
- ✅ Install dependencies: `ttkbootstrap`, `requests` (or `httpx`), `python-dateutil`, and `pandas` (optional for data shaping).
- ✅ Capture exact dependency versions in `requirements.txt`.

## 2. Data Acquisition & Validation
- [ ] Implement `src/api_client.py` with function to download JSON from https://nfs.faireconomy.media/ff_calendar_thisweek.json using a configurable URL.
- [ ] Add retry/backoff and timeout handling for network errors.
- [ ] Persist last successful payload to `data/latest_calendar.json` for offline fallback.
- [ ] Validate response schema; log/notify if unexpected fields or empty payload.
- [ ] Normalize timestamp fields to Python `datetime` objects (UTC) and local timezone if helpful.

## 3. Data Modeling & Filtering
- [ ] Define dataclasses or lightweight models in `src/models.py` for calendar events (date, time, currency, impact, event, actual, forecast, previous, etc.).
- [ ] Implement helper functions for grouping events by calendar day and for filtering by impact (`High`, `Medium`, `Low`, `Holiday`).
- [ ] Add free-text search/filter helpers (currency, keyword) to support UI enhancements.
- [ ] Provide sorting utilities (e.g., time within day, impact severity).

## 4. Markdown Export Pipeline
- [ ] Create `src/export_markdown.py` to generate Markdown mirroring `Upcoming_News.md` structure.
- [ ] Ensure export groups events by day with `## Day` headings and tables matching column order.
- [ ] Restrict primary export to High impact events while preserving all columns; include "No scheduled events." when empty.
- [ ] Save output to `exports/high_impact_news.md` with timestamped filename option.
- [ ] Add CLI entry point (e.g., `python -m src.export_markdown --impact High`) for scripted runs.

## 5. UI Architecture (Tkinter + ttkbootstrap)
- [ ] Initialize main application in `src/app.py` using ttkbootstrap `Window(theme="cyborg")`.
- [ ] Build layout with frames: header (controls), content (Treeview for calendar), footer (status bar).
- [ ] Configure styles (fonts, row height, alternating row colors) matching theme aesthetics.
- [ ] Add menu bar with actions: Refresh Data, Export High Impact Markdown, Settings, Exit.

## 6. Data Presentation Components
- [ ] Populate Treeview with columns Time, Currency, Impact, Event, Actual, Forecast, Previous.
- [ ] Implement impact-color tagging (e.g., red for High, yellow for Medium) consistent with cyborg palette.
- [ ] Provide detail panel or modal showing extended description on double-click.
- [ ] Display last updated timestamp and source URL in status bar.

## 7. Filtering & User Controls
- [ ] Add impact filter buttons/checklist (High/Medium/Low/Holiday) with toggle state.
- [ ] Include currency dropdown and keyword search entry; filter Treeview in real-time.
- [ ] Supply date range selector (current week by default) with navigation to previous/next week if API supports.
- [ ] Offer quick "High Impact Only" shortcut button and export trigger.
- [ ] Add reset filters control.

## 8. Background Tasks & Refresh
- [ ] Implement async-friendly refresh using `after()` loop or `threading` to avoid blocking UI during fetches.
- [ ] Show progress indicator/spinner while downloading.
- [ ] Cache latest dataset and diff against previous to highlight newly added/changed events.
- [ ] Add auto-refresh interval setting (e.g., every 30 or 60 minutes) with toggle.

## 9. Configuration & Settings
- [ ] Store user preferences (selected filters, auto-refresh interval, window geometry) in `config.json` under `data/`.
- [ ] Load settings at startup and persist on exit.
- [ ] Allow user to change export directory and API URL via settings dialog.

## 10. Logging & Error Handling
- [ ] Configure logging to file (`logs/app.log`) with rotation.
- [ ] Display non-blocking toast/dialog for errors with option to retry fetch.
- [ ] Gracefully handle network failures by prompting to use cached data.

## 11. Testing & Tooling
- [ ] Add unit tests for data parsing, filtering, and markdown export using `pytest`.
- [ ] Mock HTTP responses to ensure deterministic tests.
- [ ] Include script `make_export.ps1` or `tasks.py` for running exports and linting.
- [ ] Consider `ruff` or `flake8` for linting; add pre-commit hooks if desired.

## 12. Documentation & Packaging
- [ ] Document setup and usage in `README.md` (venv activation, running app, exporting markdown).
- [ ] Provide screenshots or GIF of the UI once implemented.
- [ ] Add `__main__.py` or console entry point for `python -m src` launch.
- [ ] Prepare simple packaging instructions (e.g., `pyinstaller` spec) if distribution is needed.

## 13. Future Enhancements (Backlog)
- [ ] Integrate additional data sources (economic news sentiment, historical outcomes).
- [ ] Add notifications (desktop or email) for upcoming high-impact events within user-defined lead time.
- [ ] Provide CSV export and calendar (.ics) integration.
- [ ] Offer dark/light theme toggle and custom theme overrides.
- [ ] Include analytics view summarizing counts by currency/impact over time.
