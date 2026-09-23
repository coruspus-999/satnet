"""TLE text parsing with recovery from malformed records.

Parse 2-line (2LE) and 3-line (3LE) TLE text into validated SatelliteTLE
records.  Unlike the earlier version this parser never aborts an entire batch
because of a single malformed record: bad lines are recorded as parse failures
and skipped, so a real external group (e.g. a CelesTrak "noaa"/"iridium"
response that starts with a non-TLE header line) degrades gracefully instead
of raising TLEParseError for the whole file.

Public API
----------
parse(text, source, *, with_report=False)
    Returns a list of SatelliteTLE when ``with_report`` is False (default).
    Returns ``(records, report)`` when ``with_report`` is True.

ParsedTLE = SatelliteTLE                 # successful parse
ParseFailure = namedtuple("ParseFailure", ("source_line_index", "line", "reason"))
"""
from __future__ import annotations

from collections import namedtuple
from typing import NamedTuple

from satnet.domain.exceptions import TLEParseError
from satnet.ingestion.validator import TLEValidator


class ParseFailure(NamedTuple):
    source_line_index: int        # 1-based index into the *non-empty* lines
    line: str                     # the offending raw non-empty line (rstrip'd)
    reason: str                   # human-readable reason


class TLEParser:
    """Parse 2LE / 3LE TLE text with per-record failure recovery.

    ``validator`` is injected so tests can swap in a strict/lenient validator
    without reaching into parsing internals.
    """

    def __init__(self, validator: TLEValidator | None = None) -> None:
        self.validator = validator or TLEValidator()

    def parse(self, text: str, source: str = "upload") -> list:
        """Legacy name kept for back-compat; delegates to parse_with_report
        and returns only the records list."""
        records, _report = self.parse_with_report(text, source)
        return records

    def parse_with_report(
        self, text: str, source: str = "upload"
    ) -> tuple[list, "ParseReport"]:
        """Parse ``text`` and return records plus a diagnostics report.

        Malformed lines are **not** a hard error: they are accumulated into
        the report and skipped so the remaining valid records are still
        returned.  A completely empty input is still a hard error.
        """
        lines = [line.rstrip("\r\n") for line in text.splitlines() if line.strip()]
        if not lines:
            raise TLEParseError("TLE input is empty.")

        records: list = []
        failures: list[ParseFailure] = []
        i = 0
        source_line_index = 0  # 1-based index into the filtered lines

        while i < len(lines):
            source_line_index += 1
            line = lines[i]

            if line.startswith("1 "):
                # 2-line TLE: line1 is the current line, line2 must follow.
                if i + 1 >= len(lines):
                    failures.append(
                        ParseFailure(source_line_index, line,
                                     "2LE line 1 is missing its line 2.")
                    )
                    i += 1
                    continue
                name = "UNKNOWN"
                line1 = line
                line2 = lines[i + 1]
                i += 2
            else:
                # 3-line TLE (or a header / junk line we cannot interpret).
                if i + 2 >= len(lines):
                    failures.append(
                        ParseFailure(source_line_index, line,
                                     f"Incomplete TLE record near line "
                                     f"{source_line_index}.")
                    )
                    i += 1
                    continue
                name, line1, line2 = lines[i], lines[i + 1], lines[i + 2]
                i += 3

            try:
                tle = self.validator.validate(name, line1, line2, source)
            except Exception as exc:
                failures.append(
                    ParseFailure(source_line_index, line,
                                 f"Validation rejected: {exc}")
                )
                continue
            records.append(tle)

        return records, ParseReport(
            source=source,
            total_records_attempted=len(lines),
            parsed=len(records),
            failed=len(failures),
            failures=failures,
        )


class ParseReport:
    """Diagnostics for one parse call.

    Attributes
    ----------
    source:
        The ``source`` label passed to parsing (e.g. ``"upload:file.tle"``).
    total_records_attempted:
        Number of non-empty lines inspected as the start of a record.
    parsed:
        Number of successfully validated SatelliteTLE records.
    failed:
        Number of records that could not be parsed/validated.
    failures:
        Ordered list of ``ParseFailure`` for the failed records.
    """

    def __init__(
        self,
        source: str,
        total_records_attempted: int,
        parsed: int,
        failed: int,
        failures: list[ParseFailure],
    ) -> None:
        self.source = source
        self.total_records_attempted = total_records_attempted
        self.parsed = parsed
        self.failed = failed
        self.failures = list(failures)

    def __repr__(self) -> str:
        return (
            f"ParseReport(source={self.source!r}, "
            f"attempted={self.total_records_attempted}, "
            f"parsed={self.parsed}, failed={self.failed})"
        )
