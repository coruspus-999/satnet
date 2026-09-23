"""Download a real public TLE group to disk for offline demos and testing.

Usage:
  python examples/fetch_tle_group.py --group stations
  python examples/fetch_tle_group.py --group visual --output tle_group.tle
  python examples/fetch_tle_group.py --group galileo --output galileo.tle

Groups known to parse + validate end-to-end from CelesTrak (gp.php):
  visual, stations, galileo, sarsat  — all accepted with zero rejections.
  noaa, iridium                      — server returns a non-TLE header line
                                      that the parser currently rejects.
  starlink                           — currently 403-forbidden from this
                                      environment's CelesTrak access.

Output file is written relative to the project root by default.
"""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from satnet.core.config import get_settings
from satnet.ingestion.fetcher import TLEFetcher
from satnet.ingestion.service import TLEIngestionService

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_URL = "https://celestrak.org/NORAD/elements/gp.php"
DEFAULT_OUTPUT = "tle_group.tle"


async def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Download a real TLE group from a remote source."
    )
    parser.add_argument(
        "--group",
        default="stations",
        help="TLE group name (e.g. stations, visual, galileo, sarsat, noaa).",
    )
    parser.add_argument(
        "--url",
        default=None,
        help=f"Override the TLE source URL (default: {DEFAULT_URL}).",
    )
    parser.add_argument(
        "--desired",
        type=int,
        default=None,
        help="Approximate number of satellites to request (NUMSATS).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(DEFAULT_OUTPUT),
        help="Write the raw TLE text to this file (default: tle_group.tle).",
    )
    args = parser.parse_args()

    url = args.url or DEFAULT_URL
    fetcher = TLEFetcher(timeout_seconds=90.0)
    service = TLEIngestionService(fetcher=fetcher)

    t0 = time.perf_counter()
    records, report, raw_text = await service.fetch_and_parse_with_report(
        url,
        {"GROUP": args.group, "FORMAT": "tle"},
        args.desired,
        return_raw_text=True,
    )
    elapsed = time.perf_counter() - t0

    logger.info(
        "Fetched group %r: %d unique satellites in %.2fs",
        args.group,
        report.unique_satellites,
        elapsed,
    )
    logger.info(
        "Diagnostics: accepted=%d rejected=%d failed_norad=%s",
        report.accepted,
        report.rejected,
        report.failed_norad_ids,
    )

    out: Path = args.output
    if not out.is_absolute():
        # Resolve relative to the project root (CWD), not the examples/ dir,
        # so that `--output examples/visual_tle.tle` does not become
        # examples/examples/visual_tle.tle.
        out = Path(__file__).resolve().parent.parent / out
    out.parent.mkdir(parents=True, exist_ok=True)
    assert isinstance(raw_text, str), f"raw_text must be str, got {type(raw_text)}"
    out.write_text(raw_text, encoding="utf-8")
    logger.info("Wrote raw TLE text to %s (%d bytes)", out, len(raw_text))
    _print_tle_summary(raw_text, count=12)


def _print_tle_summary(text: str, count: int = 12) -> None:
    """Print a short human-readable summary of the first TLEs in `text`."""
    lines = text.splitlines()
    printed = 0
    for i, line in enumerate(lines):
        if line.startswith("1 ") and printed < count:
            name = lines[i - 1].strip() if i > 0 else "UNKNOWN"
            print(f"  NORAD {line[2:7].strip():>5}  {name[:40]}")
            printed += 1
    if printed == 0:
        print("  (no TLE records found in response)")


if __name__ == "__main__":
    asyncio.run(main())
