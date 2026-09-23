"""Probability-of-collision boundary.

Scientific rule enforced here: NO covariance = NO Pc.

The calculator validates Pc inputs (3x3 positive-definite combined covariance,
3D relative position, positive hard-body radius) and reports Pc as explicitly
``unavailable`` until a validated encounter-plane integration method and a real
covariance source exist. It never substitutes a geometric miss distance for Pc
and never invents a numeric probability.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from satnet.domain.exceptions import ProbabilityCalculationError


@dataclass(frozen=True)
class ProbabilityResult:
    value: float | None
    status: str
    message: str


class ProbabilityOfCollisionCalculator:
    def availability_report(self) -> ProbabilityResult:
        """Standard 'Pc unavailable' result used when no covariance source exists."""
        return ProbabilityResult(
            None,
            "unavailable",
            "Probability of collision requires covariance information, which is "
            "not available in this system; the reported miss distance is a "
            "geometric screening value, not a probability.",
        )

    def calculate(
        self,
        relative_position_km,
        combined_covariance_km2,
        hard_body_radius_km: float,
        relative_velocity_km_s=None,
    ) -> ProbabilityResult:
        if combined_covariance_km2 is None:
            return ProbabilityResult(
                None, "unavailable", "Combined covariance not provided."
            )
        cov = np.asarray(combined_covariance_km2, dtype=float)
        pos = np.asarray(relative_position_km, dtype=float)
        if cov.shape != (3, 3) or pos.shape != (3,):
            raise ProbabilityCalculationError(
                "Expected 3x3 covariance and 3D relative position."
            )
        if hard_body_radius_km <= 0:
            raise ProbabilityCalculationError("Hard-body radius must be positive.")
        if not np.all(np.isfinite(cov)) or not np.all(np.isfinite(pos)):
            raise ProbabilityCalculationError("Pc inputs must be finite.")
        if np.any(np.linalg.eigvalsh(cov) <= 0):
            raise ProbabilityCalculationError(
                "Combined covariance must be positive definite."
            )
        if relative_velocity_km_s is None:
            return ProbabilityResult(
                None, "unavailable", "Encounter geometry is incomplete."
            )
        return ProbabilityResult(
            None,
            "unavailable",
            "A validated encounter-plane Pc method and covariance source are "
            "required before reporting Pc.",
        )
