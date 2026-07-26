# Data sources

The pipeline runs in two interchangeable modes that emit identical schemas
(`src/ingomob/schemas.py`), so every downstream stage is source-agnostic.

## `live` — real open data

| Domain | Provider | Endpoint | Format | Status |
|---|---|---|---|---|
| Hourly weather | Deutscher Wetterdienst (CDC) | `opendata.dwd.de/.../climate/hourly/air_temperature/recent/` | `;`-separated in ZIP, latin-1, `-999` = missing | Implemented; nearest station discovered at runtime |
| Public transport | VGI / INVG | GTFS static archive (`INGOMOB_GTFS_URL`) | GTFS ZIP | Implemented |
| EV charging | OpenStreetMap via Overpass API | `overpass-api.de/api/interpreter` | JSON | Implemented |
| Traffic counts | City of Ingolstadt loop detectors | — | — | **Not publicly available as an open feed.** Supply a local export via `INGOMOB_TRAFFIC_CSV` |

Related portals worth citing: the city publishes 200+ datasets on
[ingolstadt.bydata.de](https://ingolstadt.bydata.de) (Bavarian open-data portal), and the
Bundesnetzagentur maintains the authoritative German charging register.

**Verification status.** The live parsers are covered by tests that replay the exact
real-world formats through a local HTTP server (see `tests/test_live_source.py`). The
production endpoints themselves were **not** contacted from the environment this project
was built in, which had no outbound network. Run the `live-smoke` GitHub Actions workflow
or `python -m ingomob.cli --source live generate` on a networked machine to confirm.

## `demo` — synthetic, default

Seeded generation conforming to the same schemas, so the repository is fully reproducible
and CI never depends on a third-party endpoint. The generator models a diurnal profile,
weekday/weekend/holiday and school-holiday effects, weather elasticity, a mean-reverting
per-detector level with multi-week roadworks shifts, AR(1) residuals, incident spikes,
stuck-at-zero sensor faults and missing hours.

**Every value is synthetic.** Nothing produced in `demo` mode is a statement about
Ingolstadt, and all artefacts are labelled with their source mode.

## Licensing
DWD Open Data is provided under the GeoNutzV / DL-DE-BY-2.0 terms; OpenStreetMap data is
ODbL; GTFS feeds follow the publishing agency's terms. Check each provider before
redistributing derived data.
