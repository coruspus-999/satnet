"""Application service orchestrating propagation -> ML boundary -> screening -> risk."""
from __future__ import annotations

import time
from uuid import uuid4

from satnet.application.store import SimulationRecord
from satnet.domain.models import ConjunctionEvent, SimulationSummary
from satnet.physics.ml_boundary import SafeTrajectoryModel
from satnet.risk.classifier import RiskClassifier
from satnet.risk.pc import ProbabilityOfCollisionCalculator
from satnet.risk.screening import ConjunctionDetectionService, ConjunctionRefiner, SpatialScreeningService


class SimulationService:
    def __init__(
        self,
        propagation,
        ml: SafeTrajectoryModel,
        risk_classifier: RiskClassifier,
        pc_calculator: ProbabilityOfCollisionCalculator,
        store,
    ):
        self.propagation = propagation
        self.ml = ml
        self.risk_classifier = risk_classifier
        self.pc_calculator = pc_calculator
        self.store = store

    def run(self, tles, config, safety_radius_km: float, ml_enabled: bool = False):
        started = time.perf_counter()
        simulation_id = str(uuid4())

        trajectories = self.propagation.propagate_many(tles, config)
        ml_result = self.ml.apply(trajectories, ml_enabled)

        screening = SpatialScreeningService(safety_radius_km)
        detection = ConjunctionDetectionService(
            screening, ConjunctionRefiner(self.propagation.propagator)
        )
        candidates, raw_events = detection.detect(ml_result.trajectories)

        events: list[ConjunctionEvent] = []
        for sat_a, sat_b, tca, miss_km, rel_speed in raw_events:
            # Pc is reported explicitly as unavailable: no covariance source
            # exists in this system and none is fabricated. The screening miss
            # distance drives the geometric classification only.
            pc_result = self.pc_calculator.availability_report()
            pc_value = pc_result.value
            level, reason = self.risk_classifier.classify(miss_km, pc_value)
            events.append(
                ConjunctionEvent(
                    satellite_a=str(sat_a),
                    satellite_b=str(sat_b),
                    tca=tca,
                    miss_distance_km=miss_km,
                    relative_velocity_km_s=rel_speed,
                    pc=pc_value,
                    pc_status=pc_result.status,
                    risk_level=level,
                    risk_reason=reason,
                )
            )

        elapsed = time.perf_counter() - started
        summary = SimulationSummary(
            simulation_id=simulation_id,
            status="completed",
            satellite_count=len(tles),
            candidate_pairs=len(candidates),
            conjunction_count=len(events),
            duration_seconds=(config.end_time - config.start_time).total_seconds(),
            processing_time_seconds=elapsed,
            ml_enabled=ml_result.enabled,
            ml_fallback_used=ml_result.fallback_used,
            warning=ml_result.warning,
            conjunctions=events,
        )
        self.store.save(SimulationRecord(summary, ml_result.trajectories))
        return summary
