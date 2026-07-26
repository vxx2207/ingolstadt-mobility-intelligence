import pytest

from ingomob.config import load_settings
from ingomob.errors import ConfigError


def test_defaults():
    s = load_settings()
    assert s.source in ("demo", "live")
    assert s.seed == 42


def test_rejects_unknown_source(monkeypatch):
    monkeypatch.setenv("INGOMOB_SOURCE", "wishful")
    with pytest.raises(ConfigError):
        load_settings()


def test_rejects_non_integer_seed(monkeypatch):
    monkeypatch.setenv("INGOMOB_SEED", "not-a-number")
    with pytest.raises(ConfigError):
        load_settings()


def test_rejects_absurd_sim_days(monkeypatch):
    monkeypatch.setenv("INGOMOB_SIM_DAYS", "3")
    with pytest.raises(ConfigError):
        load_settings()


def test_source_switch_is_respected(monkeypatch):
    monkeypatch.setenv("INGOMOB_SOURCE", "live")
    assert load_settings().source == "live"


def test_package_version_matches_pyproject():
    """A drifting version string is a small thing that signals carelessness."""
    import re

    import ingomob
    from ingomob.config import PROJECT_ROOT
    declared = re.search(r'^version = "([^"]+)"',
                         (PROJECT_ROOT / "pyproject.toml").read_text(), re.M).group(1)
    assert ingomob.__version__ == declared


def test_outputs_are_redirectable(monkeypatch, tmp_path):
    """Running the pipeline must never clobber the repo's committed artefacts."""
    monkeypatch.setenv("INGOMOB_OUTPUT_DIR", str(tmp_path))
    s = load_settings()
    assert s.dashboard_dir == tmp_path / "dashboard"
    assert s.reports_dir == tmp_path / "reports"
    assert s.figures_dir == tmp_path / "reports" / "figures"
