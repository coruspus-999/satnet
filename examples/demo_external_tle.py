"""Real-external-data demo for SatNet.

This demo exercises the pipeline with live public TLE data (not the in-memory
fixtures used in unit tests). It:

1. Fetches a real TLE group from a remote source.
2. Persists a small deterministic subset to a local file for offline replay.
3. Propagates the subset over a short window.
4. Runs geometric screening and reports candidate pairs.
5. Explicitly reports Pc as UNAVAILABLE (no covariance source).

Coordinate frame: TEME (native SGP4 output).
Units: position km, velocity km/s.
Time: UTC.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from satnet.application.simulation import SimulationService
from satnet.application.store import SimulationStore
from satnet.core.config import get_settings
from satnet.domain.models import PropagationConfig
from satnet.ingestion.fetcher import TLEFetcher
from satnet.ingestion.service import TLEIngestionService
from satnet.physics.ml_boundary import SafeTrajectoryModel
from satnet.physics.propagation import TrajectoryPropagationService
from satnet.risk.classifier import RiskClassifier, RiskThresholds
from satnet.risk.pc import ProbabilityOfCollisionCalculator

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

OUTPUT_FILE = Path(__file__).resolve().parent / "starlink_subset.tle"


async def main() -> None:
    settings = get_settings()
    url = settings.tle_source_url

    # 1. Fetch a real group. "stations" is small, reliable, and contains ISS.
    logger.info("Fetching real TLE group 'stations' from %s ...", url)
    service = TLEIngestionService(fetcher=TLEFetcher(timeout_seconds=90.0))
    records, report, raw_text = await service.fetch_and_parse_with_report(
        url,
        {"GROUP": "stations", "FORMAT": "tle"},
        desired_count=30,
        return_raw_text=True,
    )
    logger.info(
        "Fetched %d unique satellites (diagnostics: accepted=%d, failed_norad=%s)",
        report.unique_satellites,
        report.accepted,
        report.failed_norad_ids,
    )

    if not records:
        logger.error("No records returned. Cannot continue demo.")
        return

    # 2. Keep a deterministic, small subset (sorted by NORAD) for a manageable demo.
    subset = sorted(records, key=lambda r: r.norad_id)[:6]
    logger.info(
        "Keeping a deterministic subset of %d satellites for the demo:",
        len(subset),
    )
    for rec in subset:
        logger.info("  NORAD %5d  %s", rec.norad_id, rec.name[:30])

    # Persist the subset for offline replay.
    lines: list[str] = []
    for rec in subset:
        lines.append(rec.name)
        lines.append(rec.line1)
        lines.append(rec.line2)
    OUTPUT_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("Persisted demo subset to %s", OUTPUT_FILE)

    # 3. Propagate + screen via the application service.
    now = datetime.now(timezone.utc)
    config = PropagationConfig(
        start_time=now,
        end_time=now + timedelta(minutes=120),
        time_step_seconds=60,
    )

    sim = SimulationService(
        propagation=TrajectoryPropagationService(),
        ml=SafeTrajectoryModel(),
        risk_classifier=RiskClassifier(RiskThresholds()),
        pc_calculator=ProbabilityOfCollisionCalculator(),
        store=SimulationStore(),
    )

    summary = sim.run(subset, config, safety_radius_km=25.0, ml_enabled=False)
    logger.info(
        "Simulation complete: %s | satellites=%d | candidates=%d | conjunctions=%d | elapsed=%.3fs",
        summary.status,
        summary.satellite_count,
        summary.candidate_pairs,
        summary.conjunction_count,
        summary.processing_time_seconds,
    )

    logger.info("\nConjunction events (screening, NOT Pc):")
    if not summary.conjunctions:
        logger.info("  (none within the configured safety radius during this window)")
    for ev in summary.conjunctions:
        logger.info(
            "  %s <-> %s  TCA=%s  miss=%.3f km  rel_v=%.3f km/s  risk=%s  Pc=%s (%s)",
            ev.satellite_a,
            ev.satellite_b,
            ev.tca.isoformat(),
            ev.miss_distance_km,
            ev.relative_velocity_km_s,
            ev.risk_level.value,
            ev.pc if ev.pc is not None else "UNAVAILABLE",
            ev.pc_status,
        )

    if summary.conjunctions:
        logger.info("\nPc note: %s", summary.conjunctions[0].pc_status)
    logger.info(
        "Probability of collision is UNAVAILABLE because no covariance source is present."
    )


if __name__ == "__main__":
    asyncio.run(main())
