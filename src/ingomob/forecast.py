"""Hourly traffic-demand forecasting - evaluated honestly.

Methodology
-----------
* **Rolling-origin cross-validation** (expanding window, 4 folds, 14-day test
  horizons). A single hold-out can be lucky; folds expose variance.
* **A ladder of baselines**, not one: last-observation, seasonal-naive
  (same hour last week), and a calendar-only model. Reporting only the weakest
  baseline is the most common way portfolio projects flatter themselves.
* **No target leakage**: features are strictly backwards-looking, generator
  parameters are excluded, and the scaler/encoder is fit per fold on train only.
* Metrics are reported as mean +/- std across folds, plus a final hold-out.

Interpretation caveat (also in docs/model_card.md): on the ``demo`` source the
target is synthetic, so absolute accuracy measures how well the model recovers a
known stochastic process - not real-world forecast skill.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from . import features as F
from .config import Settings, load_settings
from .logging_conf import get_logger

log = get_logger(__name__)

N_FOLDS = 4
TEST_HORIZON_DAYS = 14


def _metrics(y, p) -> dict:
    y = np.asarray(y, float)
    p = np.asarray(p, float)
    ok = ~(np.isnan(y) | np.isnan(p))
    y, p = y[ok], p[ok]
    if len(y) == 0:
        return {"mae": None, "rmse": None, "r2": None, "smape_pct": None, "n": 0}
    denom = (np.abs(y) + np.abs(p)) / 2
    m = denom > 0
    smape = float(np.mean(np.abs(y[m] - p[m]) / denom[m]) * 100) if m.any() else None
    return {"mae": round(float(mean_absolute_error(y, p)), 2),
            "rmse": round(float(np.sqrt(mean_squared_error(y, p))), 2),
            "r2": round(float(r2_score(y, p)), 4),
            "smape_pct": round(smape, 2) if smape is not None else None,
            "n": int(len(y))}


def _model(seed: int) -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        max_iter=400, learning_rate=0.06, max_leaf_nodes=63,
        l2_regularization=0.1, early_stopping=True, validation_fraction=0.15,
        random_state=seed)


def _fit_predict(df, train_idx, test_idx, feature_set, seed):
    X, names = F.design_matrix(df, feature_set)
    m = _model(seed)
    m.fit(X.loc[train_idx], df.loc[train_idx, F.TARGET])
    pred = np.clip(m.predict(X.loc[test_idx]), 0, None)
    return m, pred, X, names


def _folds(df: pd.DataFrame) -> list[tuple[pd.Index, pd.Index, pd.Timestamp]]:
    """Expanding-window folds; each test block is TEST_HORIZON_DAYS long."""
    end = df["ts"].max().normalize()
    out = []
    for k in range(N_FOLDS, 0, -1):
        test_start = end - np.timedelta64(TEST_HORIZON_DAYS * k - 1, "D")
        test_end = test_start + np.timedelta64(TEST_HORIZON_DAYS, "D")
        tr = df.index[df["ts"] < test_start]
        te = df.index[(df["ts"] >= test_start) & (df["ts"] < test_end)]
        if len(tr) > 500 and len(te) > 100:
            out.append((tr, te, test_start))
    return out


def train_and_evaluate(settings: Settings | None = None) -> dict:
    s = settings or load_settings()
    df = F.build_feature_frame()
    folds = _folds(df)
    if not folds:
        raise ValueError("Not enough history for rolling-origin CV; increase INGOMOB_SIM_DAYS.")
    log.info("rolling-origin CV: %d folds x %d-day horizon", len(folds), TEST_HORIZON_DAYS)

    cv = {"model": [], "seasonal_naive": [], "last_value": [], "calendar_only": []}
    for i, (tr, te, start) in enumerate(folds, 1):
        y = df.loc[te, F.TARGET].to_numpy()
        _, pred, _, _ = _fit_predict(df, tr, te, F.NUMERIC_FEATURES, s.seed)
        _, cal, _, _ = _fit_predict(df, tr, te, F.CALENDAR_ONLY, s.seed)
        cv["model"].append(_metrics(y, pred))
        cv["calendar_only"].append(_metrics(y, cal))
        cv["seasonal_naive"].append(_metrics(y, df.loc[te, "lag_168"].to_numpy()))
        cv["last_value"].append(_metrics(y, df.loc[te, "lag_24"].to_numpy()))
        log.info("  fold %d (from %s): model MAE %.2f | seasonal-naive %.2f | calendar-only %.2f",
                 i, start.date(), cv["model"][-1]["mae"], cv["seasonal_naive"][-1]["mae"],
                 cv["calendar_only"][-1]["mae"])

    def agg(key, metric):
        vals = [f[metric] for f in cv[key] if f[metric] is not None]
        return {"mean": round(float(np.mean(vals)), 2), "std": round(float(np.std(vals)), 2)}

    summary = {k: {m: agg(k, m) for m in ("mae", "rmse", "r2")} for k in cv}

    # Final hold-out = most recent fold, used for the plotted time series.
    tr, te, start = folds[-1]
    y = df.loc[te, F.TARGET].to_numpy()
    model, pred, X, names = _fit_predict(df, tr, te, F.NUMERIC_FEATURES, s.seed)
    holdout = {"model": _metrics(y, pred),
               "seasonal_naive": _metrics(y, df.loc[te, "lag_168"].to_numpy()),
               "last_value": _metrics(y, df.loc[te, "lag_24"].to_numpy())}

    rng = np.random.default_rng(s.seed)
    sample = rng.choice(len(te), size=min(3000, len(te)), replace=False)
    perm = permutation_importance(model, X.loc[te].iloc[sample], y[sample], n_repeats=5,
                                  random_state=s.seed, scoring="neg_mean_absolute_error")
    importance = (pd.DataFrame({"feature": names, "importance": perm.importances_mean})
                  .sort_values("importance", ascending=False).head(12))

    ts = df.loc[te, ["ts"]].copy()
    ts["actual"] = y
    ts["predicted"] = pred
    ts["baseline"] = df.loc[te, "lag_168"].to_numpy()
    city = ts.groupby("ts", as_index=False).sum(numeric_only=True).sort_values("ts")

    base_mae = holdout["seasonal_naive"]["mae"]
    improvement = round((base_mae - holdout["model"]["mae"]) / base_mae * 100, 1)
    lift_over_calendar = round(
        (summary["calendar_only"]["mae"]["mean"] - summary["model"]["mae"]["mean"])
        / summary["calendar_only"]["mae"]["mean"] * 100, 1)

    results = {
        "source": s.source,
        "cv": {"n_folds": len(folds), "horizon_days": TEST_HORIZON_DAYS, "summary": summary,
               "per_fold": cv},
        "holdout": {"test_start": str(start.date()),
                    "test_end": str(df.loc[te, "ts"].max().date()),
                    "n_train": int(len(tr)), "n_test": int(len(te)), **holdout},
        "mae_improvement_pct": improvement,
        "lift_over_calendar_only_pct": lift_over_calendar,
        "features_used": F.NUMERIC_FEATURES + F.CATEGORICAL_FEATURES,
        "features_excluded": ["peak_base (generator parameter - leakage risk)"],
        "top_features": importance.to_dict(orient="records"),
        # kept for the dashboard's flat KPI reads
        "model": holdout["model"], "baseline": holdout["seasonal_naive"],
        "n_train": int(len(tr)), "n_test": int(len(te)),
        "test_start": str(start.date()), "test_end": str(df.loc[te, "ts"].max().date()),
    }
    s.processed_dir.mkdir(parents=True, exist_ok=True)
    (s.processed_dir / "forecast_metrics.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    city.to_csv(s.processed_dir / "forecast_timeseries.csv", index=False)
    importance.to_csv(s.processed_dir / "forecast_importance.csv", index=False)
    log.info("CV MAE %.2f +/- %.2f | seasonal-naive %.2f | calendar-only %.2f (lift %.1f%%)",
             summary["model"]["mae"]["mean"], summary["model"]["mae"]["std"],
             summary["seasonal_naive"]["mae"]["mean"],
             summary["calendar_only"]["mae"]["mean"], lift_over_calendar)
    return results
