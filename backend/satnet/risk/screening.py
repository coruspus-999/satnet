"""Geometric close-approach screening.

IMPORTANT SCIENTIFIC SCOPE
--------------------------
Everything in this module is *geometric screening* over sampled SGP4
trajectories in TEME (km, UTC). It produces candidate pairs and minimum
separations ("screening miss distances").

This is NOT probabilistic conjunction assessment: a geometric miss distance is
not a probability of collision (Pc). Pc requires covariance information that
this system does not fabricate; see ``satnet.risk.pc``.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree

from satnet.domain.exceptions import ConjunctionCalculationError
from satnet.domain.models import StateVector, Trajectory
from satnet.risk.relative import relative_speed_km_s, separation_km

# Golden-section search constant.
_GS_RATIO = (5**0.5 - 1) / 2


@dataclass(frozen=True)
class CandidatePair:
    """A coarse screening hit on a single time step.

    Attributes:
        satellite_a: NORAD id of one satellite (sorted so a < b).
        satellite_b: NORAD id of the other satellite.
        coarse_index: index into the shared deterministic time grid where the
            hit was detected.
    """
    satellite_a: int
    satellite_b: int
    coarse_index: int


class SpatialScreeningService:
    """Coarse cKDTree screening over a shared deterministic time grid.

    For each time step, all satellite positions are inserted into a KD-tree and
    query_pairs(safety_radius_km) yields pairs whose separation is within the
    safety radius.  Duplicate (a,b,index) hits are deduplicated.
    """

    def __init__(self, safety_radius_km: float) -> None:
        if safety_radius_km <= 0:
            raise ValueError("Safety radius must be positive.")
        self.safety_radius_km = safety_radius_km

    def find_candidates(
        self, trajectories: list[Trajectory]
    ) -> list[CandidatePair]:
        """Return candidate pairs within the safety radius at any grid step.

        Raises:
            ConjunctionCalculationError:
                If trajectories do not share the same number of states, or if
                NORAD ids are duplicated in the set.
        """
        if not trajectories:
            return []

        expected = len(trajectories[0].states)
        if any(len(t.states) != expected for t in trajectories):
            raise ConjunctionCalculationError(
                "All trajectories must share the same time grid."
            )
        if len(trajectories) < 2:
            return []

        ids = [t.satellite.norad_id for t in trajectories]
        if len(set(ids)) != len(ids):
            raise ConjunctionCalculationError(
                "Duplicate NORAD ids in trajectory set."
            )

        found: set[tuple[int, int, int]] = set()
        for index in range(expected):
            points = np.asarray(
                [t.states[index].position_km for t in trajectories],
                dtype=np.float64,
            )
            for a, b in cKDTree(points).query_pairs(self.safety_radius_km):
                x, y = sorted((ids[a], ids[b]))
                found.add((x, y, index))

        return [CandidatePair(*row) for row in sorted(found)]


class ConjunctionRefiner:
    """Refines TCA by minimizing SGP4-derived relative distance in a bracket.

    Golden-section search over *actual SGP4 states* (no physics interpolation):
    the objective is re-propagated at each trial time.  Bounded to the bracket
    [grid index - 1, grid index + 1] around a coarse candidate.  This converges
    toward a local minimum of the separation function; it is a screening aid,
    not a rigorously optimal TCA solver.
    """

    def __init__(self, propagator, max_iterations: int = 28) -> None:
        self.propagator = propagator
        self.max_iterations = max_iterations

    def refine(
        self, a: Trajectory, b: Trajectory, index: int
    ) -> tuple[datetime, float, float]:
        """Refine the TCA, miss distance, and relative speed for one pair.

        Returns ``(tca, miss_distance_km, relative_velocity_km_s)``.
        """
        times = [s.timestamp for s in a.states]
        i = max(0, min(index, len(times) - 1))
        lo = times[max(0, i - 1)]
        hi = times[min(len(times) - 1, i + 1)]

        if hi <= lo:
            state_a, state_b = a.states[i], b.states[i]
            return (
                state_a.timestamp,
                separation_km(state_a.position_km, state_b.position_km),
                relative_speed_km_s(
                    state_a.velocity_km_s, state_b.velocity_km_s
                ),
            )

        tle_a, tle_b = a.satellite, b.satellite

        def evaluate(t: datetime) -> tuple[float, StateVector, StateVector]:
            sa = self.propagator.propagate_one(tle_a, t)
            sb = self.propagator.propagate_one(tle_b, t)
            return (
                separation_km(sa.position_km, sb.position_km),
                sa,
                sb,
            )

        x1 = hi - (hi - lo) * _GS_RATIO
        x2 = lo + (hi - lo) * _GS_RATIO
        f1, sa1, sb1 = evaluate(x1)
        f2, sa2, sb2 = evaluate(x2)

        for _ in range(self.max_iterations):
            if f1 > f2:
                lo, x1, f1, sa1, sb1 = x1, x2, f2, sa2, sb2
                x2 = lo + (hi - lo) * _GS_RATIO
                f2, sa2, sb2 = evaluate(x2)
            else:
                hi, x2, f2, sa2, sb2 = x2, x1, f1, sa1, sb1
                x1 = hi - (hi - lo) * _GS_RATIO
                f1, sa1, sb1 = evaluate(x1)

        if f1 <= f2:
            best_t, best_d, best_a, best_b = x1, f1, sa1, sb1
        else:
            best_t, best_d, best_a, best_b = x2, f2, sa2, sb2

        return (
            best_t,
            best_d,
            relative_speed_km_s(best_a.velocity_km_s, best_b.velocity_km_s),
        )


class ConjunctionDetectionService:
    """Screening + per-pair TCA refinement, reduced to the best event per pair."""

    def __init__(
        self,
        screening: SpatialScreeningService,
        refiner: ConjunctionRefiner,
    ) -> None:
        self.screening = screening
        self.refiner = refiner

    def detect(
        self, trajectories: list[Trajectory]
    ) -> tuple[list[CandidatePair], list[tuple[int, int, datetime, float, float]]]:
        """Return coarse candidates and the refined per-pair events.

        Returns ``(candidates, raw_events)`` where each raw event is
        ``(sat_a, sat_b, tca, miss_km, rel_speed)`` and only the closest
        approach per unordered pair is kept.
        """
        candidates = self.screening.find_candidates(trajectories)
        by_id = {t.satellite.norad_id: t for t in trajectories}
        events: dict[tuple[int, int], tuple[datetime, float, float]] = {}

        for candidate in candidates:
            tca, distance, speed = self.refiner.refine(
                by_id[candidate.satellite_a],
                by_id[candidate.satellite_b],
                candidate.coarse_index,
            )
            key = (candidate.satellite_a, candidate.satellite_b)
            if key not in events or distance < events[key][1]:
                events[key] = (tca, distance, speed)

        return candidates, [
            (pair[0], pair[1], *value) for pair, value in events.items()
        ]
