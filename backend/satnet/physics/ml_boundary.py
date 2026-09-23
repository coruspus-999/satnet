"""ML boundary shim for trajectory refinement.

This module exists so the simulation can *optionally* consult a trajectory
refinement model without the rest of the system knowing anything about ML.

Today nothing is wired (ml_enabled is treated as a no-op), so this is a safe
place to land real model integration later without touching the simulation
orchestration.
"""
from __future__ import annotations

from dataclasses import dataclass

from satnet.domain.exceptions import MLInferenceError


@dataclass(frozen=True)
class MLResult:
    """Result of an optional ML refinement pass.

    Attributes:
        trajectories: the (possibly refined) trajectories to use downstream.
        enabled: whether the model was actually invoked.
        fallback_used: whether the model failed and the safe SGP4 fallback was
            retained.
        warning: optional human-readable warning when a fallback was used.
    """
    trajectories: list
    enabled: bool
    fallback_used: bool
    warning: str | None = None


class TrajectoryRefinementModel:
    """Interface for an optional trajectory refinement model."""

    def predict(self, trajectories: list) -> list:
        raise NotImplementedError


class SafeTrajectoryModel:
    """Safe wrapper around an optional refinement model.

    If no model is set, or if ML is disabled, this is a no-op: trajectories
    pass through unchanged.  If a model is set and enabled but raises, the
    wrapper logs and falls back to the original SGP4 trajectories rather than
    crashing the simulation.
    """

    def __init__(self, model: TrajectoryRefinementModel | None = None) -> None:
        self.model = model

    def apply(
        self, trajectories: list, enabled: bool = False
    ) -> MLResult:
        if not enabled or self.model is None:
            return MLResult(trajectories=trajectories, enabled=False, fallback_used=False)

        try:
            refined = self.model.predict(trajectories)
        except Exception as exc:  # noqa: BLE001 - fallback, not crash
            return MLResult(
                trajectories=trajectories,
                enabled=True,
                fallback_used=True,
                warning=f"ML inference failed; SGP4 fallback used: {exc}",
            )

        if len(refined) != len(trajectories):
            raise MLInferenceError(
                "ML model returned an invalid trajectory count "
                f"({len(refined)} vs {len(trajectories)} expected)."
            )
        return MLResult(trajectories=refined, enabled=True, fallback_used=False)
