# SatNet Architecture

SatNet is a modular monolith. The layers are intentionally separated:

```text
React + Three.js/WebGL
        │ structured REST JSON
        ▼
FastAPI API
        ▼
Application Services
        ├── TLE ingestion
        ├── simulation orchestration
        ├── reporting
        └── simulation store
        ▼
Physics / Risk
        ├── SGP4 baseline propagation (TEME, km, km/s)
        ├── cKDTree screening
        ├── actual-SGP4 local TCA refinement
        ├── risk classifier
        └── isolated Pc boundary
        ▼
Persistence
        └── SQLAlchemy → SQLite locally / MySQL in production
```

The ML layer is an explicit adapter boundary. A failed ML inference never destroys a valid SGP4 result.

## Performance

Propagation uses `Satrec.sgp4_array` when available, avoiding one Python SGP4 call per timestamp. Screening uses `scipy.spatial.cKDTree`. Precise TCA refinement is only run for screened candidate pairs.

The 500-satellite/48-hour target is an engineering target rather than a guarantee; benchmark on the deployment machine with the actual TLE set and timestep before claiming compliance.

## Scientific boundaries

- SGP4 output remains TEME unless an explicit coordinate transformation is implemented.
- Pc is not inferred from miss distance.
- Pc remains unavailable without valid covariance and encounter-plane geometry.
- No maneuver recommendation or autonomous control exists.
- ML is not claimed to improve physical orbit accuracy without validated training evidence.
