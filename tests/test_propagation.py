"""Tests for SGP4 propagation and the trajectory service.

Propagation is the physics baseline: TEME frame, km and km/s, UTC timestamps.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from satnet.domain.exceptions import PropagationError, TLEValidationError
from satnet.domain.models import PropagationConfig
from satnet.ingestion.parser import TLEParser
from satnet.physics.propagation import (
    SGP4Propagator,
    TrajectoryPropagationService,
    _datetime_grid,
)


def _config(start: datetime, hours: float = 2, step: int = 60) -> PropagationConfig:
    return PropagationConfig(
        start_time=start,
        end_time=start + timedelta(hours=hours),
        time_step_seconds=step,
    )


def test_propagate_valid_tle(iss_tle_text: str) -> None:
    tle = TLEParser().parse(iss_tle_text)[0]
    start = datetime(2025, 8, 8, 12, tzinfo=timezone.utc)
    trajectory = TrajectoryPropagationService().propagate(tle, _config(start))
    assert len(trajectory.states) == 121
    assert trajectory.frame == "TEME"
    assert trajectory.position_unit == "km"
    assert trajectory.velocity_unit == "km/s"


def test_state_vector_frame_and_units(iss_tle_text: str) -> None:
    tle = TLEParser().parse(iss_tle_text)[0]
    start = datetime(2025, 8, 8, 12, tzinfo=timezone.utc)
    state = TrajectoryPropagationService().propagate(tle, _config(start)).states[0]
    assert state.frame == "TEME"
    assert state.position_unit == "km"
    assert state.velocity_unit == "km/s"
    assert len(state.position_km) == 3
    assert len(state.velocity_km_s) == 3
    assert state.timestamp.tzinfo is not None


def test_position_magnitude_leo(iss_tle_text: str) -> None:
    """Sanity check: LEO radius ~6700-7300 km from geocenter."""
    tle = TLEParser().parse(iss_tle_text)[0]
    start = datetime(2025, 8, 8, 12, tzinfo=timezone.utc)
    state = TrajectoryPropagationService().propagate(tle, _config(start)).states[0]
    radius = sum(c * c for c in state.position_km) ** 0.5
    assert 6600 < radius < 7400


def test_naive_timestamp_rejected(iss_tle_text: str) -> None:
    tle = TLEParser().parse(iss_tle_text)[0]
    propagator = SGP4Propagator()
    with pytest.raises(PropagationError, match="timezone-aware"):
        propagator.propagate_one(tle, datetime(2025, 8, 8, 12))


def test_naive_config_times_rejected(iss_tle_text: str) -> None:
    """Naive config times are rejected by the domain model before propagation."""
    with pytest.raises(ValidationError):
        TrajectoryPropagationService().propagate(
            TLEParser().parse(iss_tle_text)[0],
            _config(datetime(2025, 8, 8, 12)),
        )


def test_non_utc_offsets_accepted_and_normalized(iss_tle_text: str) -> None:
    """Timezone-aware non-UTC input is accepted and normalized to UTC."""
    tle = TLEParser().parse(iss_tle_text)[0]
    start = datetime(2025, 8, 8, 14, tzinfo=timezone(timedelta(hours=2)))
    trajectory = TrajectoryPropagationService().propagate(
        tle, _config(start, hours=0.01)
    )
    assert trajectory.states[0].timestamp.utcoffset() == timedelta(0)


def test_grid_is_deterministic() -> None:
    start = datetime(2025, 8, 8, 12, tzinfo=timezone.utc)
    grid1 = _datetime_grid(_config(start, hours=1, step=1800))
    grid2 = _datetime_grid(_config(start, hours=1, step=1800))
    assert grid1 == grid2
    assert len(grid1) == 3  # 0, 30, 60 min
    assert grid1[-1] == start + timedelta(hours=1)


def test_grid_includes_exact_end() -> None:
    start = datetime(2025, 8, 8, 12, tzinfo=timezone.utc)
    grid = _datetime_grid(_config(start, hours=0.5, step=3600))
    assert grid[-1] == start + timedelta(minutes=30)


def test_propagate_many_shares_grid(two_satellite_tle_text: str) -> None:
    tles = TLEParser().parse(two_satellite_tle_text)
    start = datetime(2025, 8, 8, 12, tzinfo=timezone.utc)
    trajectories = TrajectoryPropagationService().propagate_many(
        tles, _config(start, hours=0.1)
    )
    assert len(trajectories) == 2
    stamps = [s.timestamp for s in trajectories[0].states]
    assert all(s.timestamp == t for s, t in zip(trajectories[1].states, stamps))


def test_empty_times_rejected(iss_tle_text: str) -> None:
    tle = TLEParser().parse(iss_tle_text)[0]
    with pytest.raises(PropagationError):
        SGP4Propagator().propagate(tle, [])


def test_sgp4_error_surfaces() -> None:
    """A decayed/bad TLE (far from epoch) still validates but SGP4 may error."""
    from satnet.ingestion.validator import TLEValidator

    line1 = "1 25544U 98067A   25220.51839244  .00017356  00000+0  31752-3 0  9999"
    line2 = "2 25544  51.6328  47.2102 0002964  72.7432  50.8368 15.50117825522003"
    tle = TLEValidator().validate("ISS", line1, line2)
    far_future = datetime(2040, 1, 1, tzinfo=timezone.utc)
    # Either propagates or raises a clean PropagationError - never a raw crash.
    try:
        state = SGP4Propagator().propagate_one(tle, far_future)
        assert state.frame == "TEME"
    except PropagationError:
        pass


def test_checksum_failure_reported_by_parser_not_raised() -> None:
    """A TLE whose checksum fails is reported by the parser as a failure now."""
    from tests.conftest import ISS_LINE1, ISS_LINE2, recompute_checksum

    bad_line1 = recompute_checksum(
        "1 25544U 98067A   25220.51839244  .00017356  00000+0  31752-3 0  9994"
    )
    text = f"ISS (ZARYA)\n{bad_line1}\n{ISS_LINE2}\n"
    records, report = TLEParser().parse_with_report(text)
    assert len(records) == 0
    assert report.parsed == 0
    assert report.failed == 1
    assert report.total_records_attempted == 3
