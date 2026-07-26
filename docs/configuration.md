# Configuration

Everything is environment-driven; nothing needs editing in code.

| Variable | Default | Purpose |
|---|---|---|
| `INGOMOB_SOURCE` | `demo` | `demo` (offline synthetic) or `live` (real downloads) |
| `INGOMOB_DATA_DIR` | `<repo>/data` | Root for raw / processed / warehouse data |
| `INGOMOB_DB_PATH` | `<data>/warehouse/ingomob.duckdb` | DuckDB file location |
| `INGOMOB_CACHE_DIR` | `<data>/cache` | Cache for downloaded files |
| `INGOMOB_OUTPUT_DIR` | `<repo>` | Where `dashboard/` and `reports/` are written |
| `INGOMOB_LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `INGOMOB_SEED` | `42` | RNG seed for the demo source and the model |
| `INGOMOB_SIM_DAYS` | `180` | Days of demo history (28–1095) |
| `INGOMOB_HTTP_TIMEOUT` | `30` | Per-request timeout in seconds (live mode) |
| `INGOMOB_HTTP_RETRIES` | `3` | Retry attempts with exponential backoff |
| `INGOMOB_GITHUB_USER` | *(empty)* | Used only to render repository links |

### Live-mode endpoint overrides
| Variable | Default |
|---|---|
| `INGOMOB_DWD_STATIONS_URL` | DWD CDC hourly station description |
| `INGOMOB_DWD_BASE` | DWD CDC hourly base URL |
| `INGOMOB_GTFS_URL` | VGI GTFS static archive |
| `INGOMOB_OVERPASS_URL` | `https://overpass-api.de/api/interpreter` |
| `INGOMOB_TRAFFIC_CSV` | Local CSV of loop-detector counts (required for a full live run) |

### Exit codes
| Code | Meaning |
|---|---|
| 0 | success |
| 1 | handled pipeline error (missing input, unbuilt warehouse, bad config) |
| 2 | data-quality gate failed |
| 130 | interrupted |

### Troubleshooting
Run `ingomob doctor` first — it prints the resolved paths, source mode, dependency
versions and whether a JDK is available.

| Symptom | Cause / fix |
|---|---|
| `Warehouse not found` | Run `ingomob warehouse` (or `run-all`) |
| Dashboard shows the error state | Serve over HTTP: `ingomob serve`; `file://` blocks `fetch()` |
| `DownloadError` in live mode | No internet or endpoint moved; override the URL or use `--source demo` |
| Data-quality exit code 2 | Inspect `data/processed/data_quality_report.json` |
| Windows: `make` not found | Use `python -m ingomob.cli <stage>`; `make` is optional |
