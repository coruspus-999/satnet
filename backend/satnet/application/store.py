from __future__ import annotations
from dataclasses import dataclass
from threading import RLock
from satnet.domain.models import SimulationSummary, Trajectory

@dataclass
class SimulationRecord:
    summary: SimulationSummary
    trajectories: list[Trajectory]

class SimulationStore:
    def __init__(self, repository=None):
        self.repository = repository
        self._records = {}
        self._lock = RLock()
    def save(self, record: SimulationRecord):
        with self._lock:
            self._records[record.summary.simulation_id] = record
            if self.repository:
                self.repository.save_summary(record.summary)
    def get(self, simulation_id: str):
        with self._lock:
            record = self._records.get(simulation_id)
        if record is not None:
            return record
        summary = self.repository.get_summary(simulation_id) if self.repository else None
        if summary is None:
            return None
        # Persisted summaries intentionally do not recreate large trajectory arrays.
        return SimulationRecord(summary=summary, trajectories=[])
