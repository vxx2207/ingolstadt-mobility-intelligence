"""The data-quality gate must actually FAIL on bad data.

The previous revision only ever tested the happy path, so nothing proved the
gate could catch anything.
"""
from __future__ import annotations

import pandas as pd
import pytest

from ingomob import quality
from ingomob.errors import DataQualityError, SourceError
from ingomob.java_validate import run_validation


def _seed_valid(s):
    pd.DataFrame({"detector_id": ["D1", "D1"], "date": ["2025-01-01", "2025-01-01"],
                  "hour": [0, 1], "vehicle_count": [10, 12]}
                 ).to_csv(s.raw_dir / "traffic_counts.csv", index=False)
    pd.DataFrame({"station_id": ["CS1"], "name": ["x"], "operator": ["o"],
                  "lat": [48.76], "lon": [11.42], "num_points": [2], "power_kw": [22],
                  "district": ["Mitte"]}).to_csv(s.raw_dir / "charging_stations.csv", index=False)
    pd.DataFrame({"stop_id": ["S1"], "stop_name": ["n"], "stop_lat": [48.76],
                  "stop_lon": [11.42]}).to_csv(s.gtfs_dir / "stops.txt", index=False)


def test_clean_data_passes(isolated_env):
    _seed_valid(isolated_env)
    assert quality.evaluate(isolated_env)["all_passed"] is True


@pytest.mark.parametrize("rule,mutate", [
    ("vehicle_count_non_negative",
     lambda df: df.assign(vehicle_count=[-5, 12])),
    ("valid_date_format",
     lambda df: df.assign(date=["01.01.2025", "2025-01-01"])),
    ("hour_in_range",
     lambda df: df.assign(hour=[99, 1])),
    ("no_duplicate_detector_hour",
     lambda df: pd.concat([df, df.iloc[[0]]], ignore_index=True)),
])
def test_each_traffic_rule_catches_its_defect(isolated_env, rule, mutate):
    _seed_valid(isolated_env)
    path = isolated_env.raw_dir / "traffic_counts.csv"
    mutate(pd.read_csv(path)).to_csv(path, index=False)
    report = quality.evaluate(isolated_env)
    failing = {c["name"] for c in report["checks"] if c["failed"]}
    assert rule in failing, f"{rule} did not fire; failing={failing}"
    assert report["all_passed"] is False


def test_out_of_bbox_coordinates_are_caught(isolated_env):
    _seed_valid(isolated_env)
    pd.DataFrame({"station_id": ["CS1"], "name": ["x"], "operator": ["o"],
                  "lat": [52.52], "lon": [13.40],  # Berlin, not Ingolstadt
                  "num_points": [1], "power_kw": [22], "district": ["Mitte"]}
                 ).to_csv(isolated_env.raw_dir / "charging_stations.csv", index=False)
    failing = {c["name"] for c in quality.evaluate(isolated_env)["checks"] if c["failed"]}
    assert "coords_within_bbox" in failing


def test_enforce_raises_and_pipeline_aborts(isolated_env):
    _seed_valid(isolated_env)
    path = isolated_env.raw_dir / "traffic_counts.csv"
    pd.read_csv(path).assign(vehicle_count=[-1, -2]).to_csv(path, index=False)
    with pytest.raises(DataQualityError):
        run_validation(prefer_java=False, strict=True, settings=isolated_env)


def test_no_strict_mode_returns_report_instead_of_raising(isolated_env):
    _seed_valid(isolated_env)
    path = isolated_env.raw_dir / "traffic_counts.csv"
    pd.read_csv(path).assign(vehicle_count=[-1, -2]).to_csv(path, index=False)
    report = run_validation(prefer_java=False, strict=False, settings=isolated_env)
    assert report["all_passed"] is False


def test_missing_input_file_gives_actionable_error(isolated_env):
    with pytest.raises(SourceError) as exc:
        quality.evaluate(isolated_env)
    assert "not found" in str(exc.value)


def test_rule_names_match_java_implementation(isolated_env):
    """Guards against the Python and Java engines drifting apart."""
    java_src = (isolated_env.java_dir / "src/com/ingomob/dq/DataQualityValidator.java").read_text()
    for rule in quality.RULE_NAMES:
        assert f'"{rule}"' in java_src, f"Java validator is missing rule {rule}"
