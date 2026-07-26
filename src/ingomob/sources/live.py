"""Real (``live``) source: downloads official open data and normalises it to the
same contracts the ``demo`` source emits.

Endpoints (all public, keyless, documented):

| Domain | Provider | Endpoint |
|---|---|---|
| Hourly weather | Deutscher Wetterdienst, CDC | ``opendata.dwd.de/.../climate/hourly/air_temperature/recent/`` |
| Public transport | VGI / INVG GTFS static | ``INGOMOB_GTFS_URL`` (see docs) |
| Charging stations | OpenStreetMap via Overpass API | ``INGOMOB_OVERPASS_URL`` |

Design notes
------------
* The DWD station is **discovered at runtime**: the station description file is
  parsed and the station closest to Ingolstadt is selected, rather than
  hard-coding an ID that may be decommissioned.
* DWD files use ``;``-separated fixed columns, an ``eor`` terminator and
  ``-999`` as the missing-value sentinel - all handled explicitly.
* Traffic loop-detector counts are **not** published as an open feed by the City
  of Ingolstadt at the time of writing. ``live`` mode therefore raises a clear
  error for that domain unless ``INGOMOB_TRAFFIC_CSV`` points at a local export.
  This limitation is stated up front rather than papered over.
"""
from __future__ import annotations

import io
import math
import os
import zipfile

import pandas as pd

from .. import config as C
from ..config import Settings
from ..errors import DownloadError, SourceError
from ..http_client import fetch
from ..logging_conf import get_logger
from ..schemas import CHARGING_STATIONS, GTFS_STOPS, WEATHER

log = get_logger(__name__)

DWD_BASE = ("https://opendata.dwd.de/climate_environment/CDC/observations_germany/"
            "climate/hourly")
DWD_STATIONS_URL = f"{DWD_BASE}/air_temperature/recent/TU_Stundenwerte_Beschreibung_Stationen.txt"
DEFAULT_OVERPASS = "https://overpass-api.de/api/interpreter"
DEFAULT_GTFS_URL = "https://www.vgi.de/fileadmin/user_upload/VGI/Downloads/GTFS/vgi_gtfs.zip"

MISSING_SENTINEL = -999


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class LiveSource:
    """Downloads and normalises real open data."""

    name = "live"

    def __init__(self, settings: Settings):
        self.s = settings
        self.overpass_url = os.environ.get("INGOMOB_OVERPASS_URL", DEFAULT_OVERPASS)
        self.gtfs_url = os.environ.get("INGOMOB_GTFS_URL", DEFAULT_GTFS_URL)
        self.dwd_stations_url = os.environ.get("INGOMOB_DWD_STATIONS_URL", DWD_STATIONS_URL)
        self.dwd_base = os.environ.get("INGOMOB_DWD_BASE", DWD_BASE)

    def _fetch(self, url, suffix):
        return fetch(url, self.s.cache_dir, timeout=self.s.http_timeout,
                     retries=self.s.http_retries, suffix=suffix)

    # -- DWD weather -----------------------------------------------------
    @staticmethod
    def parse_station_list(text: str) -> pd.DataFrame:
        """Parse the DWD station description (fixed-width, latin-1, 2 header lines)."""
        rows = []
        for line in text.splitlines()[2:]:
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) < 7:
                continue
            try:
                rows.append({"station_id": parts[0],
                             "height_m": int(parts[3]),
                             "lat": float(parts[4]),
                             "lon": float(parts[5]),
                             "name": " ".join(parts[6:-1]) or parts[6]})
            except (ValueError, IndexError):
                continue
        if not rows:
            raise SourceError("DWD station list could not be parsed (unexpected layout).")
        return pd.DataFrame(rows)

    def nearest_station(self, stations: pd.DataFrame) -> dict:
        lat0, lon0 = C.CITY_CENTER
        stations = stations.assign(
            dist_km=[_haversine_km(lat0, lon0, r.lat, r.lon) for r in stations.itertuples()]
        ).sort_values("dist_km")
        best = stations.iloc[0]
        log.info("nearest DWD station: %s (%s) - %.1f km from Ingolstadt",
                 best["name"], best["station_id"], best["dist_km"])
        return best.to_dict()

    @staticmethod
    def parse_dwd_product(text: str, value_col: str, out_col: str) -> pd.DataFrame:
        """Parse a DWD ``produkt_*.txt`` payload into (date, hour, <out_col>)."""
        df = pd.read_csv(io.StringIO(text), sep=";", skipinitialspace=True)
        df.columns = [c.strip().upper() for c in df.columns]
        if value_col not in df.columns:
            raise SourceError(f"DWD product missing column {value_col}; got {list(df.columns)}")
        df = df[["MESS_DATUM", value_col]].copy()
        df["MESS_DATUM"] = df["MESS_DATUM"].astype(str).str.strip()
        ts = pd.to_datetime(df["MESS_DATUM"], format="%Y%m%d%H", errors="coerce")
        df = df.assign(date=ts.dt.date.astype(str), hour=ts.dt.hour)
        df[out_col] = pd.to_numeric(df[value_col], errors="coerce")
        df.loc[df[out_col] <= MISSING_SENTINEL, out_col] = pd.NA  # explicit sentinel handling
        return df.dropna(subset=["hour"])[["date", "hour", out_col]]

    @staticmethod
    def _product_from_zip(path) -> str:
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if n.lower().startswith("produkt")]
            if not names:
                raise SourceError(f"No produkt_*.txt inside {path.name}")
            return z.read(names[0]).decode("latin-1")

    def weather(self) -> pd.DataFrame:
        stations_path = self._fetch(self.dwd_stations_url, ".txt")
        stations = self.parse_station_list(stations_path.read_bytes().decode("latin-1"))
        st = self.nearest_station(stations)
        sid = str(st["station_id"]).zfill(5)

        tu = self._fetch(f"{self.dwd_base}/air_temperature/recent/stundenwerte_TU_{sid}_akt.zip",
                         ".zip")
        temp = self.parse_dwd_product(self._product_from_zip(tu), "TT_TU", "temp_c")
        try:
            rr = self._fetch(
                f"{self.dwd_base}/precipitation/recent/stundenwerte_RR_{sid}_akt.zip", ".zip")
            precip = self.parse_dwd_product(self._product_from_zip(rr), "R1", "precip_mm")
            df = temp.merge(precip, on=["date", "hour"], how="left")
        except (DownloadError, SourceError) as exc:
            log.warning("precipitation unavailable for station %s (%s); defaulting to 0", sid, exc)
            df = temp.assign(precip_mm=0.0)

        df["precip_mm"] = df["precip_mm"].fillna(0.0)
        df["temp_c"] = df["temp_c"].astype(float).interpolate(limit=3)
        df = df.dropna(subset=["temp_c"])
        df["hour"] = df["hour"].astype(int)
        df["is_holiday"] = [int(pd.Timestamp(d).date() in C.BAVARIA_HOLIDAYS) for d in df["date"]]
        WEATHER.validate(df, "DWD hourly")
        log.info("DWD weather: %s hourly rows (%s -> %s)", f"{len(df):,}",
                 df["date"].min(), df["date"].max())
        return df

    # -- Overpass charging ----------------------------------------------
    @staticmethod
    def parse_overpass(payload: dict) -> pd.DataFrame:
        elements = payload.get("elements", [])
        rows = []
        for i, el in enumerate(elements, start=1):
            tags = el.get("tags", {})
            lat = el.get("lat") or (el.get("center") or {}).get("lat")
            lon = el.get("lon") or (el.get("center") or {}).get("lon")
            if lat is None or lon is None:
                continue
            try:
                pts = int(str(tags.get("capacity", "1")).split(";")[0])
            except ValueError:
                pts = 1
            kw_raw = str(tags.get("charging_station:output")
                         or tags.get("socket:type2:output") or "22").replace("kW", "").strip()
            try:
                kw = int(float(kw_raw.split(";")[0]))
            except ValueError:
                kw = 22
            rows.append({"station_id": f"OSM{el.get('id', i)}",
                         "name": tags.get("name") or f"Charging point {i}",
                         "operator": tags.get("operator") or "unknown",
                         "lat": round(float(lat), 6), "lon": round(float(lon), 6),
                         "num_points": max(1, pts), "power_kw": max(1, kw),
                         "install_year": 0})
        if not rows:
            raise SourceError("Overpass returned no charging stations for the query area.")
        return pd.DataFrame(rows)

    def charging(self) -> pd.DataFrame:
        query = ('[out:json][timeout:60];node(around:9000,'
                 f'{C.CITY_CENTER[0]},{C.CITY_CENTER[1]})[amenity=charging_station];out center;')
        import json
        import urllib.parse
        url = f"{self.overpass_url}?data={urllib.parse.quote(query)}"
        path = self._fetch(url, ".json")
        df = self.parse_overpass(json.loads(path.read_text(encoding="utf-8")))
        df["district"] = [self._nearest_district(r.lat, r.lon) for r in df.itertuples()]
        CHARGING_STATIONS.validate(df, "Overpass")
        log.info("Overpass: %d charging stations around Ingolstadt", len(df))
        return df

    @staticmethod
    def _nearest_district(lat, lon) -> str:
        return min(C.DISTRICTS, key=lambda d: _haversine_km(lat, lon, d[1], d[2]))[0]

    # -- GTFS ------------------------------------------------------------
    def gtfs(self) -> dict[str, pd.DataFrame]:
        path = self._fetch(self.gtfs_url, ".zip")
        out = {}
        with zipfile.ZipFile(path) as z:
            available = set(z.namelist())
            for fname in ("stops.txt", "routes.txt", "trips.txt", "stop_times.txt",
                          "agency.txt", "calendar.txt"):
                if fname not in available:
                    if fname in ("agency.txt", "calendar.txt"):
                        continue
                    raise SourceError(f"GTFS archive is missing {fname}; got {sorted(available)}")
                out[fname] = pd.read_csv(io.BytesIO(z.read(fname)))
        GTFS_STOPS.validate(out["stops.txt"], "GTFS stops.txt")
        log.info("GTFS: %d stops, %d routes, %d trips", len(out["stops.txt"]),
                 len(out["routes.txt"]), len(out["trips.txt"]))
        return out

    # -- entrypoint ------------------------------------------------------
    def materialise(self) -> dict:
        s = self.s
        s.ensure_dirs()
        weather = self.weather()
        charging = self.charging()
        gtfs = self.gtfs()

        traffic_csv = os.environ.get("INGOMOB_TRAFFIC_CSV")
        if not traffic_csv:
            raise SourceError(
                "Live mode fetched weather, charging and GTFS successfully, but the City of "
                "Ingolstadt does not publish an open hourly loop-detector feed. Set "
                "INGOMOB_TRAFFIC_CSV=/path/to/counts.csv (columns: detector_id,date,hour,"
                "vehicle_count) to complete the live pipeline, or use --source demo."
            )
        traffic = pd.read_csv(traffic_csv)

        for name, df in (("stops.txt", gtfs["stops.txt"]), ("routes.txt", gtfs["routes.txt"]),
                         ("trips.txt", gtfs["trips.txt"]),
                         ("stop_times.txt", gtfs["stop_times.txt"])):
            df.to_csv(s.gtfs_dir / name, index=False)
        weather.to_csv(s.raw_dir / "weather.csv", index=False)
        charging.to_csv(s.raw_dir / "charging_stations.csv", index=False)
        traffic.to_csv(s.raw_dir / "traffic_counts.csv", index=False)
        return {"source": "live", "weather_rows": len(weather),
                "charging_stations": len(charging), "stops": len(gtfs["stops.txt"]),
                "traffic_rows": len(traffic)}
