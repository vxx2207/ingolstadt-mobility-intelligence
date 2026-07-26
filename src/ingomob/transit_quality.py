"""Public-transport service-quality analytics derived from the GTFS marts."""
from __future__ import annotations

import json

from .config import Settings, load_settings
from .errors import NotBuiltError
from .logging_conf import get_logger
from .warehouse import query_df, table_exists

log = get_logger(__name__)


def summarize(settings: Settings | None = None) -> dict:
    s = settings or load_settings()
    if not table_exists("dim_route"):
        raise NotBuiltError("Warehouse not built. Run 'ingomob warehouse' first.")
    routes = query_df("SELECT * FROM mart_route_service ORDER BY route_short_name")
    stops = query_df("SELECT * FROM mart_stop_service")
    if routes.empty or stops.empty:
        raise NotBuiltError("Transit marts are empty - check the GTFS input.")

    served = stops[stops["departures_weekday"] > 0]
    threshold = float(served["departures_weekday"].quantile(0.20))
    underserved = served[served["departures_weekday"] <= threshold]
    no_sunday = stops[stops["departures_sunday"] == 0]

    best = routes.loc[routes["avg_peak_headway_min"].idxmin()]
    worst = routes.loc[routes["avg_peak_headway_min"].idxmax()]
    weekday_trips = int(routes["trips_weekday"].sum())
    sunday_trips = int(routes["trips_sunday"].sum())

    summary = {
        "n_routes": int(len(routes)),
        "n_stops": int(len(stops)),
        "total_weekday_trips": weekday_trips,
        "total_sunday_trips": sunday_trips,
        "weekend_service_ratio_pct": round(sunday_trips / weekday_trips * 100, 1),
        "avg_peak_headway_min": round(float(routes["avg_peak_headway_min"].mean()), 1),
        "best_route": {"line": str(best["route_short_name"]),
                       "headway_min": float(best["avg_peak_headway_min"])},
        "worst_route": {"line": str(worst["route_short_name"]),
                        "headway_min": float(worst["avg_peak_headway_min"])},
        "underserved_stop_threshold_weekday_departures": round(threshold, 1),
        "n_underserved_stops": int(len(underserved)),
        "n_stops_without_sunday_service": int(len(no_sunday)),
        "method_note": ("Headway is the mean gap between consecutive first-stop departures "
                        "inside the 07:00-09:00 and 16:00-18:00 windows. Underserved = bottom "
                        "quintile of weekday departures among stops with any service."),
    }
    s.processed_dir.mkdir(parents=True, exist_ok=True)
    (s.processed_dir / "transit_quality.json").write_text(json.dumps(summary, indent=2, default=str))
    log.info("transit: %d routes, mean peak headway %.1f min, %d underserved stops",
             summary["n_routes"], summary["avg_peak_headway_min"], summary["n_underserved_stops"])
    return summary
