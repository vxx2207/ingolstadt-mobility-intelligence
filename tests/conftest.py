"""Test fixtures.

Every test runs against an isolated data directory in ``tmp_path`` so the suite
never touches (or depends on) a developer's working copy.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

_SESSION_DIR = Path(tempfile.mkdtemp(prefix="ingomob-tests-"))


def _point_env_at(directory: Path) -> None:
    os.environ["INGOMOB_DATA_DIR"] = str(directory)
    os.environ["INGOMOB_DB_PATH"] = str(directory / "warehouse" / "ingomob.duckdb")
    os.environ["INGOMOB_CACHE_DIR"] = str(directory / "cache")
    # Never write into the repository's committed dashboard/ and reports/ artefacts.
    os.environ["INGOMOB_OUTPUT_DIR"] = str(directory / "out")
    os.environ["INGOMOB_SOURCE"] = "demo"
    os.environ["INGOMOB_LOG_LEVEL"] = "WARNING"
    # Shorter history keeps the suite fast; still long enough for 4 CV folds.
    os.environ["INGOMOB_SIM_DAYS"] = "120"


_point_env_at(_SESSION_DIR)


@pytest.fixture(scope="session", autouse=True)
def _cleanup():
    yield
    shutil.rmtree(_SESSION_DIR, ignore_errors=True)


@pytest.fixture(scope="session")
def pipeline():
    """Build raw data + warehouse once for the whole session."""
    from ingomob.config import load_settings
    from ingomob.java_validate import run_validation
    from ingomob.sources.demo import DemoSource
    from ingomob.transform import build_warehouse
    s = load_settings()
    DemoSource(s).materialise()
    run_validation(prefer_java=False, settings=s)
    build_warehouse()
    return s


@pytest.fixture(scope="session")
def forecast_result(pipeline):
    """Train once per session - model fitting dominates the suite runtime."""
    from ingomob.forecast import train_and_evaluate
    return train_and_evaluate(pipeline)


@pytest.fixture(scope="session")
def analytics_ready(pipeline):
    from ingomob import siting, transit_quality
    transit_quality.summarize(pipeline)
    siting.recommend(settings=pipeline)
    return pipeline


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    """A throwaway data dir for tests that deliberately corrupt inputs."""
    monkeypatch.setenv("INGOMOB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("INGOMOB_DB_PATH", str(tmp_path / "warehouse" / "t.duckdb"))
    monkeypatch.setenv("INGOMOB_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("INGOMOB_OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.setenv("INGOMOB_SIM_DAYS", "40")   # corruption tests need no long history
    from ingomob.config import load_settings
    s = load_settings()
    s.ensure_dirs()
    yield s
    _point_env_at(_SESSION_DIR)
