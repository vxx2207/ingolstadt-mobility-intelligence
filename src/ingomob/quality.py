"""Data-quality rule engine.

The rule *specification* lives here in one place and is mirrored by the Java
validator. ``tests/test_quality.py`` asserts both engines agree on the same
input, so the two implementations cannot silently drift apart.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass

import pandas as pd

from . import config as C
from .config import Settings
from .errors import DataQualityError, SourceError
from .logging_conf import get_logger

log = get_logger(__name__)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

RULE_NAMES = (
    "vehicle_count_non_negative",
    "no_duplicate_detector_hour",
    "valid_date_format",
    "hour_in_range",
    "power_kw_positive",
    "coords_within_bbox",
    "num_points_ge_1",
    "stop_coords_within_bbox",
    "stop_id_unique",
)


@dataclass
class RuleResult:
    name: str
    table: str
    passed: int
    failed: int
    sample_issues: list

    def as_dict(self) -> dict:
        return {"name": self.name, "table": self.table, "passed": int(self.passed),
                "failed": int(self.failed), "sample_issues": self.sample_issues}


def _in_box(lat, lon) -> bool:
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return False
    return (C.BBOX["min_lat"] <= lat <= C.BBOX["max_lat"]
            and C.BBOX["min_lon"] <= lon <= C.BBOX["max_lon"])


def _rule(name, table, mask: pd.Series) -> RuleResult:
    mask = mask.fillna(False).astype(bool)
    bad = mask.index[~mask][:5]
    return RuleResult(name, table, int(mask.sum()), int((~mask).sum()),
                      [f"row {int(i)}" for i in bad])


def evaluate(settings: Settings) -> dict:
    """Run every rule; returns a JSON-serialisable report."""
    s = settings
    files = {"traffic": s.raw_dir / "traffic_counts.csv",
             "charging": s.raw_dir / "charging_stations.csv",
             "stops": s.gtfs_dir / "stops.txt"}
    for label, path in files.items():
        if not path.exists():
            raise SourceError(f"Data-quality gate: {label} file not found at {path}")

    results: list[RuleResult] = []
    total = 0

    t = pd.read_csv(files["traffic"])
    total += len(t)
    counts = pd.to_numeric(t["vehicle_count"], errors="coerce")
    results.append(_rule("vehicle_count_non_negative", "traffic_counts", counts >= 0))
    results.append(_rule("no_duplicate_detector_hour", "traffic_counts",
                         ~t.duplicated(subset=["detector_id", "date", "hour"])))
    results.append(_rule("valid_date_format", "traffic_counts",
                         t["date"].astype(str).str.match(DATE_RE)))
    hours = pd.to_numeric(t["hour"], errors="coerce")
    results.append(_rule("hour_in_range", "traffic_counts", (hours >= 0) & (hours <= 23)))

    c = pd.read_csv(files["charging"])
    total += len(c)
    results.append(_rule("power_kw_positive", "charging_stations",
                         pd.to_numeric(c["power_kw"], errors="coerce") > 0))
    results.append(_rule("coords_within_bbox", "charging_stations",
                         c.apply(lambda r: _in_box(r["lat"], r["lon"]), axis=1)))
    results.append(_rule("num_points_ge_1", "charging_stations",
                         pd.to_numeric(c["num_points"], errors="coerce") >= 1))

    st = pd.read_csv(files["stops"])
    total += len(st)
    results.append(_rule("stop_coords_within_bbox", "gtfs_stops",
                         st.apply(lambda r: _in_box(r["stop_lat"], r["stop_lon"]), axis=1)))
    results.append(_rule("stop_id_unique", "gtfs_stops", ~st["stop_id"].duplicated()))

    report = {"generated_at": dt.datetime.now().isoformat(timespec="seconds"),
              "total_rows_checked": int(total),
              "all_passed": all(r.failed == 0 for r in results),
              "checks": [r.as_dict() for r in results],
              "engine": "python"}
    return report


def write_report(report: dict, settings: Settings) -> None:
    settings.processed_dir.mkdir(parents=True, exist_ok=True)
    (settings.processed_dir / "data_quality_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


def enforce(report: dict) -> None:
    """Raise if any rule failed - this is what makes the gate a real gate."""
    if not report["all_passed"]:
        failing = [c["name"] for c in report["checks"] if c["failed"]]
        raise DataQualityError(
            f"Data-quality gate failed on {len(failing)} rule(s): {', '.join(failing)}")
