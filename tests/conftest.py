"""Shared deterministic TLE fixtures for offline tests (no live network)."""
from __future__ import annotations

import pytest

ISS_TLE = """ISS (ZARYA)
1 25544U 98067A   25220.51839244  .00017356  00000+0  31752-3 0  9999
2 25544  51.6328  47.2102 0002964  72.7432  50.8368 15.50117825522003
"""

ISS_LINE1 = ISS_TLE.splitlines()[1]
ISS_LINE2 = ISS_TLE.splitlines()[2]


def recompute_checksum(line: str) -> str:
    """Recompute the TLE checksum digit for a patched 69-char line."""
    body = line[:68]
    total = sum(int(c) for c in body if c.isdigit()) + body.count("-")
    return body + str(total % 10)


def tle_with_norad(line1: str, line2: str, norad_id: int) -> tuple[str, str]:
    """Patch the NORAD id into both lines and fix checksums (test helper)."""
    id_field = f"{norad_id:5d}"
    line1 = recompute_checksum(line1[:2] + id_field + line1[7:])
    line2 = recompute_checksum(line2[:2] + id_field + line2[7:])
    return line1, line2


HST_LINE1, HST_LINE2 = tle_with_norad(ISS_LINE1, ISS_LINE2, 20580)
HST_TLE = f"HST\n{HST_LINE1}\n{HST_LINE2}\n"


@pytest.fixture
def iss_tle_text() -> str:
    return ISS_TLE


@pytest.fixture
def two_satellite_tle_text() -> str:
    return ISS_TLE + HST_TLE
