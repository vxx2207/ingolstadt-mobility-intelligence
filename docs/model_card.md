# Model card — hourly traffic demand forecast

## Purpose
Predict the number of vehicles passing a loop detector in the next hour, to support
short-horizon operational planning (signal timing, parking guidance, staffing).

## Data
| Item | Value |
|---|---|
| Unit of observation | detector × date × hour |
| Target | `vehicle_count` |
| Features | `hour_sin`, `hour_cos`, `dow`, `month`, `is_weekend`, `is_holiday`, `is_school_holiday`, `temp_c`, `precip_mm`, `lag_24`, `lag_168`, `roll_mean_24`, `roll_std_24`, one-hot `road_type` and `detector_id` |
| Explicitly excluded | `peak_base` — a parameter of the demo generator; using it would let the model observe the data-generating process |
| Algorithm | `HistGradientBoostingRegressor` (scikit-learn), early stopping on an internal 15 % split |

## Evaluation protocol
* **Rolling-origin cross-validation**, expanding window, 4 folds, 14-day test horizons.
  Training data always precedes the test block; no shuffling.
* Metrics reported as **mean ± standard deviation across folds**, never a single split.
* **Baseline ladder** — a model must be compared against the strongest cheap alternative,
  not the weakest:

| Predictor | What it does |
|---|---|
| Last value | copy the count 24 h earlier |
| Seasonal-naive | copy the count 168 h earlier (same hour, previous week) |
| Calendar + weather model | same algorithm, no lag features — the honest benchmark |
| Full model | calendar + weather + lags |

The headline number is the improvement over the **calendar-only** model. Quoting only the
seasonal-naive comparison overstates the contribution of the machine learning.

## Known limitations and biases
1. **Synthetic target in `demo` mode.** Metrics measure recovery of a known stochastic
   process, not real-world forecast skill. Treat them as a demonstration of method.
2. **Detector-specific.** `detector_id` is a feature, so the model cannot score a new
   detector without retraining.
3. **Short horizon only.** Validated at a 1-hour horizon with observed lags available.
   Multi-step-ahead forecasting would require recursive prediction and would degrade.
4. **Weather is observed, not forecast.** In production the model would consume *forecast*
   weather, which carries its own error and would widen intervals.
5. **No incident or event feed.** Road closures, football matches and construction are not
   modelled; the demo generator injects incidents that the model cannot anticipate,
   which is the main irreducible error.
6. **No uncertainty intervals.** Point predictions only. Quantile regression would be the
   next step for operational use.
7. **Sensor faults are learned as real zeros.** Stuck-at-zero periods are not flagged
   before training, so the model partially learns the fault pattern.

## Ethical / operational notes
Aggregate vehicle counts contain no personal data. Predictions should not be used to
justify enforcement actions against individuals, and any deployment should re-validate
on live data before use.

## Revision history
* **v2** — removed `peak_base`, added rolling-origin CV, added the calendar-only baseline
  and this card. The v1 result (R² 0.98) was an artefact of an over-clean synthetic
  generator: a calendar-only model reached the same score, proving the benchmark was
  uninformative. The generator now includes autocorrelated residuals, level drift,
  incidents, sensor faults and missing hours.
