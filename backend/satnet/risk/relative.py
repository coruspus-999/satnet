"""Relative-motion helpers for geometric screening.

All inputs and outputs are TEME km / km/s; both states must share the frame.
These helpers operate on state-vector tuples, not on full domain models, so
they stay small and testable.
"""
from __future__ import annotations

import numpy as np


@np.errstate(invalid="ignore", over="ignore")
def _norm(v: np.ndarray) -> float:
    return float(np.linalg.norm(v))


def relative_position_km(
    a: tuple[float, float, float], b: tuple[float, float, float]
) -> np.ndarray:
    """Vector from b to a, in km."""
    return np.asarray(a, dtype=np.float64) - np.asarray(b, dtype=np.float64)


def relative_velocity_km_s(
    a: tuple[float, float, float], b: tuple[float, float, float]
) -> np.ndarray:
    """Relative velocity of a with respect to b, in km/s."""
    return np.asarray(a, dtype=np.float64) - np.asarray(b, dtype=np.float64)


def separation_km(
    a: tuple[float, float, float], b: tuple[float, float, float]
) -> float:
    """Euclidean separation between two position vectors, in km."""
    return _norm(relative_position_km(a, b))


def relative_speed_km_s(
    a: tuple[float, float, float], b: tuple[float, float, float]
) -> float:
    """Relative speed between two velocity vectors, in km/s."""
    return _norm(relative_velocity_km_s(a, b))
