
from requests import RequestException
import json

import pytest

from src.api_client import CalendarAPIError, CalendarClient
from src.models import build_events


class DummyResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            from requests import HTTPError

            raise HTTPError(f"{self.status_code}")


class DummySession:
    def __init__(self, responses):
        self._responses = list(responses)

    def get(self, url, timeout):
        if self._responses:
            result = self._responses.pop(0)
        else:
            result = RequestException("no stub available")
        if isinstance(result, Exception):
            raise result
        return result


@pytest.fixture
def payload():
    return [
        {
            "date": "2025-10-01T12:30:00Z",
            "impact": "High",
            "country": "USD",
            "title": "GDP",
        }
    ]


def test_fetch_success_with_cache(tmp_path, payload):
    cache_path = tmp_path / "cache.json"
    client = CalendarClient(
        session=DummySession([DummyResponse(payload)]), cache_path=cache_path
    )
    result = client.fetch()
    assert not result.from_cache
    assert build_events(result.events)[0].title == "GDP"
    assert json.loads(cache_path.read_text())


def test_fetch_uses_cache_when_download_fails(tmp_path, payload):
    cache_path = tmp_path / "cache.json"
    client = CalendarClient(
        session=DummySession([DummyResponse(payload)]), cache_path=cache_path
    )
    client.fetch()
    failing_client = CalendarClient(
        session=DummySession([RequestException("boom")] * 3),
        cache_path=cache_path,
    )
    cached = failing_client.fetch()
    assert cached.from_cache


def test_fetch_raises_when_no_cache(tmp_path):
    client = CalendarClient(
        session=DummySession([RequestException("boom")] * 3),
        cache_path=tmp_path / "missing.json",
    )
    with pytest.raises(CalendarAPIError):
        client.fetch()
