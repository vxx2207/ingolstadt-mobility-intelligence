"""Feature engineering for the hourly traffic-demand forecast.

Deliberately excluded features
------------------------------
``peak_base`` was dropped in v2. It is a *parameter of the demo generator*
(the amplitude used to synthesise the target), so including it lets the model
peek at the data-generating process. It is also redundant with the detector
identity the model already sees. Removing it costs ~1% MAE and removes a
legitimate leakage objection.

Lag features are strictly backwards-looking and computed per detector after
sorting by time, so no future information can enter a training row.
"""
from __future__ import annotations

import pandas as pd

from .errors import NotBuiltError
from .warehouse import query_df, table_exists

BASE_QUERY = """
SELECT f.date, f.hour, det.detector_id, det.road_type,
       dd.dow, dd.month, dd.is_weekend, dd.is_holiday, dd.is_school_holiday,
       f.temp_c, f.precip_mm, f.vehicle_count
FROM fact_traffic f
JOIN dim_date dd      ON dd.date_key = f.date_key
JOIN dim_detector det ON det.detector_key = f.detector_key
"""

NUMERIC_FEATURES = [
    "hour_sin", "hour_cos", "dow", "month", "is_weekend", "is_holiday", "is_school_holiday",
    "temp_c", "precip_mm", "lag_24", "lag_168", "roll_mean_24", "roll_std_24",
]
CATEGORICAL_FEATURES = ["road_type", "detector_id"]
TARGET = "vehicle_count"

CALENDAR_ONLY = ["hour_sin", "hour_cos", "dow", "month", "is_weekend", "is_holiday",
                 "is_school_holiday", "temp_c", "precip_mm"]


def build_feature_frame() -> pd.DataFrame:
    if not table_exists("fact_traffic"):
        raise NotBuiltError("fact_traffic is missing. Run 'ingomob warehouse' first.")
    df = query_df(BASE_QUERY)
    if df.empty:
        raise NotBuiltError("fact_traffic is empty - nothing to model.")

    df["ts"] = pd.to_datetime(df["date"].astype(str)) + pd.to_timedelta(df["hour"], unit="h")
    df = df.sort_values(["detector_id", "ts"]).reset_index(drop=True)

    # Cyclical encoding: hour 23 and hour 0 are adjacent, not 23 apart.
    import numpy as np
    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)

    # Lags are computed on the *time index*, so gaps in the series do not
    # silently shift a "24h ago" lag onto the wrong timestamp.
    frames = []
    for _det, grp in df.groupby("detector_id", sort=False):
        g = grp.set_index("ts").sort_index()
        target = g[TARGET]
        g["lag_24"] = target.reindex(g.index - pd.Timedelta(hours=24)).to_numpy()
        g["lag_168"] = target.reindex(g.index - pd.Timedelta(hours=168)).to_numpy()
        roll = target.shift(1).rolling("24h", min_periods=6)
        g["roll_mean_24"] = roll.mean()
        g["roll_std_24"] = roll.std()
        frames.append(g.reset_index())
    df = pd.concat(frames, ignore_index=True)

    for col in ("is_weekend", "is_holiday", "is_school_holiday"):
        df[col] = df[col].astype(int)

    before = len(df)
    df = df.dropna(subset=["lag_24", "lag_168", "roll_mean_24", "roll_std_24"])
    df = df.sort_values("ts").reset_index(drop=True)
    if df.empty:
        raise NotBuiltError(
            f"No rows survived lag construction (started with {before}). "
            "The history is too short - increase INGOMOB_SIM_DAYS.")
    return df


def design_matrix(df: pd.DataFrame, feature_set: list[str] | None = None):
    feats = feature_set if feature_set is not None else NUMERIC_FEATURES
    X = pd.get_dummies(df[feats + CATEGORICAL_FEATURES],
                       columns=CATEGORICAL_FEATURES, prefix=CATEGORICAL_FEATURES)
    return X, list(X.columns)
