# API

- `GET /api/health`
- `POST /api/tle/upload`
- `POST /api/tle/fetch`
- `POST /api/simulations`
- `GET /api/simulations/{simulation_id}`
- `GET /api/simulations/{simulation_id}/trajectories`
- `GET /api/simulations/{simulation_id}/conjunctions`
- `GET /api/reports/{simulation_id}/csv`
- `GET /api/reports/{simulation_id}/pdf`

Simulation requests require timezone-aware UTC `start_time` and `end_time`.

Trajectory responses explicitly declare `TEME`, `km`, and `km/s`.
