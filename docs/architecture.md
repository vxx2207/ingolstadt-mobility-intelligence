# Architecture

## Pipeline

```mermaid
flowchart LR
  subgraph SRC["Source layer (interchangeable)"]
    D["demo · seeded generator"]
    L["live · DWD / GTFS / Overpass"]
  end
  DQ["Data-quality gate<br/>9 rules · Java 11 or Python<br/>exit 2 on failure"]
  ING["Ingest → DuckDB staging<br/>(schema contracts enforced)"]
  WH[("DuckDB star schema<br/>7 dims · 3 facts · 5 marts")]
  AN["Analytics<br/>transit quality · charging siting"]
  ML["Forecast<br/>rolling-origin CV · baseline ladder"]
  OUT["data.json · figures · report"]
  UI["Plotly dashboard<br/>GitHub Pages"]

  D --> DQ
  L --> DQ
  DQ --> ING --> WH
  WH --> AN --> OUT
  WH --> ML --> OUT
  OUT --> UI
```

Both source modes write the same files in the same schemas
(`src/ingomob/schemas.py`), so nothing downstream knows or cares which one ran.

## Star schema

```mermaid
erDiagram
  dim_date       ||--o{ fact_traffic : date_key
  dim_detector   ||--o{ fact_traffic : detector_key
  dim_district   ||--o{ fact_traffic : district_key
  dim_route      ||--o{ fact_stop_departures : route_key
  dim_stop       ||--o{ fact_stop_departures : stop_key
  dim_district   ||--o{ fact_charging : district_key
  dim_charging_station ||--o{ fact_charging : station_key
```

| Layer | File | Builds |
|---|---|---|
| Dimensions | `sql/01_dimensions.sql` | `dim_date` (incl. public + school holidays), `dim_time`, `dim_district`, `dim_stop`, `dim_route`, `dim_detector`, `dim_charging_station` |
| Facts | `sql/02_facts.sql` | `fact_traffic`, `fact_stop_departures`, `fact_charging` |
| Marts | `sql/03_marts.sql` | `mart_hourly_profile`, `mart_daily_traffic`, `mart_route_service`, `mart_stop_service`, `mart_district_scorecard` |

## Module map

| Module | Responsibility |
|---|---|
| `config.py` | Environment-driven `Settings`, validated on load |
| `errors.py` | Typed exceptions, each with an actionable hint |
| `logging_conf.py` | Structured logging, level via `INGOMOB_LOG_LEVEL` |
| `schemas.py` | Column contracts shared by both source modes |
| `http_client.py` | Retries, backoff, disk cache, SHA-256 provenance |
| `sources/demo.py` | Seeded stochastic generator |
| `sources/live.py` | Real downloads + format parsers |
| `quality.py` / `java_validate.py` | Rule spec / engine dispatch |
| `warehouse.py` | DuckDB access, quote-aware SQL splitter |
| `features.py`, `forecast.py` | Leakage-audited features, rolling-origin CV |
| `siting.py`, `transit_quality.py` | Domain analytics |
| `export_dashboard.py`, `plots.py`, `report.py` | Outputs |
| `cli.py` | Subcommands, exit codes, `doctor`, `serve` |

## Design decisions

- **DuckDB** — embedded columnar warehouse: zero ops, standard SQL, single file, trivially
  reviewable in a portfolio context.
- **Star schema** — keeps marts simple and mirrors how a BI tool would consume the data.
- **Static client-side dashboard** — one generated `data.json` plus Plotly, so it deploys to
  GitHub Pages with no backend and no secrets.
- **Two source modes instead of faking one** — synthetic data keeps CI hermetic and
  deterministic; live mode proves the same code handles real formats.
- **Quality gate before ingestion** — bad data must fail loudly and early, not produce a
  clean-looking dashboard built on nonsense.
