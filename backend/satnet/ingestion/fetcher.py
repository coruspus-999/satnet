"""Remote TLE fetching.

Isolated HTTP concern: the parser and the propagator never touch the network.
The HTTP transport is injected so tests can mock it (no live internet in CI).
"""
from __future__ import annotations

from urllib.parse import urlparse

import httpx

from satnet.domain.exceptions import TLEFetchError

DEFAULT_CELESTRAK_URL = "https://celestrak.org/NORAD/elements/gp.php"
_KNOWN_HOSTS = ("celestrak.org", "www.celestrak.org")


def _require_http_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise TLEFetchError(f"Invalid TLE source URL: {url!r}")


class TLEFetcher:
    """Fetch raw TLE text from a remote source.

    ``client_factory`` lets callers (and tests) inject the HTTP transport;
    it must return an async context manager exposing ``get``/``raise_for_status``.
    """

    def __init__(
        self,
        timeout_seconds: float = 20.0,
        client_factory=httpx.AsyncClient,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive.")
        self.timeout_seconds = timeout_seconds
        self.client_factory = client_factory

    async def fetch(self, url: str, params: dict | None = None) -> str:
        _require_http_url(url)
        try:
            timeout = httpx.Timeout(self.timeout_seconds)
            async with self.client_factory(timeout=timeout, follow_redirects=True) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                text = response.text
        except httpx.HTTPError as exc:
            raise TLEFetchError(f"TLE fetch failed: {exc}") from exc
        if not text or not text.strip():
            raise TLEFetchError(f"TLE source returned an empty response: {url}")
        return text
