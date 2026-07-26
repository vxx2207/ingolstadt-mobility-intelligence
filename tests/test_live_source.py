"""Exercise the ``live`` source end-to-end against a local mock HTTP server.

The real endpoints are not contacted: tests must be hermetic and offline. What
*is* tested is everything that actually breaks in practice - HTTP handling,
retries, caching, ZIP extraction, the DWD ``-999`` sentinel, latin-1 encoding,
Overpass tag parsing and nearest-station discovery.
"""
from __future__ import annotations

import http.server
import io
import json
import socketserver
import threading
import zipfile

import pytest

from ingomob.errors import DownloadError
from ingomob.http_client import fetch, provenance
from ingomob.sources.live import LiveSource

STATIONS_TXT = (
    "Stations_id von_datum bis_datum Stationshoehe geoBreite geoLaenge Stationsname Bundesland\n"
    "----------- --------- --------- ------------- --------- --------- --------------- ----------\n"
    "00164 20040101 20260722 447 48.7160 11.2144 Neuburg-Donau Bayern\n"
    "03668 19310101 20260722 314 49.5030 11.0549 Nuernberg Bayern\n"
    "01262 19970101 20260722 515 48.1632 11.5429 Muenchen Bayern\n"
)
TU_PRODUCT = (
    "STATIONS_ID;MESS_DATUM;QN_9;TT_TU;RF_TU;eor\n"
    "164;2025010100;3;5.2;88.0;eor\n"
    "164;2025010101;3;-999;-999;eor\n"
    "164;2025010102;3;4.8;90.0;eor\n"
)
RR_PRODUCT = (
    "STATIONS_ID;MESS_DATUM;QN_8;R1;RS_IND;WRTR;eor\n"
    "164;2025010100;3;0.0;0;0;eor\n"
    "164;2025010101;3;1.4;1;6;eor\n"
    "164;2025010102;3;-999;0;0;eor\n"
)
OVERPASS = {"elements": [
    {"type": "node", "id": 1, "lat": 48.7660, "lon": 11.4250,
     "tags": {"name": "Rathausplatz", "operator": "Stadtwerke", "capacity": "4",
              "charging_station:output": "22 kW"}},
    {"type": "node", "id": 2, "lat": 48.7700, "lon": 11.4300, "tags": {"amenity": "charging_station"}},
]}


GTFS_FILES = {
    "stops.txt": "stop_id,stop_name,stop_lat,stop_lon\nS1,Rathausplatz,48.7660,11.4250\n",
    "routes.txt": "route_id,route_short_name,route_long_name,route_type\nR10,10,HBF - Klinikum,3\n",
    "trips.txt": "route_id,service_id,trip_id\nR10,weekday,T1\n",
    "stop_times.txt": "trip_id,stop_id,stop_sequence,arrival_time,departure_time\n"
                      "T1,S1,1,07:00:00,07:00:30\n",
}


def _gtfs_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, body in GTFS_FILES.items():
            z.writestr(name, body)
    return buf.getvalue()


def _zip_bytes(inner_name: str, text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(inner_name, text.encode("latin-1"))
    return buf.getvalue()


class _Handler(http.server.BaseHTTPRequestHandler):
    hits: dict = {}

    def log_message(self, *a):  # silence
        pass

    def do_GET(self):  # noqa: N802
        path = self.path.split("?")[0]
        _Handler.hits[path] = _Handler.hits.get(path, 0) + 1
        if path.endswith("Beschreibung_Stationen.txt"):
            body, ctype = STATIONS_TXT.encode("latin-1"), "text/plain"
        elif "stundenwerte_TU_" in path:
            body, ctype = _zip_bytes("produkt_tu_stunde_x.txt", TU_PRODUCT), "application/zip"
        elif "stundenwerte_RR_" in path:
            body, ctype = _zip_bytes("produkt_rr_stunde_x.txt", RR_PRODUCT), "application/zip"
        elif path.startswith("/gtfs"):
            body, ctype = _gtfs_zip(), "application/zip"
        elif path.startswith("/overpass"):
            body, ctype = json.dumps(OVERPASS).encode(), "application/json"
        elif path.startswith("/flaky"):
            n = _Handler.hits[path]
            if n < 3:
                self.send_error(503, "temporarily unavailable")
                return
            body, ctype = b"recovered", "text/plain"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture(scope="module")
def server():
    _Handler.hits = {}
    with socketserver.TCPServer(("127.0.0.1", 0), _Handler) as httpd:
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
        httpd.shutdown()


def _live(server, isolated_env, monkeypatch):
    monkeypatch.setenv("INGOMOB_DWD_STATIONS_URL",
                       f"{server}/TU_Stundenwerte_Beschreibung_Stationen.txt")
    monkeypatch.setenv("INGOMOB_DWD_BASE", server)
    monkeypatch.setenv("INGOMOB_OVERPASS_URL", f"{server}/overpass")
    monkeypatch.setenv("INGOMOB_GTFS_URL", f"{server}/gtfs.zip")
    return LiveSource(isolated_env)


def test_downloads_and_parses_real_dwd_layout(server, isolated_env, monkeypatch):
    df = _live(server, isolated_env, monkeypatch).weather()
    assert len(df) == 3
    # -999 sentinel must not become a temperature of minus 999
    assert df["temp_c"].min() > -50
    # missing precipitation is filled, not propagated as NaN
    assert df["precip_mm"].isna().sum() == 0
    assert set(["date", "hour", "temp_c", "precip_mm"]).issubset(df.columns)


def test_nearest_station_is_chosen_not_the_first(server, isolated_env, monkeypatch):
    src = _live(server, isolated_env, monkeypatch)
    stations = src.parse_station_list(STATIONS_TXT)
    best = src.nearest_station(stations)
    assert best["station_id"] == "00164"      # Neuburg is closest to Ingolstadt


def test_overpass_tags_parsed_with_sane_defaults(server, isolated_env, monkeypatch):
    df = _live(server, isolated_env, monkeypatch).charging()
    assert len(df) == 2
    row = df[df.station_id == "OSM1"].iloc[0]
    assert row.num_points == 4 and row.power_kw == 22 and row.operator == "Stadtwerke"
    fallback = df[df.station_id == "OSM2"].iloc[0]
    assert fallback.num_points == 1 and fallback.operator == "unknown"
    assert set(df["district"]) <= {d[0] for d in __import__("ingomob.config",
                                                            fromlist=["x"]).DISTRICTS}


def test_http_cache_avoids_a_second_request(server, isolated_env, monkeypatch):
    url = f"{server}/TU_Stundenwerte_Beschreibung_Stationen.txt"
    before = _Handler.hits.get("/TU_Stundenwerte_Beschreibung_Stationen.txt", 0)
    fetch(url, isolated_env.cache_dir, suffix=".txt")
    fetch(url, isolated_env.cache_dir, suffix=".txt")
    after = _Handler.hits["/TU_Stundenwerte_Beschreibung_Stationen.txt"]
    assert after - before == 1, "second call should have been served from cache"


def test_retries_then_succeeds(server, isolated_env):
    path = fetch(f"{server}/flaky", isolated_env.cache_dir, retries=4, suffix=".txt")
    assert path.read_bytes() == b"recovered"


def test_gives_up_with_actionable_error(isolated_env):
    with pytest.raises(DownloadError) as exc:
        fetch("http://127.0.0.1:1/nope", isolated_env.cache_dir, timeout=1, retries=1)
    assert "--source demo" in str(exc.value)


def test_provenance_records_checksums(server, isolated_env):
    fetch(f"{server}/overpass?data=x", isolated_env.cache_dir, suffix=".json")
    recs = provenance(isolated_env.cache_dir)
    assert recs and all({"url", "sha256", "bytes", "fetched_at"} <= set(r) for r in recs)


def test_gtfs_zip_is_extracted(server, isolated_env, monkeypatch):
    tables = _live(server, isolated_env, monkeypatch).gtfs()
    assert set(tables) >= {"stops.txt", "routes.txt", "trips.txt", "stop_times.txt"}
    assert tables["stops.txt"].iloc[0]["stop_name"] == "Rathausplatz"


def test_gtfs_missing_file_is_reported(server, isolated_env, monkeypatch):
    """A truncated archive must fail loudly, not silently produce empty marts."""
    from ingomob.errors import SourceError
    src = _live(server, isolated_env, monkeypatch)
    import zipfile as zf
    broken = isolated_env.cache_dir / "broken.zip"
    broken.parent.mkdir(parents=True, exist_ok=True)
    with zf.ZipFile(broken, "w") as z:
        z.writestr("stops.txt", GTFS_FILES["stops.txt"])
    monkeypatch.setattr(src, "_fetch", lambda url, suffix: broken)
    with pytest.raises(SourceError) as exc:
        src.gtfs()
    assert "missing" in str(exc.value).lower()


def test_live_mode_states_the_traffic_limitation(server, isolated_env, monkeypatch):
    monkeypatch.delenv("INGOMOB_TRAFFIC_CSV", raising=False)
    from ingomob.errors import SourceError
    with pytest.raises(SourceError) as exc:
        _live(server, isolated_env, monkeypatch).materialise()
    assert "INGOMOB_TRAFFIC_CSV" in str(exc.value)
