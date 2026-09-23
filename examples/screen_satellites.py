"""Example: geometric close-approach screening between two satellites (offline).

Run:  python examples/screen_satellites.py

What this computes: candidate pairs on a shared UTC grid and the minimum
geometric separation ("screening miss distance") per pair, refined by
re-propagating SGP4 states inside the bracketing interval.

What this does NOT compute: probability of collision (Pc). Pc requires
covariance information that is not available here and is never fabricated.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from satnet.domain.models import PropagationConfig
from satnet.ingestion.parser import TLEParser
from satnet.physics.propagation import TrajectoryPropagationService
from satnet.risk.classifier import RiskClassifier, RiskThresholds
from satnet.risk.pc import ProbabilityOfCollisionCalculator
from satnet.risk.screening import ConjunctionDetectionService, ConjunctionRefiner, SpatialScreeningService

FIXED_TLES = """ISS (ZARYA)
1 25544U 98067A   25220.51839244  .00017356  00000+0  31752-3 0  9999
2 25544  51.6328  47.2102 0002964  72.7432  50.8368 15.50117825522003
DEBRIS-A
1 48274U 98067A   25220.51839244  .00017356  00000+0  31752-3 0  9994
2 48274  51.6328  47.2102 0002964  72.7432  50.8368 16.00117825522004
"""


def main() -> None:
    records = TLEParser().parse(FIXED_TLES, "example")
    print(f"Ingested {len(records)} satellites:")
    for record in records:
        print(f"  NORAD {record.norad_id}: {record.name} (epoch {record.epoch.date()})")

    start = datetime(2025, 8, 8, 12, tzinfo=timezone.utc)
    config = PropagationConfig(
        start_time=start,
        end_time=start + timedelta(hours=48),
        time_step_seconds=60,
    )

    propagation = TrajectoryPropagationService()
    trajectories = propagation.propagate_many(records, config)
    print(f"\nPropagated {len(trajectories)} trajectories "
          f"({len(trajectories[0].states)} states each, shared UTC grid)")

    screening = SpatialScreeningService(safety_radius_km=250.0)
    detection = ConjunctionDetectionService(screening, ConjunctionRefiner(propagation.propagator))
    candidates, events = detection.detect(trajectories)
    print(f"\nCandidate pairs within 250 km on grid: {len(candidates)}")

    classifier = RiskClassifier(RiskThresholds())
    pc_boundary = ProbabilityOfCollisionCalculator()
    if not events:
        print("No geometric close approaches found in this window.")
        return

    print("\nScreening results (geometric only):")
    for sat_a, sat_b, tca, miss_km, rel_speed in events:
        level, reason = classifier.classify(miss_km)
        pc = pc_boundary.availability_report()
        print(f"  NORAD {sat_a} <-> NORAD {sat_b}")
        print(f"    TCA (UTC):          {tca.isoformat()}")
        print(f"    Miss distance:      {miss_km:.3f} km   [screening value, NOT Pc]")
        print(f"    Relative speed:     {rel_speed:.3f} km/s")
        print(f"    Risk level:         {level.value} ({reason})")
        print(f"    Pc:                 {pc.status.upper()} - {pc.message}")


if __name__ == "__main__":
    main()
