"""Synthetic ``demo`` source.

Generates hourly traffic, weather, GTFS and charging data for Ingolstadt that
is *statistically realistic*, not merely a clean formula:

* a per-detector **local level that drifts** as a mean-reverting random walk,
  plus multi-week level shifts (roadworks, land-use change) - this is what makes
  lagged features genuinely informative, exactly as in real detector series
* AR(1)-autocorrelated residuals (real traffic errors are not independent)
* heavy-tailed multiplicative noise
* incident spikes and congestion dips
* sensor faults: stuck-at-zero runs and missing hours
* school holidays, weather elasticity and a slow seasonal trend

The extra stochasticity is deliberate. An earlier revision used near-noiseless
data, which let a calendar-only model reach R^2 = 0.98 - a benchmark so easy it
told you nothing about modelling skill. See docs/model_card.md.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from .. import config as C
from ..config import Settings
from ..logging_conf import get_logger

log = get_logger(__name__)

WEEKDAY_DIURNAL = np.array([
    0.05, 0.03, 0.02, 0.02, 0.05, 0.15, 0.45, 0.85, 1.00, 0.75, 0.60, 0.62,
    0.65, 0.63, 0.66, 0.80, 0.95, 1.00, 0.85, 0.60, 0.45, 0.30, 0.18, 0.10,
])
WEEKEND_DIURNAL = np.array([
    0.10, 0.07, 0.05, 0.03, 0.03, 0.06, 0.12, 0.20, 0.35, 0.55, 0.70, 0.80,
    0.85, 0.85, 0.82, 0.80, 0.78, 0.72, 0.65, 0.55, 0.45, 0.38, 0.28, 0.18,
])

# Stochastic process parameters (documented in the model card).
AR1_PHI = 0.62          # within-day residual autocorrelation
AR1_SIGMA = 0.20        # innovation scale of log-residual
LEVEL_SIGMA = 0.045     # daily random-walk of a detector's local level
LEVEL_REVERT = 0.02     # weak mean-reversion of that level
ROADWORKS_RATE = 0.004  # P(a multi-week level shift starts on a given day)
INCIDENT_RATE = 0.0018  # P(incident starts in a given detector-hour)
FAULT_RATE = 0.0006     # P(sensor fault starts)
MISSING_RATE = 0.004    # P(hour is not reported at all)


class DemoSource:
    """Deterministic synthetic source (seeded)."""

    name = "demo"

    def __init__(self, settings: Settings):
        self.s = settings

    # -- helpers ---------------------------------------------------------
    def _rng(self) -> np.random.Generator:
        return np.random.default_rng(self.s.seed)

    @staticmethod
    def _jitter(rng, lat, lon, scale=0.006):
        return lat + rng.normal(0, scale), lon + rng.normal(0, scale)

    @staticmethod
    def _hhmmss(minutes: float) -> str:
        total = int(round(minutes * 60))
        return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"

    # -- GTFS ------------------------------------------------------------
    def _stops(self, rng) -> pd.DataFrame:
        rows, sid = [], 1
        for name, lat, lon, _w in C.DISTRICTS:
            for k in range(int(rng.integers(4, 7))):
                slat, slon = self._jitter(rng, lat, lon, 0.004)
                rows.append({"stop_id": f"S{sid:03d}",
                             "stop_name": f"{name} {['Zentrum','Nord','Sued','Ost','West','Platz'][k % 6]}",
                             "stop_lat": round(float(slat), 6), "stop_lon": round(float(slon), 6),
                             "district": name})
                sid += 1
        return pd.DataFrame(rows)

    @staticmethod
    def _departures(service: str, factor: float) -> list[str]:
        start, end = {"weekday": (5.0, 23.5), "saturday": (6.0, 23.0)}.get(service, (7.0, 22.5))
        times, t = [], start
        while t <= end:
            h = int(t)
            if service == "weekday":
                base = 12 if (7 <= h < 9 or 16 <= h < 18) else (20 if 9 <= h < 19 else 30)
            elif service == "saturday":
                base = 30 if 9 <= h < 20 else 45
            else:
                base = 40 if 9 <= h < 20 else 60
            times.append(f"{int(t):02d}:{int(round((t - int(t)) * 60)):02d}:00")
            t += max(4, int(round(base * factor))) / 60.0
        return times

    def _gtfs(self, rng, stops):
        agency = pd.DataFrame([{"agency_id": "VGI",
                                "agency_name": "Verkehrsverbund Grossraum Ingolstadt",
                                "agency_url": "https://www.vgi.de",
                                "agency_timezone": "Europe/Berlin"}])
        calendar = pd.DataFrame([
            {"service_id": "weekday", "monday": 1, "tuesday": 1, "wednesday": 1, "thursday": 1,
             "friday": 1, "saturday": 0, "sunday": 0, "start_date": "20250101", "end_date": "20250629"},
            {"service_id": "saturday", "monday": 0, "tuesday": 0, "wednesday": 0, "thursday": 0,
             "friday": 0, "saturday": 1, "sunday": 0, "start_date": "20250101", "end_date": "20250629"},
            {"service_id": "sunday", "monday": 0, "tuesday": 0, "wednesday": 0, "thursday": 0,
             "friday": 0, "saturday": 0, "sunday": 1, "start_date": "20250101", "end_date": "20250629"},
        ])
        routes, trips, stop_times = [], [], []
        stop_ids = stops["stop_id"].tolist()
        factors = [0.8, 1.4, 1.0, 1.25, 0.85, 1.15, 1.3, 0.95, 1.1]
        n = 0
        for idx, (short, long) in enumerate(C.INVG_LINES):
            rid = f"R{short}"
            routes.append({"route_id": rid, "agency_id": "VGI", "route_short_name": short,
                           "route_long_name": long, "route_type": 3})
            picked = list(rng.choice(stop_ids, size=int(rng.integers(8, 13)), replace=False))
            path = (stops.set_index("stop_id").loc[picked].reset_index()
                    .sort_values("stop_lon")["stop_id"].tolist())
            seg = rng.integers(2, 4, size=len(path) - 1)
            for service in ("weekday", "saturday", "sunday"):
                for dep in self._departures(service, factors[idx % len(factors)]):
                    n += 1
                    tid = f"T{n:05d}"
                    trips.append({"route_id": rid, "service_id": service, "trip_id": tid,
                                  "trip_headsign": long.split(" - ")[-1]})
                    h, m, _ = map(int, dep.split(":"))
                    cur = h * 60 + m
                    for i, sid in enumerate(path):
                        stop_times.append({"trip_id": tid, "stop_id": sid, "stop_sequence": i + 1,
                                           "arrival_time": self._hhmmss(cur),
                                           "departure_time": self._hhmmss(cur + 0.5)})
                        if i < len(path) - 1:
                            cur += 0.5 + float(seg[i])
        return (agency, calendar, pd.DataFrame(routes), pd.DataFrame(trips),
                pd.DataFrame(stop_times))

    # -- other domains ---------------------------------------------------
    def _charging(self, rng) -> pd.DataFrame:
        ops = ["Stadtwerke Ingolstadt", "IFG Parken", "EnBW", "Audi Charging"]
        rows, cid = [], 1
        for name, lat, lon, weight in C.DISTRICTS:
            for _ in range(2 + int(rng.poisson(4.0 * weight))):
                slat, slon = self._jitter(rng, lat, lon, 0.005)
                rows.append({"station_id": f"CS{cid:03d}", "name": f"Ladepunkt {name} {cid}",
                             "operator": str(rng.choice(ops)), "lat": round(float(slat), 6),
                             "lon": round(float(slon), 6), "num_points": int(rng.integers(1, 5)),
                             "power_kw": int(rng.choice([11, 22, 50, 150], p=[.45, .30, .18, .07])),
                             "install_year": int(rng.integers(2017, 2026)), "district": name})
                cid += 1
        return pd.DataFrame(rows)

    def _detectors(self, rng) -> pd.DataFrame:
        rows, did = [], 1
        for road_type, (peak, n) in C.ROAD_TYPES.items():
            for _ in range(n):
                d = C.DISTRICTS[rng.integers(0, len(C.DISTRICTS))]
                dlat, dlon = self._jitter(rng, d[1], d[2], 0.006)
                rows.append({"detector_id": f"D{did:03d}", "name": f"{d[0]} {road_type} #{did}",
                             "lat": round(float(dlat), 6), "lon": round(float(dlon), 6),
                             "road_type": road_type, "district": d[0],
                             "peak_base": int(peak * rng.uniform(0.8, 1.2))})
                did += 1
        return pd.DataFrame(rows)

    def _weather(self, rng) -> pd.DataFrame:
        rows = []
        for d in range(self.s.sim_days):
            date = C.SIM_START + dt.timedelta(days=d)
            doy = date.timetuple().tm_yday
            base = 2 + 12 * np.sin((doy - 20) / 365 * 2 * np.pi)
            wet_day = rng.random() < 0.28
            for h in range(24):
                temp = base + 4 * np.sin((h - 15) / 24 * 2 * np.pi) + rng.normal(0, 1.2)
                precip = float(rng.exponential(1.6)) if (wet_day and rng.random() < 0.5) else 0.0
                rows.append({"date": date.isoformat(), "hour": h, "temp_c": round(float(temp), 1),
                             "precip_mm": round(precip, 2), "is_holiday": int(date in C.BAVARIA_HOLIDAYS)})
        return pd.DataFrame(rows)

    def _traffic(self, rng, detectors, weather) -> pd.DataFrame:
        """Hourly counts with AR(1) residuals, incidents, sensor faults and gaps."""
        wx = weather.set_index(["date", "hour"])
        dates = [C.SIM_START + dt.timedelta(days=d) for d in range(self.s.sim_days)]
        records = []
        for det in detectors.itertuples():
            resid = 0.0                # AR(1) state in log space
            level = 0.0                # slow-moving local level (log space)
            roadworks_left = 0         # days remaining of a level shift
            roadworks_effect = 0.0
            incident_left = 0          # hours remaining of a congestion event
            fault_left = 0             # hours remaining of a stuck sensor
            for day_idx, date in enumerate(dates):
                dow = date.weekday()
                holiday = date in C.BAVARIA_HOLIDAYS
                school_hol = C.is_school_holiday(date)
                if dow <= 4 and not holiday:
                    diurnal, dow_f = WEEKDAY_DIURNAL, 1.0
                elif dow == 5:
                    diurnal, dow_f = WEEKEND_DIURNAL, 0.80
                else:
                    diurnal, dow_f = WEEKEND_DIURNAL, 0.62
                # slow local level: mean-reverting random walk, updated daily
                level = (1 - LEVEL_REVERT) * level + rng.normal(0, LEVEL_SIGMA)
                if roadworks_left == 0 and rng.random() < ROADWORKS_RATE:
                    roadworks_left = int(rng.integers(7, 22))
                    roadworks_effect = float(rng.uniform(-0.45, -0.18))
                if roadworks_left > 0:
                    roadworks_left -= 1
                else:
                    roadworks_effect = 0.0
                season = 0.92 + 0.13 * (day_idx / self.s.sim_days)
                hol_f = 0.55 if holiday else (0.88 if school_hol else 1.0)
                for h in range(24):
                    w = wx.loc[(date.isoformat(), h)]
                    weather_f = 1.0
                    if w["precip_mm"] > 5:
                        weather_f *= 0.88
                    elif w["precip_mm"] > 2:
                        weather_f *= 0.94
                    if w["temp_c"] < 0:
                        weather_f *= 0.96

                    # AR(1) residual: today's error depends on the previous hour
                    resid = AR1_PHI * resid + rng.normal(0, AR1_SIGMA)
                    # occasional heavy tail
                    if rng.random() < 0.01:
                        resid += rng.normal(0, 0.5)

                    if incident_left == 0 and rng.random() < INCIDENT_RATE:
                        incident_left = int(rng.integers(1, 5))
                    incident_f = 1.0
                    if incident_left > 0:
                        incident_f = float(rng.uniform(0.35, 0.65))
                        incident_left -= 1

                    mean = (det.peak_base * diurnal[h] * dow_f * season * hol_f
                            * weather_f * incident_f)
                    count = max(0, int(round(mean * np.exp(resid + level + roadworks_effect))))

                    if fault_left == 0 and rng.random() < FAULT_RATE:
                        fault_left = int(rng.integers(2, 10))
                    if fault_left > 0:
                        count = 0        # stuck-at-zero sensor
                        fault_left -= 1

                    if rng.random() < MISSING_RATE:
                        continue          # hour simply not reported

                    records.append({"detector_id": det.detector_id, "date": date.isoformat(),
                                    "hour": h, "ts": f"{date.isoformat()}T{h:02d}:00:00",
                                    "vehicle_count": count})
        return pd.DataFrame(records)

    # -- entrypoint ------------------------------------------------------
    def materialise(self) -> dict:
        s = self.s
        s.ensure_dirs()
        rng = self._rng()
        stops = self._stops(rng)
        agency, calendar, routes, trips, stop_times = self._gtfs(rng, stops)
        charging = self._charging(rng)
        detectors = self._detectors(rng)
        weather = self._weather(rng)
        traffic = self._traffic(rng, detectors, weather)

        stops.drop(columns=["district"]).to_csv(s.gtfs_dir / "stops.txt", index=False)
        agency.to_csv(s.gtfs_dir / "agency.txt", index=False)
        calendar.to_csv(s.gtfs_dir / "calendar.txt", index=False)
        routes.to_csv(s.gtfs_dir / "routes.txt", index=False)
        trips.to_csv(s.gtfs_dir / "trips.txt", index=False)
        stop_times.to_csv(s.gtfs_dir / "stop_times.txt", index=False)
        stops[["stop_id", "district"]].to_csv(s.raw_dir / "stop_districts.csv", index=False)
        charging.to_csv(s.raw_dir / "charging_stations.csv", index=False)
        detectors.to_csv(s.raw_dir / "traffic_detectors.csv", index=False)
        weather.to_csv(s.raw_dir / "weather.csv", index=False)
        traffic.to_csv(s.raw_dir / "traffic_counts.csv", index=False)

        expected = len(detectors) * s.sim_days * 24
        manifest = {"source": "demo", "stops": len(stops), "routes": len(routes),
                    "trips": len(trips), "stop_times": len(stop_times),
                    "charging_stations": len(charging), "detectors": len(detectors),
                    "weather_rows": len(weather), "traffic_rows": len(traffic),
                    "traffic_rows_expected": expected,
                    "missing_pct": round((1 - len(traffic) / expected) * 100, 2)}
        log.info("demo source: %s traffic rows (%.2f%% missing by design)",
                 f"{len(traffic):,}", manifest["missing_pct"])
        return manifest
