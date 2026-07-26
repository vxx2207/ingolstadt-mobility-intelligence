"""CLI behaviour, including the exit codes CI relies on."""
from __future__ import annotations

import pandas as pd

from ingomob.cli import main


def test_help_exits_cleanly(capsys):
    try:
        main(["--help"])
    except SystemExit as e:
        assert e.code == 0
    assert "run-all" in capsys.readouterr().out


def test_doctor_reports_environment(capsys, pipeline):
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "source mode" in out and "duckdb" in out


def test_unknown_subcommand_is_rejected():
    try:
        main(["teleport"])
    except SystemExit as e:
        assert e.code != 0


def test_data_quality_failure_returns_exit_code_2(isolated_env, monkeypatch):
    from ingomob.sources.demo import DemoSource
    DemoSource(isolated_env).materialise()
    p = isolated_env.raw_dir / "traffic_counts.csv"
    df = pd.read_csv(p)
    df.loc[df.index[:5], "vehicle_count"] = -1
    df.to_csv(p, index=False)
    assert main(["--python-only", "validate"]) == 2


def test_no_strict_flag_keeps_exit_code_0(isolated_env):
    from ingomob.sources.demo import DemoSource
    DemoSource(isolated_env).materialise()
    p = isolated_env.raw_dir / "traffic_counts.csv"
    df = pd.read_csv(p)
    df.loc[df.index[:5], "vehicle_count"] = -1
    df.to_csv(p, index=False)
    assert main(["--python-only", "--no-strict", "validate"]) == 0


def test_missing_prerequisite_returns_exit_code_1(isolated_env):
    assert main(["warehouse"]) == 1
