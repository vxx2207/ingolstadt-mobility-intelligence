"""Data contracts.

A single declaration of the columns and semantics every raw dataset must have,
regardless of whether it came from the ``demo`` generator or a ``live``
download. Both source modes are validated against these contracts *before*
ingestion, which is what makes the two modes interchangeable.
"""
from __future__ import annotations

from dataclasses import dataclass

from .errors import SchemaError


@dataclass(frozen=True)
class TableSchema:
    name: str
    required_columns: tuple[str, ...]
    description: str

    def validate(self, df, path: str = "") -> None:
        """Raise SchemaError if required columns are missing or the frame is empty."""
        missing = [c for c in self.required_columns if c not in df.columns]
        where = f" in {path}" if path else ""
        if missing:
            raise SchemaError(
                f"{self.name}{where}: missing required column(s) {missing}. "
                f"Found: {list(df.columns)}"
            )
        if len(df) == 0:
            raise SchemaError(f"{self.name}{where}: table is empty - refusing to build on no data.")


TRAFFIC_COUNTS = TableSchema(
    "traffic_counts",
    ("detector_id", "date", "hour", "vehicle_count"),
    "Hourly vehicle counts per loop detector.",
)
TRAFFIC_DETECTORS = TableSchema(
    "traffic_detectors",
    ("detector_id", "name", "lat", "lon", "road_type", "district"),
    "Loop-detector inventory with location and road classification.",
)
CHARGING_STATIONS = TableSchema(
    "charging_stations",
    ("station_id", "name", "operator", "lat", "lon", "num_points", "power_kw", "district"),
    "EV charging stations with connector count and rated power.",
)
WEATHER = TableSchema(
    "weather",
    ("date", "hour", "temp_c", "precip_mm"),
    "Hourly weather observations (temperature, precipitation).",
)
GTFS_STOPS = TableSchema(
    "gtfs_stops", ("stop_id", "stop_name", "stop_lat", "stop_lon"), "GTFS stops.txt")
GTFS_ROUTES = TableSchema(
    "gtfs_routes", ("route_id", "route_short_name", "route_long_name", "route_type"),
    "GTFS routes.txt")
GTFS_TRIPS = TableSchema(
    "gtfs_trips", ("route_id", "service_id", "trip_id"), "GTFS trips.txt")
GTFS_STOP_TIMES = TableSchema(
    "gtfs_stop_times", ("trip_id", "stop_id", "stop_sequence", "departure_time"),
    "GTFS stop_times.txt")

ALL_SCHEMAS = (
    TRAFFIC_COUNTS, TRAFFIC_DETECTORS, CHARGING_STATIONS, WEATHER,
    GTFS_STOPS, GTFS_ROUTES, GTFS_TRIPS, GTFS_STOP_TIMES,
)
