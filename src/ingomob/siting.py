"""Charging-station siting optimisation.

Scores a spatial grid over Ingolstadt by *unmet demand* = mobility demand
(traffic volume + transit activity) minus existing charging supply, using
distance-decayed kernels. A greedy, spacing-aware selector then recommends new
sites so recommendations don't cluster on a single hotspot.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from . import config as C
from .config import Settings, load_settings
from .errors import NotBuiltError
from .logging_conf import get_logger
from .warehouse import query_df, table_exists

log = get_logger(__name__)

LAT_KM = 111.0
LON_KM = 111.0 * np.cos(np.radians(C.CITY_CENTER[0]))


def _km(lat1, lon1, lat2, lon2):
    return np.sqrt(((lat1 - lat2) * LAT_KM) ** 2 + ((lon1 - lon2) * LON_KM) ** 2)


def _kernel(dist_km, sigma):
    return np.exp(-((dist_km / sigma) ** 2))


def _grid(n):
    lats = np.linspace(C.BBOX["min_lat"], C.BBOX["max_lat"], n)
    lons = np.linspace(C.BBOX["min_lon"], C.BBOX["max_lon"], n)
    gl, go = np.meshgrid(lats, lons)
    return pd.DataFrame({"lat": gl.ravel(), "lon": go.ravel()})


def recommend(n_recommend=8, grid_n=18, sigma_km=1.3,
              transit_weight=0.35, min_spacing_km=1.2,
              settings: Settings | None = None) -> dict:
    """Rank candidate charging locations by unmet demand.

    This is an explicit **heuristic**, not a validated optimiser: demand and
    supply are min-max normalised before subtraction, so ``gap_score`` is an
    ordinal ranking signal, not a physical quantity. Real siting also needs grid
    capacity, land availability, parking turnover and cost - none of which are
    in the open data. Stated plainly rather than dressed up as optimisation.
    """
    s = settings or load_settings()
    if not table_exists("fact_traffic"):
        raise NotBuiltError("Warehouse not built. Run 'ingomob warehouse' first.")
    det = query_df("""
        SELECT d.lat, d.lon, AVG(daily) AS w FROM (
            SELECT detector_key, date, SUM(vehicle_count) AS daily
            FROM fact_traffic GROUP BY detector_key, date) q
        JOIN dim_detector d ON d.detector_key = q.detector_key
        GROUP BY d.lat, d.lon
    """)
    stops = query_df("SELECT lat, lon, departures_weekday AS w FROM mart_stop_service "
                     "WHERE departures_weekday > 0")
    charging = query_df("SELECT lat, lon, num_points AS w FROM dim_charging_station")

    grid = _grid(grid_n)

    def field(src, sigma):
        if src.empty:
            return np.zeros(len(grid))
        d = _km(grid["lat"].values[:, None], grid["lon"].values[:, None],
                src["lat"].values[None, :], src["lon"].values[None, :])
        return (_kernel(d, sigma) * src["w"].values[None, :]).sum(axis=1)

    traffic_demand = field(det, sigma_km)
    transit_demand = field(stops, sigma_km)
    supply = field(charging, sigma_km * 0.9)

    def norm(x):
        rng = x.max() - x.min()
        return (x - x.min()) / rng if rng > 0 else np.zeros_like(x)

    demand = norm(traffic_demand) + transit_weight * norm(transit_demand)
    demand = norm(demand)
    supply_n = norm(supply)
    gap = np.clip(demand - supply_n, 0, None)

    grid = grid.assign(demand=demand.round(3), supply=supply_n.round(3),
                       gap_score=gap.round(3))

    # Greedy spacing-aware selection
    picks = []
    cand = grid.sort_values("gap_score", ascending=False).reset_index(drop=True)
    chosen = []
    for _, row in cand.iterrows():
        if row["gap_score"] <= 0:
            break
        if all(_km(row["lat"], row["lon"], c[0], c[1]) >= min_spacing_km for c in chosen):
            chosen.append((row["lat"], row["lon"]))
            picks.append(row)
        if len(picks) >= n_recommend:
            break

    recs = pd.DataFrame(picks).reset_index(drop=True)
    recs.insert(0, "rank", recs.index + 1)
    recs["lat"] = recs["lat"].round(6)
    recs["lon"] = recs["lon"].round(6)

    # Assign nearest district for readability
    dist = query_df("SELECT district, lat, lon FROM dim_district")
    nearest = []
    for _, r in recs.iterrows():
        dd = _km(r["lat"], r["lon"], dist["lat"].values, dist["lon"].values)
        nearest.append(dist.iloc[int(dd.argmin())]["district"])
    recs["nearest_district"] = nearest

    s.processed_dir.mkdir(parents=True, exist_ok=True)
    recs.to_csv(s.processed_dir / "siting_recommendations.csv", index=False)
    grid.to_csv(s.processed_dir / "siting_grid.csv", index=False)
    out = {
        "method": "heuristic gap score (normalised demand minus normalised supply)",
        "caveats": ["gap_score is ordinal, not a physical unit",
                    "grid capacity, land availability and cost are not modelled",
                    "OSM/demo charging inventory may be incomplete"],
        "n_recommendations": int(len(recs)),
        "grid_cells": int(len(grid)),
        "params": {"grid_n": grid_n, "sigma_km": sigma_km,
                   "transit_weight": transit_weight, "min_spacing_km": min_spacing_km},
        "recommendations": recs[["rank", "lat", "lon", "gap_score",
                                 "demand", "supply", "nearest_district"]].to_dict("records"),
    }
    (s.processed_dir / "siting_summary.json").write_text(json.dumps(out, indent=2, default=str))
    log.info("siting: %d recommendations over %d grid cells", len(recs), len(grid))
    return out


if __name__ == "__main__":
    print(json.dumps(recommend(), indent=2))
