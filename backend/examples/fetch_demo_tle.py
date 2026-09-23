"""Download real, live TLE data from CelesTrak for offline demo / testing.

This script exercises the project's ingestion service against the live network
rather than against any bundled fixture, so it demonstrates that the pipeline
works for *other* inputs besides the training/`fixtures/` data.

Usage:
  cd backend
  PYTHONPATH=src python examples/fetch_demo_tle.py
  PYTHONPATH=src python examples/fetch_demo_tle.py --group visual --output tle_visual.tle

Groups known to parse + validate cleanly from CelesTrak (gp.php, tle format):
  visual, stations, galileo, sarsat - all accepted with zero rejections.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from satnet.ingestion.fetcher import TLEFetcher
from satnet.ingestion.parser import TLEParser
from satnet.ingestion.service import TLEIngestionService

logger = logging.getLogger(__name__)


def _print_tle_summary(text: str, count: int = 12) -> None:
    lines = text.splitlines()
    printed = 0
    for i, line in enumerate(lines):
        if line.startswith("1 ") and printed < count:
            name = lines[i - 1].strip() if i > 0 else "UNKNOWN"
            print(f"  NORAD {line[2:7].strip():>5}  {name[:40]}")
            printed += 1
    if printed == 0:
        print("  (no TLE records found in response)")


async def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Download live TLE data for demo.")
    parser.add_argument("--group", default="visual", help="TLE group name.")
    parser.add_argument("--output", type=Path, default=Path("tle_demo.tle"), help="Output file.")
    parser.add_argument("--url", default=None, help="Override the TLE source URL.")
    args = parser.parse_args()

    url = args.url or "https://celestrak.org/NORAD/elements/gp.php"
    fetcher = TLEFetcher(timeout_seconds=90.0)
    service = TLEIngestionService(fetcher=fetcher)

    t0 = time.perf_counter()
    records, report, raw_text = await service.fetch_and_parse_with_report(
        url,
        {"GROUP": args.group, "FORMAT": "tle"},
        desired_count=30,
        return_raw_text=True,
    )
    elapsed = time.perf_counter() - t0

    print(f"Fetched group {args.group!r}: {report.unique_satellites} satellites in {elapsed:.2f}s")
    print(f"Accepted: {report.accepted}, Rejected: {report.rejected}")
    print(f"First few records:")
    _print_tle_summary(raw_text, count=12)

    out = args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(raw_text, encoding="utf-8")
    print(f"Wrote raw TLE text to {out} ({len(raw_text)} bytes, {report.unique_satellites} satellites)")


if __name__ == "__main__":
    asyncio.run(main())
