"""Fetcher tests with a fully mocked HTTP transport (no live internet)."""
from __future__ import annotations

import httpx
import pytest

from satnet.domain.exceptions import TLEFetchError
from satnet.ingestion.fetcher import TLEFetcher

VALID_TEXT = (
    "ISS (ZARYA)\n"
    "1 25544U 98067A   25220.51839244  .00017356  00000+0  31752-3 0  9999\n"
    "2 25544  51.6328  47.2102 0002964  72.7432  50.8368 15.50117825522003\n"
)


class FakeResponse:
    def __init__(self, text="", status=200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error", request=None, response=None
            )


class FakeClient:
    """Duck-typed httpx.AsyncClient for transport injection."""

    def __init__(self, response, fail=False, timeout=None, follow_redirects=True):
        self._response = response
        self._fail = fail
        self.last_url = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, params=None):
        if self._fail:
            raise httpx.ConnectError("connection refused")
        self.last_url = url
        return self._response


@pytest.mark.anyio
async def _fetch(fetcher, url="https://celestrak.org/NORAD/elements/gp.php"):
    return await fetcher.fetch(url)


def test_successful_fetch(monkeypatch):
    client = FakeClient(FakeResponse(VALID_TEXT))
    fetcher = TLEFetcher(client_factory=lambda **kw: client)
    import asyncio

    text = asyncio.run(fetcher.fetch("https://celestrak.org/gp.php"))
    assert "25544" in text
    assert client.last_url == "https://celestrak.org/gp.php"


def test_http_error_maps_to_fetch_error():
    fetcher = TLEFetcher(client_factory=lambda **kw: FakeClient(FakeResponse(), fail=True))
    import asyncio

    with pytest.raises(TLEFetchError, match="fetch failed"):
        asyncio.run(fetcher.fetch("https://celestrak.org/gp.php"))


def test_http_status_error_maps_to_fetch_error():
    fetcher = TLEFetcher(client_factory=lambda **kw: FakeClient(FakeResponse(status=404)))
    import asyncio

    with pytest.raises(TLEFetchError):
        asyncio.run(fetcher.fetch("https://celestrak.org/gp.php"))


def test_timeout_maps_to_fetch_error():
    class TimeoutClient(FakeClient):
        async def get(self, url, params=None):
            raise httpx.ReadTimeout("timed out")

    fetcher = TLEFetcher(client_factory=lambda **kw: TimeoutClient(FakeResponse()))
    import asyncio

    with pytest.raises(TLEFetchError, match="timed out"):
        asyncio.run(fetcher.fetch("https://celestrak.org/gp.php"))


def test_empty_response_rejected():
    fetcher = TLEFetcher(client_factory=lambda **kw: FakeClient(FakeResponse("   \n")))
    import asyncio

    with pytest.raises(TLEFetchError, match="empty"):
        asyncio.run(fetcher.fetch("https://celestrak.org/gp.php"))


def test_invalid_url_rejected_without_network():
    fetcher = TLEFetcher()
    import asyncio

    for bad in ("ftp://x", "not-a-url", ""):
        with pytest.raises(TLEFetchError, match="Invalid TLE source URL"):
            asyncio.run(fetcher.fetch(bad))


def test_invalid_timeout_rejected():
    with pytest.raises(ValueError):
        TLEFetcher(timeout_seconds=0)
