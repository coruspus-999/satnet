"""Invalid-input tests: malformed TLEs, bad configs, wrong types.

Where the parser once raised on a single bad record and aborted the whole
input, it now reports that record as a failure and continues.  Tests that
previously asserted a hard error on a corrupt TLE still confirm that the bad
record is *not* accepted — but they may now see it reported as a ``failed``
record rather than as a raised exception, depending on the surrounding text.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from satnet.domain.exceptions import (
    PropagationError,
    TLEParseError,
    TLEValidationError,
)
from satnet.domain.models import PropagationConfig, SatelliteTLE
from satnet.ingestion.parser import TLEParser
from satnet.ingestion.service import TLEIngestionService
from tests.conftest import ISS_LINE1, ISS_LINE2, recompute_checksum

GOOD = (
    "ISS (ZARYA)\n"
    "1 25544U 98067A   25220.51839244  .00017356  00000+0  31752-3 0  9999\n"
    "2 25544  51.6328  47.2102 0002964  72.7432  50.8368 15.50117825522003\n"
)


def test_garbage_text_rejected() -> None:
    """Garbage without '1 '/'2 ' prefixes fails; none of it is accepted."""
    records, report = TLEParser().parse_with_report(
        "this is not a tle at all\njust words\nmore words\n"
    )
    assert len(records) == 0
    assert report.parsed == 0
    assert report.failed == 1
    assert report.total_records_attempted == 1


def test_naive_datetime_rejected_in_config() -> None:
    with pytest.raises(ValidationError):
        PropagationConfig(
            start_time=datetime(2025, 8, 8, 12),  # naive
            end_time=datetime(2025, 8, 8, 13, tzinfo=timezone.utc),
        )


def test_end_before_start_rejected() -> None:
    with pytest.raises(ValidationError):
        PropagationConfig(
            start_time=datetime(2025, 8, 8, 13, tzinfo=timezone.utc),
            end_time=datetime(2025, 8, 8, 12, tzinfo=timezone.utc),
        )


def test_zero_time_step_rejected() -> None:
    with pytest.raises(ValidationError):
        PropagationConfig(
            start_time=datetime(2025, 8, 8, 12, tzinfo=timezone.utc),
            end_time=datetime(2025, 8, 8, 13, tzinfo=timezone.utc),
            time_step_seconds=0,
        )


def test_negative_norad_rejected() -> None:
    with pytest.raises(ValidationError):
        SatelliteTLE(
            name="X",
            norad_id=-1,
            line1="1" * 69,
            line2="2" * 69,
            epoch=datetime(2025, 8, 8, tzinfo=timezone.utc),
        )


def test_dedup_keeps_newest_epoch() -> None:
    service = TLEIngestionService()
    older_line1 = recompute_checksum(
        ISS_LINE1.replace("25220.51839244", "25210.00000000")
    )
    older = f"ISS (ZARYA)\n{older_line1}\n{ISS_LINE2}\n"
    records = service.parse_text(GOOD + older)
    assert len(records) == 1
    assert records[0].line1 == ISS_LINE1


def test_ingestion_service_surfaces_empty_input_error() -> None:
    service = TLEIngestionService()
    with pytest.raises(TLEParseError):
        service.parse_text("")


def test_exception_hierarchy() -> None:
    from satnet.domain.exceptions import (
        ConjunctionCalculationError,
        ProbabilityCalculationError,
        SatNetError,
        TLEFetchError,
    )

    for exc in (
        TLEParseError,
        TLEValidationError,
        TLEFetchError,
        PropagationError,
        ConjunctionCalculationError,
        ProbabilityCalculationError,
    ):
        assert issubclass(exc, SatNetError)
