"""Configuration.

Everything that a user might reasonably want to change is an environment
variable with a sane default, resolved once into an immutable ``Settings``
object. Paths are anchored to the repository root so the pipeline behaves
identically from any working directory, on Windows, macOS and Linux.

| Variable | Default | Purpose |
|---|---|---|
| `INGOMOB_SOURCE` | `demo` | `demo` (offline, synthetic) or `live` (real downloads) |
| `INGOMOB_DATA_DIR` | `<repo>/data` | root for raw/processed/warehouse data |
| `INGOMOB_DB_PATH` | `<data>/warehouse/ingomob.duckdb` | DuckDB file |
| `INGOMOB_LOG_LEVEL` | `INFO` | logging verbosity |
| `INGOMOB_SEED` | `42` | RNG seed (demo source, model) |
| `INGOMOB_SIM_DAYS` | `180` | days of demo history |
| `INGOMOB_HTTP_TIMEOUT` | `30` | per-request timeout, seconds |
| `INGOMOB_HTTP_RETRIES` | `3` | retry attempts for live downloads |
| `INGOMOB_CACHE_DIR` | `<data>/cache` | downloaded-file cache |
| `INGOMOB_OUTPUT_DIR` | `<repo>` | root for `dashboard/` and `reports/` outputs |
| `INGOMOB_GITHUB_USER` | `` | used only to render links in docs/report |
"""
from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass
from pathlib import Path

from .errors import ConfigError

PROJECT_ROOT = Path(__file__).resolve().parents[2]

VALID_SOURCES = ("demo", "live")


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc


@dataclass(frozen=True)
class Settings:
    source: str
    data_dir: Path
    db_path: Path
    cache_dir: Path
    output_dir: Path
    seed: int
    sim_days: int
    http_timeout: int
    http_retries: int
    github_user: str

    # --- derived paths -------------------------------------------------
    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def gtfs_dir(self) -> Path:
        return self.raw_dir / "gtfs"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"

    @property
    def warehouse_dir(self) -> Path:
        return self.data_dir / "warehouse"

    @property
    def sql_dir(self) -> Path:
        return PROJECT_ROOT / "sql"

    @property
    def dashboard_dir(self) -> Path:
        return self.output_dir / "dashboard"

    @property
    def reports_dir(self) -> Path:
        return self.output_dir / "reports"

    @property
    def figures_dir(self) -> Path:
        return self.reports_dir / "figures"

    @property
    def java_dir(self) -> Path:
        return PROJECT_ROOT / "java"

    def ensure_dirs(self) -> None:
        for p in (self.raw_dir, self.gtfs_dir, self.processed_dir, self.warehouse_dir,
                  self.cache_dir, self.dashboard_dir, self.reports_dir, self.figures_dir):
            p.mkdir(parents=True, exist_ok=True)


def load_settings() -> Settings:
    """Read settings from the environment. Called fresh so tests can monkeypatch env."""
    source = _env("INGOMOB_SOURCE", "demo").lower()
    if source not in VALID_SOURCES:
        raise ConfigError(f"INGOMOB_SOURCE must be one of {VALID_SOURCES}, got {source!r}")
    data_dir = Path(_env("INGOMOB_DATA_DIR", str(PROJECT_ROOT / "data"))).expanduser()
    db_path = Path(_env("INGOMOB_DB_PATH", str(data_dir / "warehouse" / "ingomob.duckdb")))
    cache_dir = Path(_env("INGOMOB_CACHE_DIR", str(data_dir / "cache")))
    output_dir = Path(_env("INGOMOB_OUTPUT_DIR", str(PROJECT_ROOT))).expanduser()
    sim_days = _env_int("INGOMOB_SIM_DAYS", 180)
    if not 28 <= sim_days <= 1095:
        raise ConfigError(f"INGOMOB_SIM_DAYS must be between 28 and 1095, got {sim_days}")
    return Settings(
        source=source,
        data_dir=data_dir,
        db_path=db_path,
        cache_dir=cache_dir,
        output_dir=output_dir,
        seed=_env_int("INGOMOB_SEED", 42),
        sim_days=sim_days,
        http_timeout=_env_int("INGOMOB_HTTP_TIMEOUT", 30),
        http_retries=_env_int("INGOMOB_HTTP_RETRIES", 3),
        github_user=_env("INGOMOB_GITHUB_USER", ""),
    )


# --------------------------------------------------------------------------- #
# Domain constants (Ingolstadt geography). Not user-tunable.                   #
# --------------------------------------------------------------------------- #
CITY_CENTER = (48.7665, 11.4258)
BBOX = {"min_lat": 48.71, "max_lat": 48.82, "min_lon": 11.35, "max_lon": 11.50}
SIM_START = dt.date(2025, 1, 1)

DISTRICTS = [
    ("Mitte", 48.7630, 11.4255, 1.00),
    ("Nordwest", 48.7810, 11.4020, 0.72),
    ("Nordost", 48.7880, 11.4520, 0.65),
    ("Südwest", 48.7420, 11.3980, 0.70),
    ("Südost", 48.7460, 11.4560, 0.68),
    ("Ringsee", 48.7550, 11.4100, 0.55),
    ("Friedrichshofen", 48.7720, 11.3820, 0.48),
    ("Etting", 48.8010, 11.4360, 0.40),
    ("Unsernherrn", 48.7360, 11.4230, 0.42),
    ("Oberhaunstadt", 48.8020, 11.4600, 0.38),
]

INVG_LINES = [
    ("10", "Hauptbahnhof - Zentrum - Klinikum"),
    ("11", "Friedrichshofen - Zentrum - Nordost"),
    ("15", "Südwest - Rathausplatz - Etting"),
    ("16", "Ringsee - Zentrum - Oberhaunstadt"),
    ("20", "Hauptbahnhof - Audi - Nordwest"),
    ("21", "Unsernherrn - Zentrum - Nordost"),
    ("40", "Südost - Klinikum - Etting"),
    ("44", "Ringsee - Hauptbahnhof - Nordost"),
    ("60", "Friedrichshofen - Audi - Oberhaunstadt"),
]

ROAD_TYPES = {
    "arterial": (1250, 4),
    "ring": (1550, 3),
    "collector": (620, 4),
    "local": (210, 3),
}

BAVARIA_HOLIDAYS = {
    dt.date(2025, 1, 1): "Neujahr",
    dt.date(2025, 1, 6): "Heilige Drei Koenige",
    dt.date(2025, 4, 18): "Karfreitag",
    dt.date(2025, 4, 21): "Ostermontag",
    dt.date(2025, 5, 1): "Tag der Arbeit",
    dt.date(2025, 5, 29): "Christi Himmelfahrt",
    dt.date(2025, 6, 9): "Pfingstmontag",
    dt.date(2025, 6, 19): "Fronleichnam",
}

# Bavarian school holidays in the window (traffic behaves differently).
SCHOOL_HOLIDAYS = [
    (dt.date(2025, 1, 1), dt.date(2025, 1, 6)),
    (dt.date(2025, 3, 3), dt.date(2025, 3, 7)),
    (dt.date(2025, 4, 14), dt.date(2025, 4, 25)),
    (dt.date(2025, 6, 10), dt.date(2025, 6, 20)),
]


def is_school_holiday(d: dt.date) -> bool:
    return any(a <= d <= b for a, b in SCHOOL_HOLIDAYS)


def settings() -> Settings:
    """Convenience accessor - re-reads the environment on every call."""
    return load_settings()


def ensure_dirs() -> None:
    load_settings().ensure_dirs()
