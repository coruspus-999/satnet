"""Tests for the TLE parser's graceful-recovery parsing behavior.

The parser now never aborts an entire batch because of one bad record: bad
lines are recorded as parse failures and skipped, so real external groups
(e.g. CelesTrak responses with non-TLE header lines) degrade gracefully.
Empty input is still a hard error.
"""
from __future__ import annotations

import pytest

from satnet.domain.exceptions import TLEParseError, TLEValidationError
from satnet.ingestion.parser import TLEParser, ParseFailure

ISS = (
    "ISS (ZARYA)\n"
    "1 25544U 98067A   25220.51839244  .00017356  00000+0  31752-3 0  9999\n"
    "2 25544  51.6328  47.2102 0002964  72.7432  50.8368 15.50117825522003\n"
)


def test_parse_three_line() -> None:
    records = TLEParser().parse(ISS)
    assert len(records) == 1
    assert records[0].name == "ISS (ZARYA)"
    assert records[0].norad_id == 25544


def test_parse_two_line_defaults_unknown_name() -> None:
    lines = ISS.splitlines()[1:]
    records = TLEParser().parse("\n".join(lines))
    assert len(records) == 1
    assert records[0].norad_id == 25544
    assert records[0].name == "UNKNOWN"


def test_parse_multiple_records() -> None:
    from tests.conftest import HST_TLE

    records = TLEParser().parse(ISS + HST_TLE)
    assert len(records) == 2
    assert {r.norad_id for r in records} == {25544, 20580}


def test_empty_input_raises() -> None:
    with pytest.raises(TLEParseError):
        TLEParser().parse("")
    with pytest.raises(TLEParseError):
        TLEParser().parse("\n \n")


def test_orphan_line1_recovers_and_reports_failure() -> None:
    """A 2LE line-1 with no line-2 is reported as a failure, not raised."""
    text = ISS.splitlines()[1] + "\n"  # only the line-1, no line-2
    records, report = TLEParser().parse_with_report(text)
    assert len(records) == 0
    assert report.failed == 1
    assert report.parsed == 0
    assert report.total_records_attempted == 1
    failure = report.failures[0]
    assert isinstance(failure, ParseFailure)
    assert "line 2" in failure.reason


def test_truncated_record_recovers_and_reports_failure() -> None:
    """A record whose trailing line(s) are missing is reported, not raised."""
    # A name line followed by only one TLE line is an incomplete 3LE record.
    text = "MYSAT\n" + ISS.splitlines()[1]
    records, report = TLEParser().parse_with_report(text)
    assert len(records) == 0
    assert report.failed == 2
    assert report.parsed == 0
    assert report.total_records_attempted == 2
    reasons = [f.reason for f in report.failures]
    assert any("Incomplete" in r for r in reasons)
    assert any("line 2" in r for r in reasons)


def test_corrupt_fields_reported_not_raised() -> None:
    """A TLE with corrupted numeric fields is reported as a parse/validation failure."""
    from tests.conftest import ISS_LINE1, ISS_LINE2, recompute_checksum

    corrupt_line2 = recompute_checksum(ISS_LINE2[:52] + "AB.CDEFG" + ISS_LINE2[63:])
    text = f"ISS (ZARYA)\n{ISS_LINE1}\n{corrupt_line2}\n"
    records, report = TLEParser().parse_with_report(text)
    assert len(records) == 0
    assert report.failed == 1
    assert report.parsed == 0
    assert report.total_records_attempted == 3
    assert any(
        "checksum" in f.reason.lower()
        or "rejected" in f.reason.lower()
        or "validation" in f.reason.lower()
        for f in report.failures
    )


def test_garbage_junk_lines_skipped_with_failures() -> None:
    """Junk lines that cannot be interpreted as 2LE/3LE are reported and skipped."""
    # 2 lines of junk + a complete ISS 3LE: the junk is treated as a 2-line 3LE
    # candidate that fails, then ISS parses successfully.
    text = "this is not a tle at all\njust words\n" + ISS
    records, report = TLEParser().parse_with_report(text)
    assert len(records) == 1
    assert records[0].norad_id == 25544
    assert report.parsed == 1
    assert report.failed == 1
    assert report.total_records_attempted == 2
    assert any(
        "Incomplete" in f.reason for f in report.failures
    )


def test_crlf_and_blank_lines_tolerated() -> None:
    text = ISS.replace("\n", "\r\n") + "\r\n   \r\n"
    records, report = TLEParser().parse_with_report(text)
    assert len(records) == 1
    assert report.parsed == 1
    assert report.failed == 0


def test_parse_backwards_compat_returns_records_only() -> None:
    """Legacy ``parse()`` still returns only the records list (no report)."""
    records = TLEParser().parse(ISS)
    assert len(records) == 1
    assert records[0].norad_id == 25544


def test_with_report_total_records_attempted_is_line_count() -> None:
    """``total_records_attempted`` counts non-empty lines consumed as record starts."""
    text = "A\nB\nC\n"
    records, report = TLEParser().parse_with_report(text)
    assert report.total_records_attempted == 1
    assert report.parsed == 0
    assert report.failed == 1
