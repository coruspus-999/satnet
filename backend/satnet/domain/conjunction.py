"""Conjunction-assessment domain objects.

Phase 4 foundation: these types carry encounter geometry and an *explicit*
covariance placeholder so that future covariance-based Pc analysis can be
added without changing the geometric layer.

The covariance is either provided (from a real source) or explicitly
"unavailable". This system never fabricates covariance or Pc values.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class RelativeState:
    """Relative state of A with respect to B: r = r_A - r_B, v = v_A - v_B."""

    position_km: tuple[float, float, float]
    velocity_km_s: tuple[float, float, float]
    frame: str = "TEME"
    position_unit: str = "km"
    velocity_unit: str = "km/s"


@dataclass(frozen=True)
class Covariance3x3:
    """Explicit 3x3 position covariance placeholder (km^2).

    ``matrix_km2 is None`` means covariance data is NOT available. Absence is
    represented explicitly rather than hidden; no code may substitute a
    geometric miss distance or an invented value for a real covariance.
    """

    matrix_km2: tuple[tuple[float, float, float], ...] | None = None
    status: str = "unavailable"
    source: str = "not-provided"

    @property
    def is_available(self) -> bool:
        return self.matrix_km2 is not None


@dataclass(frozen=True)
class Encounter:
    """A screened close approach between two catalogued objects."""

    satellite_a: int  # NORAD id
    satellite_b: int  # NORAD id
    tca: datetime
    miss_distance_km: float
    relative_state: RelativeState
    covariance: Covariance3x3 = field(default_factory=Covariance3x3)
