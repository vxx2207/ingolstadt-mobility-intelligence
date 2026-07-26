"""Load raw files into DuckDB staging tables, validating contracts first."""
from __future__ import annotations

import pandas as pd

from .config import Settings
from .errors import SourceError
from .logging_conf import get_logger
from .schemas import (
    CHARGING_STATIONS,
    GTFS_ROUTES,
    GTFS_STOP_TIMES,
    GTFS_STOPS,
    GTFS_TRIPS,
    TRAFFIC_COUNTS,
    TRAFFIC_DETECTORS,
    WEATHER,
)

log = get_logger(__name__)


def _sources(s: Settings):
    return {
        "stg_stops": (s.gtfs_dir / "stops.txt", GTFS_STOPS),
        "stg_routes": (s.gtfs_dir / "routes.txt", GTFS_ROUTES),
        "stg_trips": (s.gtfs_dir / "trips.txt", GTFS_TRIPS),
        "stg_stop_times": (s.gtfs_dir / "stop_times.txt", GTFS_STOP_TIMES),
        "stg_calendar": (s.gtfs_dir / "calendar.txt", None),
        "stg_stop_districts": (s.raw_dir / "stop_districts.csv", None),
        "stg_charging": (s.raw_dir / "charging_stations.csv", CHARGING_STATIONS),
        "stg_detectors": (s.raw_dir / "traffic_detectors.csv", TRAFFIC_DETECTORS),
        "stg_weather": (s.raw_dir / "weather.csv", WEATHER),
        "stg_traffic": (s.raw_dir / "traffic_counts.csv", TRAFFIC_COUNTS),
    }


def load_staging(con, settings: Settings) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table, (path, schema) in _sources(settings).items():
        if not path.exists():
            raise SourceError(
                f"Missing raw input for {table}: {path}. Run 'ingomob generate' first.")
        try:
            df = pd.read_csv(path)
        except pd.errors.EmptyDataError as exc:
            raise SourceError(f"{path} is empty - cannot build {table}.") from exc
        except pd.errors.ParserError as exc:
            raise SourceError(f"{path} is not valid CSV: {exc}") from exc
        if schema is not None:
            schema.validate(df, str(path))
        con.register(f"_df_{table}", df)
        con.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM _df_{table}")
        con.unregister(f"_df_{table}")
        counts[table] = len(df)
    log.info("staged %d tables (%s rows total)", len(counts), f"{sum(counts.values()):,}")
    return counts
