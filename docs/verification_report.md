# Verification report — IngoMobility v2

Second review pass, conducted at senior-data-engineer / recruiter level.
Everything below was executed from a **freshly extracted archive**, not from the working copy.

---

## 1. Weaknesses found in v1 (and what was done about each)

| # | Weakness | Severity | Evidence | Fix |
|---|---|---|---|---|
| 1 | **R² 0.98 was a meaningless benchmark.** The synthetic generator was nearly noiseless: a *calendar-only* model scored R² 0.984 — better than the full model (0.980). The headline number measured formula recovery, not modelling skill. | Critical | Ablation run: calendar-only MAE 28.69 vs full model 33.20 | Generator rebuilt with AR(1) residuals, mean-reverting per-detector level drift, multi-week roadworks shifts, incident spikes, stuck-at-zero sensor faults and missing hours. Honest result: **R² 0.84**, model beats calendar-only by 8.6 % in all 4 folds. |
| 2 | **Generator parameter used as a feature.** `peak_base` — the amplitude used to synthesise the target — was in the feature set. | High (leakage optics) | Removing it changed MAE 33.20 → 33.50, i.e. it was redundant *and* indefensible | Removed from `NUMERIC_FEATURES`; documented in the model card; test `test_no_generator_parameter_in_features` prevents its return. |
| 3 | **Single hold-out, single weak baseline.** One 30-day split against seasonal-naive only — the classic way to flatter a model. | High | — | **Rolling-origin CV**, 4 expanding folds × 14-day horizons, metrics as mean ± std, plus a **four-rung baseline ladder** (last-value → seasonal-naive → calendar-only → full model). Headline is now the gain over calendar-only, not over the weakest baseline. |
| 4 | **The data-quality gate never actually gated.** `run_validation` returned a report; nothing aborted the pipeline, and only the happy path was tested. | High | v1 had zero tests exercising a failing rule | `quality.enforce()` raises `DataQualityError`; CLI exits **2**; parametrised tests prove *each* rule catches its own defect (negative counts, bad dates, out-of-range hours, duplicates, out-of-bbox coordinates). |
| 5 | **SQL splitter silently corrupted statements.** It stripped everything after `--` on any line, including inside string literals. | High (silent data corruption) | `SELECT 'a--b'` was truncated to `SELECT 'a` | Quote- and comment-aware `split_sql()`; regression test `test_double_dash_inside_literal_survives`. |
| 6 | **No logging, no error handling.** Bare `print()`; missing files surfaced as raw `FileNotFoundError` tracebacks. | Medium | Reproduced live during this pass: `plots.py` crashed with `FileNotFoundError` | Typed exception hierarchy with actionable hints, structured logging via `INGOMOB_LOG_LEVEL`, `ingomob doctor`, distinct exit codes (0/1/2/130). |
| 7 | **Only one setting was configurable** (`INGOMOB_DB_PATH`), and it existed only as a workaround. | Medium | — | Validated `Settings` dataclass; 11 documented environment variables; invalid values rejected at load with a clear message. |
| 8 | **Tests wrote into the repository's committed artefacts.** Running `pytest` silently overwrote `dashboard/data.json` and `reports/` with short-horizon test data. | Medium | Caught in this pass: committed `data.json` showed MAE 95.54 (test config) instead of 99.33 | `INGOMOB_OUTPUT_DIR` added; tests redirect all outputs to a temp dir; verified by md5 before/after a test run. |
| 9 | **Unpinned dependencies** (`>=` with no upper bound) — "reproducible" was not actually reproducible. | Medium | — | Upper bounds in `requirements.txt`/`pyproject.toml` plus a `constraints.txt` with exact verified versions. |
| 10 | **Fabricated/assumed GitHub handle** in badges and Pages URL; a CI badge that would render broken for anyone else. | Medium (credibility) | `vxx2207` hard-coded in README | All badges removed; single `YOUR_GITHUB_USER` placeholder plus `scripts/set_repo_links.py`. Zero hard-coded handles remain (verified by grep). |
| 11 | **Headway metric was an approximation labelled as a measurement.** `240 / peak_departures` assumed a 4-hour peak window. | Medium | — | True mean gap between consecutive first-stop departures inside the peak windows, via a window function; method note surfaced in the report and dashboard. |
| 12 | **Untyped warehouse columns.** `fact_traffic.date` was `VARCHAR`; the weather join compared strings. | Low–medium | — | Explicit `CAST(... AS DATE/INTEGER/DOUBLE)`; test asserts the column type is `DATE`. |
| 13 | **Two DQ engines, duplicated rules, no parity check.** Java and Python could drift apart silently. | Medium | — | Shared `RULE_NAMES` spec; `test_rule_names_match_java_implementation` fails the build on drift. Java gained the missing `hour_in_range` rule (9 rules both sides). |
| 14 | **Lag features could silently misalign.** Lags were computed with `.shift(24)` on row position, which is wrong whenever hours are missing. | Medium | The v2 generator introduces real gaps, so this became a live bug | Lags now computed on the **time index** (`reindex(index - 24h)`); test verifies alignment against ground truth. |
| 15 | **Dashboard was a chart dump.** No filters, no loading/error/empty states, no explanation of any KPI, no source or freshness indication. | Medium | — | Rebuilt: Overview tab answering the three business questions in prose, district/road/day-type filters, hover explanations for every KPI from a `glossary` block, provenance chips (source mode, period, generated-at, DQ status), loading/error/empty states with recovery instructions, responsive layout, skip link. |
| 16 | **No failure-mode tests at all.** 13 happy-path tests. | Medium | — | **70 tests**, including corrupted/empty/missing inputs, every DQ rule's failure path, CLI exit codes, config validation, engine parity, byte-level determinism, and a **mock HTTP server** exercising the live download path. |
| 17 | **"Cross-platform" was claimed but only tested on Ubuntu**; `make` and a bash script were on the critical path. | Medium | — | CI matrix Ubuntu × Windows × macOS on Python 3.10/3.12; `make` demoted to optional; `ingomob serve` replaces `serve.sh`. |
| 18 | **Siting model presented as optimisation.** It is a normalised difference of two kernels — an ordinal score. | Low–medium | — | Relabelled a heuristic; `method` and `caveats` emitted in the JSON, rendered in the dashboard and report; test asserts caveats exist. |
| 19 | **Stale/dead files shipped:** `generate_data.py` superseded by `sources/demo.py`, empty `scripts/`, unused `jinja2` dependency, unused `package-data` config. | Low | — | All removed; orphan-module scan confirms every module is referenced. |
| 20 | **Version drift.** `pyproject.toml` said 2.0.0 while `__init__.py` said 1.0.0. | Low | Caught during clean-install check | Synchronised; `test_package_version_matches_pyproject` guards it. |

**Not fixed by design:** the duplication between the Java and Python DQ engines remains (it is the point of the polyglot demonstration) — mitigated by the parity test, and disclosed in `docs/limitations.md`.

---

## 2. Real-data integration

The brief asked for at least one official dataset fully integrated, or clearly separated modes.

**What was built:** a real `live` source mode with production-grade downloaders and parsers for
three official, keyless endpoints:

| Domain | Provider | Handled specifics |
|---|---|---|
| Hourly weather | **DWD Open Data (CDC)** | Nearest station **discovered at runtime** by parsing the station description and computing haversine distance to Ingolstadt; ZIP extraction; latin-1; `;`-delimited fixed schema; `-999` missing sentinel; precipitation merged from a second product with graceful fallback |
| Public transport | **VGI / INVG GTFS** | ZIP archive, required-file validation, per-file schema contracts |
| EV charging | **OpenStreetMap / Overpass API** | JSON tag parsing with sane fallbacks (`capacity`, `charging_station:output`), nearest-district assignment |

Plus a real HTTP layer: retries with exponential backoff, explicit timeouts, on-disk cache keyed
by URL hash, SHA-256 provenance records, and `DownloadError` messages that tell the user what to do.

**Honest status — this is the main remaining limitation.** The build environment had **no outbound
network** (verified: `Tunnel connection failed: 403`), so the production endpoints were never
contacted from here. The live path is instead verified against a **local mock HTTP server that
replays the exact real file formats** (11 tests: DWD sentinel handling, ZIP extraction, station
discovery, Overpass tags, cache behaviour, retry-then-succeed, give-up error, GTFS extraction,
truncated-archive detection). The parsers are proven; the endpoints are not. A manual
`live-smoke` CI workflow exists to confirm them on a networked machine.

**Second honest gap:** the City of Ingolstadt does not publish an open **hourly loop-detector
feed**. Live mode therefore raises an explicit, actionable error for that one domain unless
`INGOMOB_TRAFFIC_CSV` is supplied. This is stated in the README, `DATA_SOURCES.md` and
`docs/limitations.md` rather than glossed over.

---

## 3. Clean-room verification results

All executed from `ingolstadt-mobility-intelligence-v2.zip`, freshly extracted, environment reset.

| Check | Result |
|---|---|
| **Clean install** (`pip install -e .`) | Pass — `ingomob 2.0.0`, console entry point works |
| **CLI** | `--help`, `doctor`, all 10 subcommands resolve; `doctor` reports paths, source mode, dependency versions, JDK availability |
| **Pipeline** (7 stages) | Pass — 60,221 traffic rows → 9 DQ rules on 60,320 rows → 25 warehouse objects → 8 siting candidates → 4-fold CV → 182,317-byte payload + 6 figures → report |
| **Determinism** | Pass — two independent clean runs produced identical MAE 99.33; byte-level hash test included. A re-run on Windows 11 / Python 3.12 with the same seed gives MAE 98.39 +/- 6.55 and a 9.4 % lift - identical conclusions. Determinism therefore holds within a platform; the small cross-platform difference comes from BLAS and threading inside scikit-learn |
| **Tests** | **70/70 pass** (run in blocks due to a 45 s sandbox limit) |
| **Lint** | `ruff check src tests scripts` — clean |
| **Dashboard** | JS syntax validated with `node --check`; every `DATA.*` path resolved against the real `data.json`; all element IDs referenced by JS exist; contract test enforces this in CI |
| **Artefact isolation** | Committed `dashboard/data.json` unchanged (MAE 99.33) after a full test run |
| **Orphan scan** | No unreferenced modules, no `YOUR_GITHUB_USER` leftovers outside the documented placeholder, no hard-coded handle |

### Model results (measured on Linux / Python 3.10 - see the cross-platform note below)

| Predictor | MAE (mean ± std, 4 folds) | R² |
|---|---|---|
| Last value (t−24 h) | 181.14 ± 9.93 | 0.47 |
| Seasonal-naive (t−168 h) | 161.35 ± 7.13 | 0.57 |
| Calendar + weather model | 108.69 ± 5.25 | 0.81 |
| **Full model** | **99.33 ± 7.75** | **0.84** |

The full model wins in **every** fold. Reported lift: **8.6 % over calendar-only** (38.4 % over
seasonal-naive, which is the flattering comparison and is labelled as such).

---

## 4. Remaining honest limitations

1. **The default data is synthetic.** Statistically realistic and schema-accurate, but no figure
   from `demo` mode describes the real Ingolstadt.
2. **Live endpoints unverified from this environment** (no network). Parsers tested against real
   formats via a mock server; run `live-smoke` to confirm the endpoints.
3. **Live mode covers 3 of 4 domains** — no open hourly traffic feed exists for Ingolstadt.
4. **Metrics on synthetic data measure process recovery**, not real-world forecast skill.
5. **One-hour horizon, point predictions only** — no prediction intervals, no multi-step forecasting.
6. **Siting is an ordinal screening heuristic** — ignores grid capacity, land, parking turnover, cost.
7. **Scheduled GTFS only** — no GTFS-Realtime, so punctuality cannot be measured.
8. **Sensor faults are learned as real zeros** — not flagged before training.
9. **DQ rule logic is duplicated** across Java and Python; parity is enforced by name, not semantics.
10. **Batch, single-machine** — no orchestration, incremental loads or CDC.

---

## 5. One action required before publishing

```bash
python scripts/set_repo_links.py <your-github-username>
```

This is the only place a personal identifier appears; nothing else is hard-coded.
