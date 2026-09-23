# External TLE demo scripts

These scripts exercise SatNet against **live public TLE data from CelesTrak**
rather than the bundled local fixtures, so you can verify the pipeline against
other inputs than the training/data files shipped in the repo.

All scripts use the `TLEIngestionService` (fetch → parse → validate → dedup)
and write the raw TLE text to disk so the rest of the demo can run offline.

## Prerequisites

From the repo root (the `.venv` is at the project root, not under `backend/`):

```bash
# Activate the project venv
.venv/Scripts/activate      # Windows
# or
source .venv/bin/activate   # POSIX

# Ensure the backend package is importable
export PYTHONPATH=backend   # POSIX
set PYTHONPATH=backend      # Windows
```

## 1. `fetch_tle_group.py` — download a CelesTrak group to disk

```bash
python examples/fetch_tle_group.py --group visual --output tle_visual.tle
python examples/fetch_tle_group.py --group stations --output tle_stations.tle
python examples/fetch_tle_group.py --group galileo --output tle_galileo.tle
python examples/fetch_tle_group.py --group sarsat --output tle_sarsat.tle
```

Known-good external groups (parse + validate end-to-end with zero rejections):

- `visual`  — brightest 156 satellites
- `stations` — human-occupied spacecraft (ISS modules, CSS, etc.)
- `galileo` — EU Galileo navigation satellites
- `sarsat`  — search-and-rescue payloads

Groups that currently need parser tweaks (server returns a non-TLE header
line that the parser rejects as "incomplete record"):

- `noaa`, `iridium`

Groups that are currently 403-forbidden from this environment's CelesTrak
access (outside our control):

- `starlink`

## 2. `fetch_demo_tle.py` — lightweight demo fetch

```bash
python examples/fetch_demo_tle.py --group visual --output tle_demo.tle
python examples/fetch_demo_tle.py --group stations --output tle_demo.tle
```

This is a smaller, demo-oriented wrapper around the same ingestion service.

## Persisted artifacts

After running the scripts you will typically have:

- `tle_visual.tle`   — 156 satellites (visual group)
- `tle_stations.tle` — 20 satellites (stations group)
- `tle_demo.tle`     — whatever the last `fetch_demo_tle.py` run downloaded

These files are plain TLE text and can be fed to the rest of the system
(parser, propagator, screening, simulation) as if they were uploaded.

## Offline replay

Once a TLE file has been downloaded, you can run the rest of the demo
without the network by pointing the parser/propagator at the on-disk file:

```bash
python - <<'PY'
from pathlib import Path
from satnet.ingestion.parser import TLEParser
from satnet.physics.propagation import TrajectoryPropagationService
from datetime import datetime, timedelta, timezone

text = Path("tle_visual.tle").read_text(encoding="utf-8")
records = TLEParser().parse(text, "tle_visual.tle")
subset = sorted(records, key=lambda r: r.norad_id)[:6]

config = _now_window := (
    lambda h=2, s=300: type("C", (), {
        "start_time": datetime.now(timezone.utc),
        "_": None,
    })()
)
# In real code, build a proper PropagationConfig:
from satnet.domain.models import PropagationConfig
config = PropagationConfig(
    start_time=datetime.now(timezone.utc),
    end_time=datetime.now(timezone.utc) + timedelta(hours=2),
    time_step_seconds=300,
)

trajs = TrajectoryPropagationService().propagate_many(subset, config)
print(f"Propagated {len(trajs)} trajectories from {len(subset)} satellites")
for t in trajs:
    print(f"  {t.states[0].position_km=}")
PY
```

## Notes

- These scripts hit the network. When offline, use the persisted `.tle` files
  instead and skip the fetch scripts.
- The pytest suite has a `@pytest.mark.live` marker for the network-dependent
  integration tests; deselect them in CI with `-m "not live"`.
