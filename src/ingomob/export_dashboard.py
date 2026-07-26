"""Assemble ``dashboard/data.json`` - the single payload the static dashboard reads."""
from __future__ import annotations

import datetime as dt
import json

import pandas as pd

from .config import Settings, load_settings
from .errors import NotBuiltError
from .logging_conf import get_logger
from .warehouse import query_df, table_exists

log = get_logger(__name__)

SOURCE_LABELS = {
    "demo": {"label": "Demo (synthetic, seeded)",
             "detail": "Generated locally to the real Ingolstadt/VGI schemas. Figures are "
                       "illustrative and must not be read as official statistics."},
    "live": {"label": "Live (official open data)",
             "detail": "Downloaded from DWD Open Data, VGI GTFS and OpenStreetMap/Overpass."},
}


def _records(df: pd.DataFrame) -> list[dict]:
    return json.loads(df.to_json(orient="records", date_format="iso"))


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def build_dashboard_data(settings: Settings | None = None) -> dict:
    s = settings or load_settings()
    if not table_exists("mart_route_service"):
        raise NotBuiltError("Warehouse not built. Run 'ingomob warehouse' first.")

    routes = query_df("SELECT * FROM mart_route_service ORDER BY avg_peak_headway_min")
    routes["route_short_name"] = routes["route_short_name"].astype(str)
    district = query_df("SELECT * FROM mart_district_scorecard ORDER BY avg_daily_traffic DESC")
    daily = query_df("SELECT date, total_count, is_weekend, is_holiday, holiday_name "
                     "FROM mart_daily_traffic ORDER BY date")
    hourly = query_df("""
        SELECT f.hour, dd.is_weekend, ROUND(AVG(f.vehicle_count),1) AS avg_count
        FROM fact_traffic f JOIN dim_date dd ON dd.date_key=f.date_key
        GROUP BY f.hour, dd.is_weekend ORDER BY f.hour""")
    hourly_roadtype = query_df("SELECT hour, road_type, avg_count FROM mart_hourly_profile "
                               "WHERE is_weekend = FALSE ORDER BY road_type, hour")
    detectors = query_df("SELECT detector_id, detector_name, lat, lon, road_type, district "
                         "FROM dim_detector")
    charging = query_df("SELECT station_id, station_name, operator, lat, lon, num_points, "
                        "power_kw, district FROM dim_charging_station")
    stops = query_df("SELECT stop_id, stop_name, district, lat, lon, departures_weekday, "
                     "departures_sunday FROM mart_stop_service")

    metrics_path = s.processed_dir / "forecast_metrics.json"
    if not metrics_path.exists():
        raise NotBuiltError(
            "forecast_metrics.json is missing - the dashboard would show empty KPIs. "
            "Run 'ingomob forecast' (or 'run-all') first.")
    metrics = _read_json(metrics_path)
    siting = _read_json(s.processed_dir / "siting_summary.json")
    transit = _read_json(s.processed_dir / "transit_quality.json")
    dq = _read_json(s.processed_dir / "data_quality_report.json")

    def _csv(name):
        p = s.processed_dir / name
        return _records(pd.read_csv(p)) if p.exists() else []

    cv = metrics.get("cv", {}).get("summary", {})
    kpis = {
        "n_detectors": int(len(detectors)),
        "n_stops": int(len(stops)),
        "n_routes": int(len(routes)),
        "n_charging_stations": int(len(charging)),
        "n_charging_points": int(charging["num_points"].sum()),
        "total_charging_kw": int((charging["num_points"] * charging["power_kw"]).sum()),
        "avg_daily_traffic_citywide": int(daily["total_count"].mean()) if len(daily) else 0,
        "forecast_mae": cv.get("model", {}).get("mae", {}).get("mean"),
        "forecast_mae_std": cv.get("model", {}).get("mae", {}).get("std"),
        "forecast_r2": cv.get("model", {}).get("r2", {}).get("mean"),
        "baseline_mae": cv.get("seasonal_naive", {}).get("mae", {}).get("mean"),
        "calendar_only_mae": cv.get("calendar_only", {}).get("mae", {}).get("mean"),
        "lift_over_calendar_pct": metrics.get("lift_over_calendar_only_pct"),
        "avg_peak_headway_min": round(float(routes["avg_peak_headway_min"].mean()), 1),
        "n_underserved_stops": transit.get("n_underserved_stops"),
        "n_stops_without_sunday_service": transit.get("n_stops_without_sunday_service"),
        "dq_rows_checked": dq.get("total_rows_checked"),
        "dq_all_passed": dq.get("all_passed"),
    }

    # Explanations rendered as tooltips in the UI - no unexplained raw numbers.
    glossary = {
        "avg_daily_traffic_citywide": "Mean vehicles counted per day across all loop detectors.",
        "forecast_mae": "Mean absolute error of the demand model, averaged over "
                        f"{metrics.get('cv', {}).get('n_folds', '?')} rolling-origin CV folds "
                        "(± is the spread across folds). Lower is better.",
        "forecast_r2": "Share of hourly variance explained by the model (0-1), mean across folds.",
        "baseline_mae": "Seasonal-naive baseline: predict the same hour one week earlier.",
        "calendar_only_mae": "A model using only calendar and weather features - the honest "
                             "benchmark to beat.",
        "lift_over_calendar_pct": "How much the full model improves on the calendar-only model.",
        "avg_peak_headway_min": "Mean minutes between consecutive departures during "
                                "07:00-09:00 and 16:00-18:00.",
        "n_underserved_stops": "Stops in the bottom quintile of weekday departures.",
        "n_charging_points": "Individual charging connectors (a station may have several).",
        "dq_rows_checked": "Rows validated by the data-quality gate before any analysis ran.",
    }

    dates = daily["date"].astype(str) if len(daily) else pd.Series(dtype=str)
    data = {
        "meta": {
            "city": "Ingolstadt",
            "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
            "source_mode": s.source,
            "source_label": SOURCE_LABELS[s.source]["label"],
            "source_detail": SOURCE_LABELS[s.source]["detail"],
            "window": {"start": dates.min() if len(dates) else None,
                       "end": dates.max() if len(dates) else None},
            "data_quality": {"rows_checked": dq.get("total_rows_checked"),
                             "all_passed": dq.get("all_passed"),
                             "engine": dq.get("engine")},
        },
        "kpis": kpis,
        "glossary": glossary,
        "filters": {"districts": sorted(district["district"].tolist()),
                    "road_types": sorted(detectors["road_type"].unique().tolist())},
        "hourly_profile": _records(hourly),
        "hourly_by_roadtype": _records(hourly_roadtype),
        "daily_traffic": _records(daily),
        "forecast": {"metrics": metrics, "timeseries": _csv("forecast_timeseries.csv")},
        "routes": _records(routes),
        "district_scorecard": _records(district),
        "detectors": _records(detectors),
        "charging_stations": _records(charging),
        "stops": _records(stops),
        "siting": {"summary": siting, "grid": _csv("siting_grid.csv")},
    }
    s.dashboard_dir.mkdir(parents=True, exist_ok=True)
    out = s.dashboard_dir / "data.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("dashboard payload: %s (%s bytes)", out.name, f"{out.stat().st_size:,}")
    return {"path": str(out), "bytes": out.stat().st_size, "kpis": kpis}
