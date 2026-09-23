from datetime import datetime, timezone

import pytest

from satnet.domain.exceptions import TLEValidationError
from satnet.ingestion.validator import TLEValidator, checksum_valid

L1 = "1 25544U 98067A   25220.51839244  .00017356  00000+0  31752-3 0  9999"
L2 = "2 25544  51.6328  47.2102 0002964  72.7432  50.8368 15.50117825522003"


def test_checksum_valid_true():
    assert checksum_valid(L1)
    assert checksum_valid(L2)


def test_checksum_valid_false_on_bad_digit():
    assert not checksum_valid(L1[:-1] + "4")


def test_validate_success_and_epoch():
    record = TLEValidator().validate("ISS (ZARYA)", L1, L2, "test")
    assert record.norad_id == 25544
    assert record.epoch > datetime(2025, 1, 1, tzinfo=timezone.utc)
    assert record.epoch.tzinfo is timezone.utc
    assert record.source == "test"


def test_wrong_line_numbers_rejected():
    with pytest.raises(TLEValidationError):
        TLEValidator().validate("X", "2 " + L1[2:], L2)
    with pytest.raises(TLEValidationError):
        TLEValidator().validate("X", L1, "1 " + L2[2:])


def test_wrong_length_rejected():
    with pytest.raises(TLEValidationError, match="69"):
        TLEValidator().validate("X", L1[:-1], L2)
    with pytest.raises(TLEValidationError, match="69"):
        TLEValidator().validate("X", L1, L2 + "x")


def test_bad_checksum_rejected():
    with pytest.raises(TLEValidationError, match="checksum"):
        TLEValidator().validate("X", L1[:-1] + "1", L2)


def test_mismatched_satellite_numbers_rejected():
    """Line 1 and line 2 disagree on the NORAD id."""
    bad_l2 = "2 25543" + L2[7:]
    with pytest.raises(TLEValidationError):
        TLEValidator().validate("X", L1, bad_l2)


def test_empty_name_gets_norad_fallback():
    record = TLEValidator().validate("   ", L1, L2)
    assert record.name == "NORAD-25544"
