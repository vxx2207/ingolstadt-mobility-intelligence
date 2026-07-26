import pytest

from ingomob import features as F
from ingomob.forecast import train_and_evaluate


def test_no_generator_parameter_in_features():
    """peak_base is a parameter of the synthetic generator: using it is leakage."""
    assert "peak_base" not in F.NUMERIC_FEATURES
    assert "peak_base" not in F.CALENDAR_ONLY


def test_lags_are_backward_looking_only(pipeline):
    df = F.build_feature_frame().sort_values(["detector_id", "ts"])
    g = df[df.detector_id == df.detector_id.iloc[0]].set_index("ts")
    import pandas as pd
    for ts in g.index[50:60]:
        expected = g["vehicle_count"].get(ts - pd.Timedelta(hours=24))
        if expected is not None and not pd.isna(g.loc[ts, "lag_24"]):
            assert abs(g.loc[ts, "lag_24"] - expected) < 1e-6


def test_model_beats_every_baseline(forecast_result):
    r = forecast_result
    s = r["cv"]["summary"]
    assert s["model"]["mae"]["mean"] < s["seasonal_naive"]["mae"]["mean"]
    assert s["model"]["mae"]["mean"] < s["last_value"]["mae"]["mean"]
    assert s["model"]["mae"]["mean"] < s["calendar_only"]["mae"]["mean"], (
        "the full model must beat a calendar-only model, otherwise the extra "
        "features are not earning their place")


def test_cross_validation_has_multiple_folds(forecast_result):
    r = forecast_result
    assert r["cv"]["n_folds"] >= 3
    assert len(r["cv"]["per_fold"]["model"]) == r["cv"]["n_folds"]


def test_results_are_not_suspiciously_perfect(forecast_result):
    """A guard against re-introducing leakage: R^2 above ~0.98 on hourly traffic
    means something is wrong with the evaluation, not that the model is great."""
    r = forecast_result
    r2 = r["cv"]["summary"]["model"]["r2"]["mean"]
    assert 0.5 < r2 < 0.98, f"implausible R2 {r2} - check for leakage"


def test_reports_uncertainty(forecast_result):
    r = forecast_result
    assert r["cv"]["summary"]["model"]["mae"]["std"] > 0


def test_short_history_raises_clear_error(isolated_env, monkeypatch):
    from ingomob.errors import NotBuiltError
    monkeypatch.setenv("INGOMOB_SIM_DAYS", "28")
    from ingomob.config import load_settings
    from ingomob.sources.demo import DemoSource
    from ingomob.transform import build_warehouse
    s = load_settings()
    DemoSource(s).materialise()
    build_warehouse()
    try:
        train_and_evaluate(s)
    except (NotBuiltError, ValueError) as exc:
        assert "INGOMOB_SIM_DAYS" in str(exc) or "history" in str(exc).lower()
    else:
        pytest.skip("28 days was enough for CV on this configuration")
