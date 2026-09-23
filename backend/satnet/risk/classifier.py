"""Risk-level classification for conjunction events.

Two independent, explicitly separated bases:
- Geometric classification uses the *screening miss distance* (km). This is a
  distance, NOT a probability of collision.
- Pc-based classification is only applied when a genuine Pc value exists. This
  system never fabricates Pc; without covariance, ``pc`` is None and the
  geometric basis is used alone.
"""
from __future__ import annotations

from dataclasses import dataclass

from satnet.domain.models import RiskLevel


@dataclass(frozen=True)
class RiskThresholds:
    red_miss_distance_km: float = 1.0
    yellow_miss_distance_km: float = 5.0
    red_pc: float = 1e-4
    yellow_pc: float = 1e-6


class RiskClassifier:
    def __init__(self, thresholds: RiskThresholds | None = None):
        self.thresholds = thresholds or RiskThresholds()

    def classify(self, miss_distance_km: float, pc: float | None = None) -> tuple[RiskLevel, str]:
        """Classify from miss distance, optionally strengthened by a real Pc.

        Returns (risk_level, human-readable reason).
        """
        if pc is not None:
            if pc >= self.thresholds.red_pc:
                return RiskLevel.RED, f"Pc >= {self.thresholds.red_pc:g}"
            if pc >= self.thresholds.yellow_pc:
                return RiskLevel.YELLOW, f"Pc >= {self.thresholds.yellow_pc:g}"
        if miss_distance_km <= self.thresholds.red_miss_distance_km:
            return RiskLevel.RED, "Miss distance is within RED threshold."
        if miss_distance_km <= self.thresholds.yellow_miss_distance_km:
            return RiskLevel.YELLOW, "Miss distance is within YELLOW threshold."
        return RiskLevel.GREEN, "Outside configured elevated-risk thresholds."
