"""SatNet FastAPI surface.

Thin HTTP layer: routers call application services; no orbital physics here.
Domain exceptions are translated to HTTP statuses at the process boundary.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from satnet.application.simulation import SimulationService
from satnet.application.store import SimulationStore
from satnet.core.config import get_settings
from satnet.database import SimulationRepository
from satnet.domain.exceptions import (
    ConjunctionCalculationError,
    PropagationError,
    SatNetError,
    TLEFetchError,
    TLEParseError,
    TLEValidationError,
)
from satnet.domain.models import PropagationConfig
from satnet.ingestion.service import TLEIngestionService
from satnet.physics.ml_boundary import SafeTrajectoryModel
from satnet.physics.propagation import TrajectoryPropagationService
from satnet.risk.classifier import RiskClassifier, RiskThresholds
from satnet.risk.pc import ProbabilityOfCollisionCalculator
from satnet.reporting import ReportService

settings = get_settings()
app = FastAPI(title=settings.app_name, version="1.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SimulationRequest(BaseModel):
    tle_text: str = Field(min_length=70, description="Raw TLE text (2LE/3LE).")
    start_time: datetime = Field(
        description="Simulation start (UTC, timezone-aware)."
    )
    end_time: datetime = Field(
        description="Simulation end (UTC, timezone-aware, after start_time)."
    )
    time_step_seconds: int = Field(
        60, ge=1, le=3600, description="Uniform propagation time step in seconds."
    )
    safety_radius_km: float = Field(
        25.0, gt=0, description="Screening safety radius in km."
    )
    ml_enabled: bool = Field(
        False, description="Enable ML trajectory refinement (no-op until a model is wired)."
    )

    @field_validator("start_time", "end_time")
    @classmethod
    def _require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ValueError("Datetime must be timezone-aware (UTC expected).")
        return value.astimezone(timezone.utc)

    @field_validator("end_time")
    @classmethod
    def _end_after_start(cls, value: datetime, info) -> datetime:
        start = info.data.get("start_time")
        if start is not None and value <= start:
            raise ValueError("end_time must be after start_time.")
        return value


class FetchRequest(BaseModel):
    url: str | None = Field(
        None, description="Override the TLE source URL (defaults to configured CelesTrak URL)."
    )
    group: str = Field(
        "stations", description="TLE group name (e.g. stations, visual, galileo, sarsat)."
    )
    desired_count: int | None = Field(
        None, ge=1, le=100000, description="Approximate number of satellites to request (NUMSATS)."
    )


def configure_app() -> None:
    """Wire services explicitly (dependency composition at the boundary)."""
    repository = SimulationRepository(settings.database_url)
    store = SimulationStore(repository)
    app.state.store = store
    app.state.ingestion = TLEIngestionService()
    app.state.propagation = TrajectoryPropagationService()
    app.state.service = SimulationService(
        propagation=app.state.propagation,
        ml=SafeTrajectoryModel(),
        risk_classifier=RiskClassifier(RiskThresholds()),
        pc_calculator=ProbabilityOfCollisionCalculator(),
        store=store,
    )
    app.state.reports = ReportService()


configure_app()


def _to_http_error(exc: SatNetError, default_status: int) -> HTTPException:
    """Map a domain exception to an HTTP status.

    Wrong user input (parse/validation failures) → 422.
    Remote fetch failures → 502.
    Propagation/conjunction math failures → 422 (bad input geometry), with the
    exception detail exposed so the caller can see what went wrong.
    """
    status = default_status
    if isinstance(exc, (TLEParseError, TLEValidationError)):
        status = 422
    elif isinstance(exc, TLEFetchError):
        status = 502
    elif isinstance(exc, (PropagationError, ConjunctionCalculationError)):
        # These usually indicate bad input geometry/timing, not a server fault.
        status = 422
    return HTTPException(status_code=status, detail=str(exc))


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": "1.1.0",
        "time": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/api/tle/upload")
async def upload_tle(request: Request, file: UploadFile = File(...)) -> dict:
    if not file.filename or not file.filename.lower().endswith(
        (".txt", ".tle")
    ):
        raise HTTPException(400, "Upload a .txt or .tle file.")

    try:
        raw = await file.read()
        text = raw.decode("utf-8", "replace")
        records, _report = request.app.state.ingestion.parse_text_with_report(
            text, f"upload:{file.filename}"
        )
    except SatNetError as exc:
        raise _to_http_error(exc, 422) from exc
    except Exception as exc:  # unexpected I/O / decoding issues → 400
        raise HTTPException(400, f"Failed to read TLE file: {exc}") from exc

    return {
        "count": len(records),
        "records": [r.model_dump(mode="json") for r in records],
    }


@app.post("/api/tle/fetch")
async def fetch_tle(request: Request, req: FetchRequest) -> dict:
    url = req.url or settings.tle_source_url
    params = {"GROUP": req.group, "FORMAT": "tle"}
    try:
        records = await request.app.state.ingestion.fetch_and_parse(
            url, params, req.desired_count
        )
    except SatNetError as exc:
        raise _to_http_error(exc, 502) from exc
    except Exception as exc:
        raise HTTPException(502, f"TLE fetch failed: {exc}") from exc

    return {
        "count": len(records),
        "records": [r.model_dump(mode="json") for r in records],
    }


@app.post("/api/simulations")
def create_simulation(request: Request, req: SimulationRequest) -> dict:
    try:
        records = request.app.state.ingestion.parse_text(req.tle_text, "simulation")
        config = PropagationConfig(
            start_time=req.start_time,
            end_time=req.end_time,
            time_step_seconds=req.time_step_seconds,
        )
        summary = request.app.state.service.run(
            records, config, req.safety_radius_km, req.ml_enabled
        )
    except SatNetError as exc:
        raise _to_http_error(exc, 422) from exc
    except Exception as exc:
        raise HTTPException(422, f"Simulation setup failed: {exc}") from exc
    return summary.model_dump(mode="json")


@app.get("/api/simulations/{simulation_id}")
def get_simulation(request: Request, simulation_id: str) -> dict:
    record = request.app.state.store.get(simulation_id)
    if record is None:
        raise HTTPException(404, "Simulation not found.")
    return record.summary.model_dump(mode="json")


@app.get("/api/simulations/{simulation_id}/conjunctions")
def get_conjunctions(request: Request, simulation_id: str) -> list:
    return get_simulation(request, simulation_id)["conjunctions"]


@app.get("/api/simulations/{simulation_id}/trajectories")
def get_trajectories(request: Request, simulation_id: str) -> dict:
    record = request.app.state.store.get(simulation_id)
    if record is None:
        raise HTTPException(404, "Simulation not found.")
    if not record.trajectories:
        raise HTTPException(
            410,
            "Trajectory data is available only for the active application "
            "process; rerun the simulation to regenerate it.",
        )
    return {
        "simulation_id": simulation_id,
        "frame": "TEME",
        "position_unit": "km",
        "velocity_unit": "km/s",
        "trajectories": [t.model_dump(mode="json") for t in record.trajectories],
    }


def _report_response(request: Request, simulation_id: str, kind: str) -> Response:
    record = request.app.state.store.get(simulation_id)
    if record is None:
        raise HTTPException(404, "Simulation not found.")
    if kind == "csv":
        payload = request.app.state.reports.csv_bytes(record.summary)
        media_type = "text/csv"
    else:
        payload = request.app.state.reports.pdf_bytes(record.summary)
        media_type = "application/pdf"
    return Response(
        payload,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="satnet-{simulation_id}.{kind}"'
        },
    )


@app.get("/api/reports/{simulation_id}/csv")
def report_csv(request: Request, simulation_id: str) -> Response:
    return _report_response(request, simulation_id, "csv")


@app.get("/api/reports/{simulation_id}/pdf")
def report_pdf(request: Request, simulation_id: str) -> Response:
    return _report_response(request, simulation_id, "pdf")
