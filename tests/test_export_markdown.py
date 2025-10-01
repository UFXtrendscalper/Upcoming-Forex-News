from models import build_events
from src.export_markdown import render_markdown


def test_render_markdown_with_events():
    events = build_events(
        [
            {
                "date": "2025-10-01T12:30:00Z",
                "impact": "High",
                "country": "USD",
                "title": "GDP",
                "actual": "2.9%",
            }
        ]
    )
    markdown = render_markdown(all_events=events, title="Sample")
    assert "# Sample" in markdown
    assert "| GDP" in markdown


def test_render_markdown_no_events_message():
    markdown = render_markdown(all_events=[], title="Empty")
    assert "No scheduled events." in markdown
