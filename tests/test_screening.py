"""Screening tests with synthetic trajectories (no SGP4 dependency)."""
from datetime import datetime, timedelta, timezone

import pytest

from satnet.domain.exceptions import ConjunctionCalculationError
from satnet.domain.models import SatelliteTLE, StateVector, Trajectory
from satnet.risk.classifier import RiskClassifier, RiskThresholds
from satnet.risk.pc import ProbabilityOfCollisionCalculator
from satnet.risk.screening import (
    CandidatePair,
    ConjunctionDetectionService,
    ConjunctionRefiner,
    SpatialScreeningService,
)

BASE = datetime(2025, 8, 8, 12, tzinfo=timezone.utc)


def _tle(norad_id: int, name: str) -> SatelliteTLE:
    return SatelliteTLE(
        name=name,
        norad_id=norad_id,
        line1="1 25544U 98067A   25220.51839244  .00017356  00000+0  31752-3 0  9999"[:69],
        line2="2 25544  51.6328  47.2102 0002964  72.7432  50.8368 15.50117825522003"[:69],
        epoch=BASE,
    )


def _trajectory(norad_id: int, name: str, offsets, velocity=(0.0, 0.0, 0.0)) -> Trajectory:
    return Trajectory(
        satellite=_tle(norad_id, name),
        states=[
            StateVector(
                timestamp=BASE + timedelta(seconds=i),
                position_km=offset,
                velocity_km_s=velocity,
            )
            for i, offset in enumerate(offsets)
        ],
    )


def test_identical_positions_zero_separation():
    a = _trajectory(1, "A", [(100.0, 0.0, 0.0)])
    b = _trajectory(2, "B", [(100.0, 0.0, 0.0)])
    screening = SpatialScreeningService(25.0)
    candidates = screening.find_candidates([a, b])
    assert len(candidates) == 1
    assert candidates[0].satellite_a == 1
    assert candidates[0].satellite_b == 2


def test_known_separation_distance():
    a = _trajectory(1, "A", [(0.0, 0.0, 0.0)])
    b = _trajectory(2, "B", [(3.0, 4.0, 0.0)])
    from satnet.risk.relative import separation_km

    assert separation_km(a.states[0].position_km, b.states[0].position_km) == pytest.approx(5.0)


def test_candidates_within_radius_only():
    a = _trajectory(1, "A", [(0.0, 0.0, 0.0)])
    b = _trajectory(2, "B", [(10.0, 0.0, 0.0)])
    c = _trajectory(3, "C", [(1000.0, 0.0, 0.0)])
    candidates = SpatialScreeningService(25.0).find_candidates([a, b, c])
    assert {(x.satellite_a, x.satellite_b) for x in candidates} == {(1, 2)}


def test_mismatched_grid_lengths_rejected():
    a = _trajectory(1, "A", [(0.0, 0.0, 0.0)] * 3)
    b = _trajectory(2, "B", [(0.0, 0.0, 0.0)] * 2)
    with pytest.raises(ConjunctionCalculationError, match="same time grid"):
        SpatialScreeningService(25.0).find_candidates([a, b])


def test_duplicate_norad_ids_rejected():
    a = _trajectory(7, "A", [(0.0, 0.0, 0.0)])
    b = _trajectory(7, "B", [(1.0, 0.0, 0.0)])
    with pytest.raises(ConjunctionCalculationError, match="Duplicate NORAD"):
        SpatialScreeningService(25.0).find_candidates([a, b])


def test_single_trajectory_no_candidates():
    a = _trajectory(1, "A", [(0.0, 0.0, 0.0)])
    assert SpatialScreeningService(25.0).find_candidates([a]) == []


def test_invalid_safety_radius():
    with pytest.raises(ValueError):
        SpatialScreeningService(0)
    with pytest.raises(ValueError):
        SpatialScreeningService(-5)


class StaticPropagator:
    """Returns trajectory states without SGP4 (deterministic refiner tests)."""

    def __init__(self, trajectories):
        self._by_id = {t.satellite.norad_id: t for t in trajectories}

    def propagate_one(self, tle, timestamp):
        states = self._by_id[tle.norad_id].states
        nearest = min(states, key=lambda s: abs((s.timestamp - timestamp).total_seconds()))
        return nearest


def test_refiner_picks_minimum_separation():
    # Satellite B passes A: at index 1 they are closest.
    offsets_a = [(0.0, 0.0, 0.0)] * 3
    offsets_b = [(10.0, 0.0, 0.0), (0.5, 0.0, 0.0), (10.0, 0.0, 0.0)]
    a = _trajectory(1, "A", offsets_a)
    b = _trajectory(2, "B", offsets_b)
    refiner = ConjunctionRefiner(StaticPropagator([a, b]))
    tca, distance, speed = refiner.refine(a, b, 1)
    assert distance == pytest.approx(0.5)
    # Search time converges to the minimum; nearest evaluated state is index 1.
    assert abs((tca - b.states[1].timestamp).total_seconds()) < 1.0


def test_detection_service_reduces_to_best_pair_event():
    offsets_a = [(0.0, 0.0, 0.0)] * 3
    offsets_b = [(10.0, 0.0, 0.0), (0.5, 0.0, 0.0), (1.0, 0.0, 0.0)]
    a = _trajectory(1, "A", offsets_a)
    b = _trajectory(2, "B", offsets_b)
    service = ConjunctionDetectionService(
        SpatialScreeningService(25.0), ConjunctionRefiner(StaticPropagator([a, b]))
    )
    candidates, events = service.detect([a, b])
    assert candidates
    assert len(events) == 1
    sat_a, sat_b, tca, miss, rel_v = events[0]
    assert (sat_a, sat_b) == (1, 2)
    assert miss == pytest.approx(0.5)


def test_pc_unavailable_without_covariance():
    result = ProbabilityOfCollisionCalculator().calculate((1.0, 0.0, 0.0), None, 1.0)
    assert result.value is None
    assert result.status == "unavailable"


def test_pc_availability_report_is_explicit():
    report = ProbabilityOfCollisionCalculator().availability_report()
    assert report.value is None
    assert report.status == "unavailable"
    assert "covariance" in report.message.lower()


def test_pc_rejects_invalid_covariance():
    import numpy as np

    calc = ProbabilityOfCollisionCalculator()
    with pytest.raises(Exception):
        calc.calculate((1.0, 0.0, 0.0), [[1, 0], [0, 1]], 1.0)
    with pytest.raises(Exception):
        calc.calculate((1.0, 0.0, 0.0), np.eye(3) * -1.0, 1.0)  # not positive definite


def test_risk_classifier_geometric_only_without_pc():
    classifier = RiskClassifier()
    assert classifier.classify(0.5)[0].value == "RED"
    assert classifier.classify(3.0)[0].value == "YELLOW"
    assert classifier.classify(20.0)[0].value == "GREEN"


def test_risk_classifier_uses_pc_when_real():
    classifier = RiskClassifier()
    level, reason = classifier.classify(100.0, pc=2e-4)
    assert level.value == "RED"
    assert "Pc" in reason
    # Geometric thresholds unchanged when pc is None.
    assert classifier.classify(100.0, pc=None)[0].value == "GREEN"
