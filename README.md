# Tkinter Forex Impact Monitor

A desktop application built with Tkinter and ttkbootstrap for monitoring the Forex Factory calendar. The app fetches high-impact economic events, displays them in a filterable Treeview, and offers quick exports, alerts, and offline resilience.

![UI Screenshot Placeholder](docs/screenshot-placeholder.png)

## Quick Start

### Prerequisites
- Python 3.11+
- Git (optional, for cloning)

### Setup
```powershell
# Clone and enter the project
git clone https://github.com/UFXtrendscalper/Upcoming-Forex-News.git
cd Upcoming-Forex-News

# Create a virtual environment
env\Scripts\python -m venv env

# Activate the environment (PowerShell)
./env/Scripts/Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### Running the App
```powershell
# Launch the Tkinter application
python -m src
```

### Export High-Impact Markdown
```powershell
# CLI export (high impact only)
python -m src.export_markdown --impact High
```
Generated reports are stored in `exports/` (you can configure the destination in Settings).

### Running Tests
```powershell
python tasks.py test
```
Pytest covers model utilities, the API client, and markdown export rendering.

## Features
- Auto-refreshing, cyborg-themed UI built with ttkbootstrap.
- Impact, currency, and keyword filtering with quick “High Impact Only” reset.
- Markdown exporter mirroring the `Upcoming_News.md` structure.
- Alert scheduler with snooze, custom `.wav` support, and reminder offsets at 60/30/15/5 minutes.
- Cached dataset fallback and retry prompt when network refresh fails.
- Persistent preferences (`data/config.json`) for API URL, export directory, filters, geometry, alerts.
- Logging to `logs/app.log` via rotating file handler.

## Configuration
- All user preferences live in `data/config.json` (ignored by git).
- Settings dialog (Tools → Settings) lets you change API endpoint (+ refresh) and default export directory.
- Alerts dialog manages reminder offsets, snooze length, and custom wav file.

## Packaging Notes
- For single-file distribution, start with [`pyinstaller`](https://pyinstaller.org/):
  ```powershell
  pyinstaller --name forex-monitor --windowed --noconfirm src\__main__.py
  ```
  Adjust the spec to bundle `data/` defaults and `logs/` directory as needed.
- Include `README.md`, `requirements.txt`, and ensure target systems have the appropriate VC runtime for Python 3.11+.

## Visuals
- Replace `docs/screenshot-placeholder.png` with an actual UI screenshot or short animated GIF (e.g., using ShareX or ScreenToGif) to showcase filtering/export actions.

## Contributing
1. Run `python -m pytest` before submitting changes.
2. For additional tasks (packaging, linting), add commands to `tasks.py`.
3. Open issues or PRs with a clear description of your updates.

## License
This project follows the repository license (see `LICENSE` if present).
