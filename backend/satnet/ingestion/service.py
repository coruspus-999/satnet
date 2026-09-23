"""TLE ingestion orchestration: fetch -> parse -> validate -> deduplicate.

External-data-friendly: supports real public TLE groups, explicit per-record
failure diagnostics, and retention of the newest record per NORAD id.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from satnet.ingestion.fetcher import TLEFetcher
from satnet.ingestion.parser import TLEParser, ParseReport, ParseFailure

logger = logging.getLogger(__name__)


@dataclass
class IngestionReport:
    """Diagnostics for one ingestion pass (fetch + parse + dedup)."""

    source: str
    total_raw_lines: int
    accepted: int
    rejected: int
    unique_satellites: int
    failed_norad_ids: list[int]

    def __repr__(self) -> str:
        return (
            f"IngestionReport(source={self.source!r}, "
            f"lines={self.total_raw_lines}, accepted={self.accepted}, "
            f"rejected={self.rejected}, unique={self.unique_satellites})"
        )


class TLEIngestionService:
    """Orchestrates ingestion: parse text (or fetch + parse) and deduplicate.

    Retention policy: keep the newest record per NORAD id (by epoch).
    """

    def __init__(
        self, parser: TLEParser | None = None, fetcher: TLEFetcher | None = None
    ) -> None:
        self.parser = parser or TLEParser()
        self.fetcher = fetcher or TLEFetcher()

    # ------------------------------------------------------------------
    # Text parsing (with + without report)
    # ------------------------------------------------------------------

    def parse_text(self, text: str, source: str = "upload") -> list:
        """Parse TLE/3LE text, keeping the newest record per NORAD id."""
        records, _report = self.parser.parse_with_report(text, source)
        return self._dedupe(records)

    def parse_text_with_report(
        self, raw_text: str, source: str = "upload"
    ) -> tuple[list, IngestionReport]:
        """Like ``parse_text``, but returns an ``IngestionReport``.

        Accepted counts successfully parsed-and-validated records.
        Rejected counts records that the parser/validation could not handle.
        """
        parse_report: ParseReport = self.parser.parse_with_report(raw_text, source)

        # Collect NORAD ids that failed at the parse/validation boundary.
        failed_norad_ids: list[int] = []
        for failure in parse_report.failures:
            norad = _norad_id_from_failure_line(failure.line)
            if norad is not None:
                failed_norad_ids.append(norad)

        records = self._dedupe(parse_report.parsed)

        return records, IngestionReport(
            source=source,
            total_raw_lines=parse_report.total_records_attempted,
            accepted=parse_report.parsed,
            rejected=parse_report.failed,
            unique_satellites=len(records),
            failed_norad_ids=sorted(set(failed_norad_ids)),
        )

    # ------------------------------------------------------------------
    # Remote fetch + parse
    # ------------------------------------------------------------------

    async def fetch_and_parse(
        self,
        url: str,
        params: dict | None = None,
        desired_count: int | None = None,
    ) -> list:
        """Fetch a remote TLE group and return the newest record per NORAD id."""
        request_params: dict = dict(params) if params else {}
        if desired_count is not None:
            request_params["NUMSATS"] = str(desired_count)
        raw_text: str = await self.fetcher.fetch(url, request_params)
        return self.parse_text(raw_text, url)

    async def fetch_and_parse_with_report(
        self,
        url: str,
        params: dict | None = None,
        desired_count: int | None = None,
        return_raw_text: bool = False,
    ) -> tuple[list, IngestionReport] | tuple[list, IngestionReport, str]:
        """Fetch a remote TLE group and return records plus a diagnostics report.

        Args:
            url: TLE source URL.
            params: query parameters for the fetch.
            desired_count: approximate number of satellites (NUMSATS param).
            return_raw_text: if True, also return the raw TLE text for
                persistence / offline replay.

        Returns:
            ``(records, report)`` normally; ``(records, report, raw_text)``
            when ``return_raw_text`` is True.
        """
        request_params: dict = dict(params) if params else {}
        if desired_count is not None:
            request_params["NUMSATS"] = str(desired_count)
        raw_text: str = await self.fetcher.fetch(url, request_params)
        records, report = self.parse_text_with_report(raw_text, url)
        if return_raw_text:
            return records, report, raw_text
        return records, report

    async def parse_text_async(self, text: str, source: str = "upload") -> list:
        return self.parse_text(text, source)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _dedupe(records: list) -> list:
        """Keep the newest record per NORAD id (by epoch)."""
        unique: dict[int, object] = {}
        for record in records:
            norad = record.norad_id
            previous = unique.get(norad)
            if previous is None or record.epoch > previous.epoch:
                unique[norad] = record
        count = len(unique)
        logger.debug("TLE ingestion dedup: %d unique satellites from %d records",
                     count, len(records))
        return list(unique.values())


def _norad_id_from_failure_line(line: str) -> int | None:
    """Try to extract a NORAD id from a failed parse line for diagnostic purposes.

    This is a best-effort helper for the ingestion report; it is intentionally
    lenient because failed lines are frequently not valid TLE lines at all.
    """
    try:
        # 2LE line1: NORAD id is in columns 3-7.
        if line.startswith("1 ") and len(line) >= 7:
            return int(line[2:7].strip())
    except (ValueError, IndexError):
        return None
    return None
