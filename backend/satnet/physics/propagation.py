"""SGP4 propagation.

Scientific baseline
-------------------
Method:      SGP4 (as implemented by the established ``sgp4`` Python library,
             Vallado's reference implementation). SGP4 equations are NOT
             re-implemented here.
Frame:       TEME (True Equator, Mean Equinox) — the native SGP4 output frame.
             No frame conversion is performed or hidden in this module.
Position:    km
Velocity:    km/s
Time system: UTC (timezone-aware datetimes required; naive datetimes rejected).
Gravity:     WGS-72, as baked into the standard SGP4/TLE model. TLE element
             sets are only consistent with WGS-72, so no other gravity model
             is offered for TLE propagation.

Limitations
-----------
SGP4 accuracy degrades with time from the TLE epoch (typically good over a few
days for LEO). It does not model maneuvers. Results are a physics *baseline*,
not a truth model, and never a substitute for covariance-bearing ephemerides.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
from sgp4.api import Satrec

from satnet.domain.exceptions import PropagationError
from satnet.domain.models import (
    PropagationConfig,
    SatelliteTLE,
    StateVector,
    Trajectory,
)

J2000_UNIX_SECONDS = 946728000.0
J2000_JD = 2451545.0


def _require_utc(timestamp: datetime, context: str) -> datetime:
    """Reject naive datetimes instead of silently guessing a timezone."""
    if timestamp.tzinfo is None or timestamp.tzinfo.utcoffset(timestamp) is None:
        raise PropagationError(
            f"{context} must be timezone-aware (UTC expected); got naive datetime."
        )
    return timestamp.astimezone(timezone.utc)


def _datetime_grid(config: PropagationConfig) -> list[datetime]:
    """Deterministic UTC grid: uniform steps plus the exact end time."""
    start = _require_utc(config.start_time, "start_time")
    end = _require_utc(config.end_time, "end_time")
    step = config.time_step_seconds
    if step <= 0:
        raise PropagationError("time_step_seconds must be positive.")

    total_seconds = (end - start).total_seconds()
    if total_seconds <= 0:
        raise PropagationError("end_time must be after start_time.")

    count = int(total_seconds // step)
    grid = [start + timedelta(seconds=i * step) for i in range(count + 1)]
    if grid[-1] < end:
        grid.append(end)
    return grid


def _julian_arrays(times: list[datetime]) -> tuple[np.ndarray, np.ndarray]:
    """Convert UTC datetimes to (jd, fr) SGP4 day fractions.

    ``datetime.timestamp()`` on timezone-aware UTC datetimes is the well-known
    Unix epoch, shifted here to the J2000 Julian date base.
    """
    seconds = np.asarray(
        [(t.timestamp() - J2000_UNIX_SECONDS) / 86400.0 for t in times],
        dtype=np.float64,
    )
    jd = J2000_JD + seconds
    whole = np.floor(jd)
    return whole, jd - whole


class SGP4Propagator:
    """Propagate a validated TLE with SGP4.

    Output frame is TEME, units are km and km/s, timestamps are UTC.
    """

    def __init__(self) -> None:
        self._satrec_cache: dict[tuple[str, str], Satrec] = {}

    def _satrec(self, tle: SatelliteTLE) -> Satrec:
        key = (tle.line1, tle.line2)
        cached = self._satrec_cache.get(key)
        if cached is None:
            cached = Satrec.twoline2rv(tle.line1, tle.line2)
            self._satrec_cache[key] = cached
        return cached

    def propagate(self, tle: SatelliteTLE, times: list[datetime]) -> Trajectory:
        if not times:
            raise PropagationError("No propagation timestamps supplied.")

        times = [_require_utc(t, "Propagation timestamp") for t in times]

        try:
            sat = self._satrec(tle)
            jd, fr = _julian_arrays(times)

            if hasattr(sat, "sgp4_array"):
                errors, positions, velocities = sat.sgp4_array(jd, fr)
            else:  # pragma: no cover - depends on sgp4 build
                rows = [sat.sgp4(float(j), float(f)) for j, f in zip(jd, fr)]
                errors = np.asarray([r[0] for r in rows])
                positions = np.asarray([r[1] for r in rows])
                velocities = np.asarray([r[2] for r in rows])

            if np.any(errors != 0):
                first = int(np.flatnonzero(errors != 0)[0])
                raise PropagationError(
                    f"SGP4 error code {int(errors[first])} at "
                    f"{times[first].isoformat()}."
                )

            if not np.all(np.isfinite(positions)) or not np.all(
                np.isfinite(velocities)
            ):
                raise PropagationError("SGP4 produced non-finite state vectors.")

            states = [
                StateVector(
                    timestamp=t,
                    position_km=(float(p[0]), float(p[1]), float(p[2])),
                    velocity_km_s=(float(v[0]), float(v[1]), float(v[2])),
                )
                for t, p, v in zip(times, positions, velocities)
            ]
            return Trajectory(satellite=tle, states=states)

        except PropagationError:
            raise
        except Exception as exc:  # surface SGP4/library failures clearly
            raise PropagationError(
                f"Propagation failed for {tle.name} (NORAD {tle.norad_id}): {exc}"
            ) from exc

    def propagate_one(
        self, tle: SatelliteTLE, timestamp: datetime
    ) -> StateVector:
        return self.propagate(tle, [_require_utc(timestamp, "Timestamp")]).states[0]

    def diagnose(self, tle: SatelliteTLE) -> dict:
        """Lightweight pre-check for a single TLE.

        Returns a small dict suitable for logging.  The check confirms that:
        - the Satrec loads, and
        - a short forward/backward sample around the current UTC time produces
          valid, timezone-aware state vectors.

        SGP4 may still error for far-future or extreme orbits; this routine is
        defensive and never raises for a TLE that already passed validation —
        it just reports ``sample_ok`` as False with a reason.
        """
        out: dict = {
            "norad_id": tle.norad_id,
            "name": tle.name,
            "epoch": tle.epoch.isoformat(),
            "satrec_loaded": True,
            "sample_ok": False,
        }
        try:
            sat = self._satrec(tle)
            out["satrec_loaded"] = True
        except Exception as exc:
            out["satrec_loaded"] = False
            out["sample_error"] = f"Satrec load failed: {exc}"
            return out

        try:
            now = _require_utc(datetime.now(timezone.utc), "diagnose current time")
            sample_times = [
                now - timedelta(hours=1),
                now,
                now + timedelta(hours=1),
            ]
            traj = self.propagate(tle, sample_times)
            out["sample_ok"] = all(
                s.timestamp.tzinfo is not None for s in traj.states
            )
            out["first_state_frame"] = traj.states[0].frame
            out["sample_state_count"] = len(traj.states)
        except PropagationError as exc:
            out["sample_ok"] = False
            out["sample_error"] = f"{type(exc).__name__}: {exc}"
        except Exception as exc:  # noqa: BLE001 - surface unexpected library issues
            out["sample_ok"] = False
            out["sample_error"] = f"{type(exc).__name__}: {exc}"

        return out


class TrajectoryPropagationService:
    """Generates trajectories on deterministic UTC time grids."""

    def __init__(self, propagator: SGP4Propagator | None = None) -> None:
        self.propagator = propagator or SGP4Propagator()

    def propagate(
        self, tle: SatelliteTLE, config: PropagationConfig
    ) -> Trajectory:
        return self.propagator.propagate(tle, _datetime_grid(config))

    def propagate_many(
        self, tles: list[SatelliteTLE], config: PropagationConfig
    ) -> list[Trajectory]:
        """All satellites share one deterministic time grid (required by screening)."""
        times = _datetime_grid(config)
        return [self.propagator.propagate(tle, times) for tle in tles]
