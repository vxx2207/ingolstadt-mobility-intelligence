"""Static matplotlib figures for the README and strategy report.

These are rendered from the same warehouse/artefacts as the interactive
dashboard, so the repository shows real visuals even without a browser.
"""
# ruff: noqa: I001  (matplotlib backend must be set before pyplot import)
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from .config import load_settings  # noqa: E402
from .errors import NotBuiltError  # noqa: E402
from .warehouse import query_df  # noqa: E402

ROAD_COLORS = {"arterial": "#2563eb", "ring": "#7c3aed",
               "collector": "#059669", "local": "#d97706"}
plt.rcParams.update({"figure.dpi": 120, "font.size": 10, "axes.grid": True,
                     "grid.alpha": 0.3, "axes.spines.top": False, "axes.spines.right": False})


def _require(path):
    """Fail with an actionable message instead of a bare FileNotFoundError."""
    if not path.exists():
        raise NotBuiltError(
            f"{path.name} is missing - run 'ingomob forecast' (or 'run-all') before "
            f"rendering figures.")
    return path


def _save(fig, name):
    figures_dir = load_settings().figures_dir
    figures_dir.mkdir(parents=True, exist_ok=True)
    path = figures_dir / name
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def fig_hourly_profile():
    df = query_df("""
        SELECT f.hour, dd.is_weekend, AVG(f.vehicle_count) AS avg_count
        FROM fact_traffic f JOIN dim_date dd ON dd.date_key=f.date_key
        GROUP BY f.hour, dd.is_weekend ORDER BY f.hour
    """)
    fig, ax = plt.subplots(figsize=(9, 4))
    for wk, lbl, col in [(False, "Weekday", "#2563eb"), (True, "Weekend", "#d97706")]:
        d = df[df.is_weekend == wk]
        ax.plot(d.hour, d.avg_count, label=lbl, color=col, lw=2.5)
    ax.set(xlabel="Hour of day", ylabel="Ø vehicles / hour",
           title="Hourly traffic profile — weekday vs. weekend")
    ax.set_xticks(range(0, 24, 2))
    ax.legend()
    return _save(fig, "hourly_profile.png")


def fig_forecast():
    ts = pd.read_csv(_require(load_settings().processed_dir / "forecast_timeseries.csv"),
                     parse_dates=["ts"])
    fig, ax = plt.subplots(figsize=(11, 4))
    ax.plot(ts.ts, ts.baseline, label="Seasonal-naive baseline", color="#ef4444", lw=1, ls=":")
    ax.plot(ts.ts, ts.actual, label="Actual", color="#64748b", lw=1.6)
    ax.plot(ts.ts, ts.predicted, label="Model (gradient boosting)", color="#2563eb", lw=1.6)
    ax.set(xlabel="", ylabel="Citywide vehicles / hour",
           title="Hourly demand forecast — most recent rolling-origin fold")
    ax.legend(loc="upper right", ncol=3, fontsize=9)
    fig.autofmt_xdate()
    return _save(fig, "forecast.png")


def fig_importance():
    imp = pd.read_csv(
        _require(load_settings().processed_dir / "forecast_importance.csv")).head(10).iloc[::-1]
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.barh(imp.feature, imp.importance, color="#7c3aed")
    ax.set(xlabel="Δ MAE when feature is shuffled", title="Permutation feature importance (top 10)")
    return _save(fig, "feature_importance.png")


def fig_headway():
    r = query_df("SELECT route_short_name, avg_peak_headway_min FROM mart_route_service "
                 "ORDER BY avg_peak_headway_min")
    r["route_short_name"] = r["route_short_name"].astype(str)
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar("L" + r.route_short_name, r.avg_peak_headway_min, color="#2563eb")
    ax.set(xlabel="Line", ylabel="Peak headway (min)",
           title="Weekday peak headway by bus line (lower = better)")
    return _save(fig, "headway.png")


def fig_siting_map():
    det = query_df("SELECT lat, lon, road_type, peak_base FROM dim_detector")
    ch = query_df("SELECT lat, lon FROM dim_charging_station")
    import json
    rec = json.loads(
        _require(load_settings().processed_dir / "siting_summary.json").read_text(encoding="utf-8"))["recommendations"]
    rec = pd.DataFrame(rec)
    fig, ax = plt.subplots(figsize=(8, 6.5))
    for rt, col in ROAD_COLORS.items():
        d = det[det.road_type == rt]
        ax.scatter(d.lon, d.lat, s=d.peak_base / 12, c=col, alpha=0.8,
                   edgecolors="white", linewidths=0.5, label=f"Detector · {rt}")
    ax.scatter(ch.lon, ch.lat, s=28, c="#059669", marker="o", alpha=0.7, label="Charging point")
    ax.scatter(rec.lon, rec.lat, s=260, c="#ef4444", marker="*",
               edgecolors="black", linewidths=0.6, label="Recommended site", zorder=5)
    for _, row in rec.iterrows():
        ax.annotate(f"#{int(row['rank'])}", (row.lon, row.lat),
                    textcoords="offset points", xytext=(7, 4), fontsize=9, fontweight="bold")
    ax.set(xlabel="Longitude", ylabel="Latitude",
           title="Mobility network & recommended charging sites — Ingolstadt")
    ax.legend(fontsize=8, loc="upper left")
    return _save(fig, "siting_map.png")


def fig_cv_comparison():
    import json
    m = json.loads(_require(load_settings().processed_dir / "forecast_metrics.json").read_text(encoding="utf-8"))
    summ = m["cv"]["summary"]
    order = [("last_value", "Last value (24h)"), ("seasonal_naive", "Seasonal-naive (168h)"),
             ("calendar_only", "Calendar-only model"), ("model", "Full model")]
    labels = [lbl for _, lbl in order]
    means = [summ[k]["mae"]["mean"] for k, _ in order]
    errs = [summ[k]["mae"]["std"] for k, _ in order]
    colors = ["#94a3b8", "#ef4444", "#d97706", "#2563eb"]
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.barh(labels, means, xerr=errs, color=colors, capsize=4)
    pad = max(means) * 0.035 + max(errs)
    for y, (v, e) in enumerate(zip(means, errs, strict=True)):
        ax.text(v + e + pad * 0.5, y, f"{v:.1f}", va="center", fontsize=9, fontweight="bold")
    ax.set_xlim(0, max(means) + max(errs) + pad * 2.2)
    ax.set(xlabel="MAE (vehicles/hour) — lower is better",
           title=f"Baseline ladder · {m['cv']['n_folds']} rolling-origin folds "
                 f"(±1 std across folds)")
    ax.invert_yaxis()
    return _save(fig, "cv_comparison.png")


def make_all() -> dict:
    return {
        "cv_comparison": str(fig_cv_comparison()),
        "hourly_profile": str(fig_hourly_profile()),
        "forecast": str(fig_forecast()),
        "feature_importance": str(fig_importance()),
        "headway": str(fig_headway()),
        "siting_map": str(fig_siting_map()),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(make_all(), indent=2))
