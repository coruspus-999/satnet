"""Example: propagate a satellite from a fixed TLE (offline, deterministic).

Run:  python examples/propagate_iss.py

Uses a fixed TLE so the output is reproducible without network access.
SGP4 is the baseline; output frame is TEME, units km and km/s, time UTC.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from satnet.domain.models import PropagationConfig
from satnet.ingestion.parser import TLEParser
from satnet.physics.propagation import TrajectoryPropagationService

FIXED_TLE = """ISS (ZARYA)
1 25544U 98067A   25220.51839244  .00017356  00000+0  31752-3 0  9999
2 25544  51.6328  47.2102 0002964  72.7432  50.8368 15.50117825522003
"""


def main() -> None:
    records = TLEParser().parse(FIXED_TLE, "example")
    tle = records[0]
    print(f"Parsed: {tle.name}  NORAD {tle.norad_id}  epoch {tle.epoch.isoformat()}")

    start = datetime(2025, 8, 8, 12, tzinfo=timezone.utc)
    config = PropagationConfig(
        start_time=start,
        end_time=start + timedelta(minutes=10),
        time_step_seconds=120,
    )

    service = TrajectoryPropagationService()
    trajectory = service.propagate(tle, config)

    print(f"\nTrajectory: {len(trajectory.states)} states")
    print(f"Frame: {trajectory.frame} | Position: {trajectory.position_unit} "
          f"| Velocity: {trajectory.velocity_unit} | Time: UTC")
    print("\nFirst / middle / last states:")
    for state in (trajectory.states[0], trajectory.states[len(trajectory.states) // 2], trajectory.states[-1]):
        x, y, z = state.position_km
        vx, vy, vz = state.velocity_km_s
        print(f"  {state.timestamp.isoformat()}  "
              f"r=({x:10.2f}, {y:10.2f}, {z:10.2f}) km  "
              f"v=({vx:7.4f}, {vy:7.4f}, {vz:7.4f}) km/s")

    radius = sum(c * c for c in trajectory.states[0].position_km) ** 0.5
    print(f"\nGeocentric radius at start: {radius:.1f} km (TEME)")


if __name__ == "__main__":
    main()
