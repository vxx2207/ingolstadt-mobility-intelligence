"""Broken, empty and malformed inputs must produce actionable errors, not tracebacks."""
from __future__ import annotations

import pytest

from ingomob.errors import SchemaError, SourceError
from ingomob.transform import build_warehouse


def test_missing_raw_files(isolated_env):
    with pytest.raises(SourceError) as exc:
        build_warehouse()
    assert "generate" in str(exc.value).lower()


def test_empty_csv_is_rejected(isolated_env, pipeline):
    import shutil
    for f in pipeline.raw_dir.rglob("*"):
        if f.is_file():
            target = isolated_env.raw_dir / f.relative_to(pipeline.raw_dir)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(f, target)
    (isolated_env.raw_dir / "traffic_counts.csv").write_text("")
    with pytest.raises(SourceError) as exc:
        build_warehouse()
    assert "empty" in str(exc.value).lower()


def test_schema_violation_is_rejected(isolated_env, pipeline):
    import shutil
    for f in pipeline.raw_dir.rglob("*"):
        if f.is_file():
            target = isolated_env.raw_dir / f.relative_to(pipeline.raw_dir)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(f, target)
    p = isolated_env.raw_dir / "traffic_counts.csv"
    import pandas as pd
    pd.read_csv(p).drop(columns=["vehicle_count"]).to_csv(p, index=False)
    with pytest.raises(SchemaError):
        build_warehouse()


def test_dashboard_export_refuses_without_forecast(isolated_env, pipeline):
    """A dashboard with empty KPIs is worse than a clear error."""
    import shutil

    from ingomob.errors import NotBuiltError
    from ingomob.export_dashboard import build_dashboard_data
    for f in pipeline.raw_dir.rglob("*"):
        if f.is_file():
            t = isolated_env.raw_dir / f.relative_to(pipeline.raw_dir)
            t.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(f, t)
    from ingomob.transform import build_warehouse
    build_warehouse()
    with pytest.raises(NotBuiltError):
        build_dashboard_data(isolated_env)


def test_plots_give_actionable_error_without_artifacts(isolated_env):
    from ingomob import plots
    from ingomob.errors import NotBuiltError
    with pytest.raises(NotBuiltError) as exc:
        plots.fig_cv_comparison()
    assert "run-all" in str(exc.value) or "forecast" in str(exc.value)
