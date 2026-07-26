"""The dashboard is a separate program that consumes data.json. This test is the
contract between them: if the exporter drops a key the UI reads, CI fails.
"""
from __future__ import annotations

import json
import re

import pytest

from ingomob.config import PROJECT_ROOT
from ingomob.export_dashboard import build_dashboard_data

TOP_LEVEL = ["meta", "kpis", "glossary", "filters", "hourly_profile", "hourly_by_roadtype",
             "daily_traffic", "forecast", "routes", "district_scorecard", "detectors",
             "charging_stations", "stops", "siting"]
KPIS = ["avg_daily_traffic_citywide", "forecast_mae", "forecast_mae_std", "forecast_r2",
        "baseline_mae", "calendar_only_mae", "lift_over_calendar_pct",
        "avg_peak_headway_min", "n_underserved_stops", "n_charging_points",
        "n_stops_without_sunday_service", "n_routes"]


@pytest.fixture(scope="module")
def payload(analytics_ready, forecast_result):
    build_dashboard_data(analytics_ready)
    return json.loads((analytics_ready.dashboard_dir / "data.json").read_text())


def test_top_level_keys(payload):
    d = payload
    for key in TOP_LEVEL:
        assert key in d, f"data.json missing '{key}'"


def test_kpis_present_and_explained(payload):
    d = payload
    for k in KPIS:
        assert k in d["kpis"], f"KPI '{k}' missing"
    # every KPI the UI shows on a card must have a glossary entry
    for k in ["avg_daily_traffic_citywide", "forecast_mae", "lift_over_calendar_pct",
              "avg_peak_headway_min", "n_underserved_stops", "n_charging_points"]:
        assert k in d["glossary"], f"KPI '{k}' has no user-facing explanation"


def test_provenance_is_present(payload):
    m = payload["meta"]
    for k in ("source_mode", "source_label", "source_detail", "generated_at", "data_quality"):
        assert m.get(k) not in (None, ""), f"meta.{k} missing"
    assert m["window"]["start"] and m["window"]["end"]


def test_record_shapes(payload):
    d = payload
    assert {"hour", "is_weekend", "avg_count"} <= set(d["hourly_profile"][0])
    assert {"route_short_name", "avg_peak_headway_min", "trips_weekday"} <= set(d["routes"][0])
    assert {"ts", "actual", "predicted", "baseline"} <= set(d["forecast"]["timeseries"][0])
    assert d["siting"]["summary"]["recommendations"]
    assert {"districts", "road_types"} <= set(d["filters"])


def test_html_only_reads_keys_the_exporter_writes(payload):
    """Catch typos like DATA.kpi vs DATA.kpis."""
    d = payload
    html = (PROJECT_ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
    referenced = set(re.findall(r"DATA\.(\w+)", html))
    unknown = referenced - set(d.keys())
    assert not unknown, f"dashboard reads keys that data.json does not provide: {unknown}"
