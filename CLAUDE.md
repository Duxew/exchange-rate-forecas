# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A pipeline that forecasts TRY exchange rates for every actively-published TCMB currency and exposes the result through a Streamlit pricing tool (CNG400 internship project):

1. `main.py` — pulls buying-rate history for all currencies in `forecasting.CURRENCY_SERIES` from the TCMB (Central Bank of Turkey) EVDS API and writes one `data/raw/<code>_try_data.csv` per currency (e.g. `usd_try_data.csv`, `eur_try_data.csv`, ...). Fetches all currencies together in a single `get_data([...])` call per date-range chunk (4 calls total) rather than one call per currency — EVDS accepts a list of series codes.
2. `forecasting.py` — shared training/evaluation/forecasting functions (Prophet + an ARIMA baseline), plus the canonical `CURRENCY_SERIES` (code → EVDS series id) and `CURRENCY_NAMES` (code → Turkish display name) dicts and `data_path`/`forecast_path`/`metrics_path`/`model_comparison_path` helpers. Imported by `main.py`, `forecast.py`, `compare_models.py`, and `app.py` — this is the single source of truth for "which currencies exist" and "what files they live in".
3. `forecast.py` — for each currency: backtests Prophet (at 3 different `changepoint_range` values) **and** ARIMA on the last 30 rows via `forecasting.select_best_model`, picks whichever of the 4 candidates has the lowest MAPE (MAE/RMSE/MAPE → `data/metrics/metrics_<code>.json`, includes which model/config won and the runner-up's MAPE), then retrains with the winning config and saves a forward forecast (`data/forecasts/forecast_<code>.csv`, columns `ds`/`yhat`/`yhat_lower`/`yhat_upper` regardless of which model produced it). This is the model `app.py` actually uses — the per-currency model choice is fully automatic, there is no single "the" production model anymore. Each run also **appends** that day's forecast (stamped with today's date as `generated_on`) to `data/forecast_history/history_<code>.csv` — unlike `forecast_<code>.csv`, which is overwritten every run and only ever holds the latest forecast, this history file accumulates over time and is what `accuracy.py` uses to score past forecasts once their target dates arrive.
4. `compare_models.py` — a separate, more thorough comparison: runs Prophet and an ARIMA baseline on the *same* train/test split per currency at 3 horizons (7/30/90 days) and writes `data/model_comparison.json`. This is a documentation/analysis script, not part of the app's runtime path, and is a different (deeper) comparison than the single-horizon one `forecast.py` uses to pick its production model. Only actually run against USD/EUR in depth so far — see "Model comparison" below; re-running it across all currencies is slow (Prophet + ARIMA AIC search × 3 horizons × 20 currencies) and hasn't been done.
5. `accuracy.py` — scores `forecast.py`'s **realized** accuracy: joins `data/forecast_history/history_<code>.csv` against the actual rates in `data/raw/<code>_try_data.csv` on `ds`, keeping only rows whose target date has already happened, buckets them by how many days ahead they were forecast (`horizon_days = ds - generated_on`, buckets 1-7/8-30/31-90 days), and writes MAE/RMSE/MAPE per bucket plus overall to `data/accuracy/accuracy_<code>.json`. This is distinct from `forecast.py`'s backtest MAPE (`data/metrics/metrics_<code>.json`), which measures held-out historical accuracy at training time — `accuracy.py` measures how the *actual, currently-deployed* forecasts have performed against reality since they were generated. A currency with no history yet (or no history entries whose target date has passed) gets no accuracy file; `app.py` handles that as "not enough history yet" rather than an error. Must run after `forecast.py` (needs the history file it produces) and after a fresh `main.py` (needs current actuals): `main.py` → `forecast.py` → `accuracy.py`.
6. `app.py` — Streamlit pricing UI: user picks a currency (dropdown shows all of `CURRENCY_SERIES`, labeled via `CURRENCY_NAMES`), enters quantity, unit price, and a target payment/delivery date; computes the TRY price at the current rate vs. the forecasted rate range for that date, a "kur riski payı" (currency risk margin) from `yhat_upper`, and plots recent history + forecast band together. The risk margin is shown as-is, including negative (when the model forecasts a decline, `yhat_upper` can be below the current rate) — it is **not** floored at zero. When formatting a negative delta for `st.metric`, put the sign as the very first character of the delta string (e.g. `f"-%{abs(risk_pct):.2f}"`, not `f"%{risk_pct:.2f}"`) — Streamlit's delta arrow/color only reads the sign correctly if it's the leading character; a `"%"` prefix before a negative number silently renders as a green up-arrow, which is backwards. A "Model doğruluk geçmişi" section below the chart reads `data/accuracy/accuracy_<code>.json` (via `accuracy_path`) and shows realized MAPE overall and by horizon bucket, wrapped in a `try`/`except FileNotFoundError` — same pattern as the mandatory-file check earlier in the script, but non-fatal here since a currency legitimately has no accuracy file until enough history accumulates.

### File layout

Everything generated (fetched data, forecasts, metrics) lives under `data/`, kept separate from the source files at the repo root:

```
main.py, forecasting.py, forecast.py, compare_models.py, app.py   <- source, repo root
CLAUDE.md, ONERI_DOKUMANI.md                                       <- docs, repo root
data/
  raw/<code>_try_data.csv                    <- main.py output (per-currency history)
  forecasts/forecast_<code>.csv              <- forecast.py output (per-currency forward forecast, overwritten each run)
  metrics/metrics_<code>.json                <- forecast.py output (per-currency backtest result)
  forecast_history/history_<code>.csv        <- forecast.py output (appended each run, one row per generated_on+ds)
  accuracy/accuracy_<code>.json              <- accuracy.py output (realized accuracy vs. actual rates)
  model_comparison.json                      <- compare_models.py output
archive/                                                          <- pre-existing, unrelated file kept aside (see below)
```

**Never hardcode a path to one of these files anywhere** — always go through `forecasting.data_path(code)` / `forecast_path(code)` / `metrics_path(code)` / `model_comparison_path()` / `forecast_history_path(code)` / `accuracy_path(code)`. All scripts that touch these files already do this; if you add a new script, do the same rather than reconstructing the path inline, or a future reorganization will silently miss it. The five `data/*` subdirectories are created automatically (`os.makedirs(..., exist_ok=True)`) the first time `forecasting.py` is imported, so no manual setup is needed after a fresh clone.

**Git tracking:** `data/raw/` and `data/model_comparison.json` are gitignored (raw history can always be re-fetched from EVDS; `compare_models.py` output is a documentation artifact, not needed at runtime). `data/forecasts/`, `data/metrics/`, `data/forecast_history/`, and `data/accuracy/` **are** committed — they're small and tracking them is what lets the GitHub Actions workflow (below) publish its daily results as visible commits, and lets `accuracy.py`'s history accumulate across machines instead of resetting on every clone.

`archive/forecast_plot.png` predates this project's current pipeline (no code references it, `matplotlib` is installed but unused) and was moved aside rather than deleted during a repo cleanup — safe to delete outright if it's confirmed unneeded, but left alone since it wasn't ours to remove without checking.

### Adding/removing a currency

Everything is driven off `forecasting.CURRENCY_SERIES` — add or remove an entry there (and the matching `CURRENCY_NAMES` entry), then re-run `main.py` then `forecast.py`. Don't hardcode a currency list anywhere else; `main.py`, `forecast.py`, `compare_models.py`, and `app.py` all iterate `CURRENCY_SERIES` already. Before adding a new code, verify TCMB is still actively publishing it — the EVDS `bie_dkdovytl` datagroup also lists several currencies that no longer get updated (BGN, IRR at time of writing) and a batch of pre-Euro national currencies (DEM, FRF, ITL, ATS, BEF, FIM, NLG, IEP, ESP, LUF, PTE, GRD) plus ECU that stopped in ~2002 — check with `evds.get_data([...], startdate=<last 10 days>, enddate=<today>)` and confirm non-null rows before trusting a series code.

XDR (IMF Special Drawing Rights) was also removed by explicit request — it's actively published by TCMB and was previously included for that reason, but it isn't a real currency and has no use in the company's product/service pricing scenario. If a similar not-quite-a-currency series comes up again, the same reasoning applies: "TCMB still publishes it" is necessary but not sufficient for inclusion — it also needs to be something the business actually prices in.

There is no shared library beyond `forecasting.py`, no tests, and no build system.

**Important:** `app.py` never trains a model itself — it only reads the CSV/JSON files `forecast.py` produces, because retraining on every Streamlit rerun is too slow. Any time `main.py` is re-run to refresh data, `forecast.py` must be re-run afterward, or `app.py` will show stale forecasts (it errors clearly via `FileNotFoundError` handling if the files are missing entirely, but not if they're just outdated). `st.cache_data` also caches by file *path*, not content — if you regenerate the CSV/JSON files while a Streamlit process is already running, you must restart it (rerunning in the browser is not enough) to see the new numbers.

## Environment setup

No `requirements.txt`/`pyproject.toml` exists; dependencies are tracked only by what's installed in `.venv`. Key packages (see exact pinned versions via `.venv/Scripts/pip.exe list`):

- `evds` — TCMB EVDS API client
- `python-dotenv` — loads `.env`
- `pandas`, `numpy`
- `prophet` (+ `cmdstanpy` backend)
- `statsmodels` — ARIMA (used both as the `compare_models.py` comparison baseline and, when it wins, as a currency's actual production model via `forecasting.select_best_model`/`forecast_future_arima`)
- `scikit-learn` — only used for `mean_absolute_error`/`mean_squared_error`
- `streamlit`, `altair` — pricing UI and its charts (`app.py`)
- `matplotlib` — installed but unused; no plotting code currently in the scripts

Use the existing `.venv` (Windows): `.venv\Scripts\python.exe <script>.py`.

`main.py` requires a `TCMB_API_KEY` in a `.env` file at the repo root (gitignored). Get a key from the EVDS website; without it `evds.evdsAPI` will fail to authenticate.

## Common commands

```
# 1) Refresh data/raw/<code>_try_data.csv for every currency in CURRENCY_SERIES from the EVDS API (requires .env with TCMB_API_KEY)
.venv\Scripts\python.exe main.py

# 2) Retrain, backtest, and regenerate data/forecasts/*.csv / data/metrics/*.json / data/forecast_history/*.csv for every currency (must run after step 1)
.venv\Scripts\python.exe forecast.py

# 3) Score realized accuracy of past forecasts into data/accuracy/*.json (must run after step 2)
.venv\Scripts\python.exe accuracy.py

# 4) Optional: Prophet vs ARIMA comparison report (data/model_comparison.json) — slow across all currencies, see above
.venv\Scripts\python.exe compare_models.py

# 5) Launch the pricing UI (reads the files steps 2-3 produced)
.venv\Scripts\python.exe -m streamlit run app.py
```

There are no lint or test commands configured in this repo.

## Automated daily refresh (GitHub Actions)

`.github/workflows/refresh.yml` runs the full pipeline (`main.py` → `forecast.py` → `accuracy.py`) daily on GitHub's own runners (cron, 05:00 UTC), plus on-demand via the Actions tab's "Run workflow" button (`workflow_dispatch`). If the pipeline produced any changes, the workflow commits `data/forecasts`, `data/metrics`, `data/forecast_history`, and `data/accuracy` back to the repo as `github-actions[bot]`, so the repo's forecasts stay current without anyone running the scripts by hand.

This requires a **`TCMB_API_KEY` repository secret** (Settings → Secrets and variables → Actions → New repository secret, same key as the local `.env`) — without it, `main.py`'s step in the workflow fails at the EVDS auth step. The workflow needs `permissions: contents: write` to push its own commits; this is already set in the workflow file.

`data/raw/` stays gitignored even though the workflow refreshes it every run — only the derived files listed above are committed. If you change what `main.py`/`forecast.py`/`accuracy.py` write to disk, check whether the workflow's `git add` list in the "Sonuclari commit'le" step needs updating to match, or new output will silently never get committed by CI (it'll still be produced and used in that run, just not persisted to the repo).

## Data pipeline notes

- `main.py` fetches data in fixed yearly chunks (`date_ranges` list, 2019–present) because the EVDS API limits how large a single date range request can be. When extending history, add a new chunk rather than widening an existing range. Each chunk is one API call covering *all* currencies at once (EVDS accepts a list of series codes), not one call per currency.
- Not every currency has data back to 2019 — TCMB only started publishing some series later (e.g. AZN/TRY ~Dec 2021). `main.py`'s per-currency `dropna()` handles this fine (rows before a series existed are just NaN and get dropped), but it means `TRAIN_WINDOW_DAYS` (730) is a *cap*, not a guarantee — some currencies train on much less history. `forecasting._limit_window` and Prophet handle a shorter series without special-casing, just with less data to learn from. (KZT/TRY was the extreme case of this — only ~150 rows since TCMB started publishing it ~Nov 2025 — and was removed from `CURRENCY_SERIES` for exactly this reason; see "Model comparison" below.)
- Columns are renamed from Turkish (`Tarih`, `TP_DK_<CODE>_A`) to `date`/`rate` before saving — every currency CSV shares this generic schema so `forecasting.load_series` works for any of them.
- `forecasting.evaluate_holdout` (Prophet) and `forecasting.evaluate_arima_holdout` (ARIMA) both split off the last `TEST_SIZE` (30) rows chronologically (not random) from the *same* `_limit_window`-ed training data, so their metrics are directly comparable — that's what `compare_models.py` relies on.
- `forecasting._limit_window` caps training data to the last `TRAIN_WINDOW_DAYS` (730 = 2 years), used by both `evaluate_holdout` and `forecast_future`. **Do not remove this** — training on the full 2019+ history reintroduces a systematic bias (see below).
- `forecasting.train_prophet` disables `yearly_seasonality`/`weekly_seasonality`. **Do not re-enable these** — see below.
- `forecasting.forecast_future` retrains on the windowed data (train+test combined, i.e. up through today) before producing the forward forecast used by the app, so it isn't handicapped by holding out the most recent 30 days.

### Known model pitfalls (found and fixed during development — don't reintroduce)

1. **Full-history training biases EUR/TRY upward.** The EUR series includes the Dec 2021 TRY crisis (a real ~25% single-day move, not a data bug). Prophet's linear trend extrapolates that period's steep growth forward, so a model trained on all data from 2019 is systematically biased high (backtest MAPE ~6.5% for EUR vs ~0.9% for USD). Fix: `TRAIN_WINDOW_DAYS = 730` — restricting training to the last 2 years dropped EUR backtest MAPE to ~0.7%, and slightly improved USD too.
2. **Yearly seasonality is unreliable and misleading with only ~2 years of data.** With `TRAIN_WINDOW_DAYS` limited to 2 years (only 2 yearly cycles observed), Prophet's yearly seasonality component is essentially overfit noise dressed up as a pattern. For EUR/TRY specifically, it fabricated a ~8-9% "seasonal decline" for Sep–Oct even though the underlying trend component was flat/rising — i.e. it forecast the rate would *drop* over the next 3 months, contradicting both the recent actual trend and the USD forecast direction. Weekly seasonality has no plausible causal basis for FX data either (business-day-only data has no real day-of-week cycle; the component mostly fit weekend-gap noise). Fix: `yearly_seasonality=False, weekly_seasonality=False` in `train_prophet`. Verified this doesn't hurt the 30-day backtest MAPE (near-identical with seasonality on/off) — the damage was specifically in longer-horizon (60–90 day) extrapolation.
3. Both of the above were caught by *inspecting the forecast trajectory shape* (`fc[['ds','trend','yearly','weekly','yhat']]`), not just by looking at the aggregate MAPE number — the 30-day backtest MAPE alone didn't reveal either problem. If asked to change `TRAIN_WINDOW_DAYS`, the seasonality flags, or Prophet's other defaults, re-run this kind of sanity check (does the forecast direction/magnitude match the recent raw-data trend?) before trusting the new metrics.
4. With both fixes in place, backtest MAPE stayed in a sane single-digit range across all 22 currencies when this was checked with Prophet-only (worst cases were NOK ~5.8%, AUD ~4.0%, RUB ~3.3%; most were under 1.5%) — no other currency has been individually root-caused the way EUR/USD were, so if one currency's MAPE looks like an outlier, apply the same "inspect the trajectory, don't just trust MAPE" process before assuming the model is fine. (These Prophet-only numbers were later superseded by per-currency Prophet-vs-ARIMA selection — see "Model comparison and per-currency production selection" below for current numbers.)
5. **Prophet's default `changepoint_range=0.8` can miss a trend break in the most recent ~20% of the training window, making the *production* forecast (not the backtest) point the wrong direction.** With `TRAIN_WINDOW_DAYS=730`, the last 20% is ~146 days (~5 months) during which Prophet is not allowed to place a new changepoint — the trend slope for that whole span, and everything forecast beyond it, is locked to whatever slope the last pre-cutoff changepoint set. Caught on KRW/TRY: a real 3-week, +6.6% rally in July 2026 fell entirely inside that blind window, so the fitted trend on the very last training day was 3.71% *below* the actual last observed rate, and `forecast_future` (trained through today) projected a decline for the next 90 days — directly contradicting the raw data (which was still rising). The 30-day backtest MAPE didn't flag this (it barely moved, 1.426% → 1.426%) because the backtest's train/test cutoff is 30 days earlier and doesn't include the affected window — **this is a case the standard backtest is structurally blind to; only inspecting "does `forecast_future`'s value on the last training day match the actual last training value" catches it.** Fix: `select_best_model` now tries Prophet at `changepoint_range` ∈ `PROPHET_CHANGEPOINT_RANGES = [0.8, 0.9, 0.95]` (plus ARIMA) as separate candidates and keeps whichever wins the 30-day backtest; verified this is non-regressive across all 20 currencies (same-or-better final MAPE everywhere, confirmed by an explicit before/after sweep) and it flips KRW's chosen config to `changepoint_range=0.95`, which correctly forecasts a continued rise. If you ever see a currency's forecast trend visually contradict its own recent raw data again, re-run this same check (`fc = model.predict(train_df[['ds']]); fc.iloc[-1]['yhat']` vs `train_df.iloc[-1]['y']`) before assuming the forecast is fine — a low/tied backtest MAPE does not rule this out.

### Model comparison and per-currency production selection

Two related but distinct comparisons exist:

- **`compare_models.py`** (deep, multi-horizon, documentation-only): backtests Prophet vs. ARIMA at 7/30/90-day horizons, currently only run in depth for USD/EUR (see table below). Useful for understanding *why* a currency favors one model, not used at runtime.
- **`forecasting.select_best_model`** (shallow, single-horizon, drives production): backtests Prophet (at each `changepoint_range` in `PROPHET_CHANGEPOINT_RANGES`) and ARIMA at the standard 30-day horizon only, and `forecast.py` uses whichever of those candidates wins to generate that currency's `forecast_<code>.csv`. This is what actually determines the model behind each currency in `app.py`.

7/30/90-day comparison (from `compare_models.py`, USD/EUR only — numbers move slightly as data refreshes):

| Horizon | USD/TRY winner | EUR/TRY winner |
|---|---|---|
| 7 days  | ARIMA (clearly) | Prophet (clearly) |
| 30 days | ARIMA (clearly) | Prophet (~tied) |
| 90 days | Prophet | Prophet (clearly) |

This table is *why* production selection was changed from "always Prophet" to per-currency: at the 30-day horizon the app's backtest reports, ARIMA is often meaningfully better, especially for volatile currencies where Prophet's smooth trend can't track short-term autocorrelation. A single global choice was leaving accuracy on the table.

**Current state (20 currencies, after the switch to per-currency selection): 17 have backtest MAPE under 1%; NOK (1.50%), KRW (1.43%), and RUB (2.78%) do not.** Typical winning margins for the 17 were large — e.g. AUD went from Prophet's 4.00% to ARIMA's 0.66%, CHF from Prophet's 1.87% to ARIMA's 0.54%. `ARIMA_ORDER_SEARCH` was widened from p,q ∈ [0,2] to [0,3] specifically because the extra flexibility helped the more volatile currencies (e.g. NOK's best order is `(1,1,0)`, but several others needed order-3 terms to win).

**NOK, KRW, RUB stay above 1% MAPE despite extensive tuning, and were kept in `CURRENCY_SERIES` anyway — this was an explicit product decision, not an oversight.** A 4th currency, KZT, was also above 1% (best achieved: 2.33%) but *was* removed — see below for the distinction. Before accepting the NOK/KRW/RUB numbers, the following were tried and did NOT get any of them under 1%:
- Prophet training-window sweep (180/365/547/730/1095 days) — best case for RUB was still 3.03% (1095-day window), for NOK still 4.34% (180-day), for KRW flat at 1.43% for any window ≥365 days.
- ARIMA order search extended to p,q ∈ [0,3] (from [0,2]) — improved NOK to 1.50% but no further.

**Why KZT was removed but NOK/KRW/RUB were not:** the user's instruction was to remove currencies whose >1% MAPE is caused by *insufficient dataset*, and explicitly keep currencies whose >1% MAPE is caused by the currency's *inherent volatility* instead. KZT/TRY only has ~150 rows of history (TCMB started publishing it ~Nov 2025) and its MAPE was flat at ~2.5% regardless of training window — a clear data-scarcity case, and more history may fix it automatically as TCMB accumulates more data (no code change needed, just re-add the `CURRENCY_SERIES`/`CURRENCY_NAMES` entries and re-run `main.py`/`forecast.py` once enough months have passed). NOK, KRW, and RUB all have ample data (1200–1900 rows) and their MAPE didn't budge with more/less training data — their day-to-day volatility (0.5–2.5% swings, vs. well under 0.5% for most currencies that hit sub-1%) appears to be a real statistical floor on 30-business-day-ahead point-forecast MAPE for a near-random-walk series, not something more data or tuning fixes. If asked to further improve NOK/KRW/RUB specifically, a fundamentally different approach (e.g. GARCH for volatility, or accepting a wider/asymmetric interval instead of chasing point-forecast MAPE) is more promising than further ARIMA/Prophet parameter search — and don't re-remove them for still being over 1%, that was already considered and rejected.

`forecast_future_arima` in `forecasting.py` is the ARIMA counterpart to `forecast_future`: it produces the same `ds`/`yhat`/`yhat_lower`/`yhat_upper` schema (using `get_forecast().summary_frame()` for the confidence interval) so `app.py` never needs to know which model backs a given currency's forecast file — it just displays `metrics['model']` in the UI caption. One difference to be aware of: ARIMA's forecast dates are business days only (`len(business_days)` rows, ~64 for a 90-calendar-day horizon), while Prophet's are all calendar days (90 rows) — `app.py`'s nearest-date matching (`day_diff`) handles this transparently, but don't assume `forecast_<code>.csv` always has exactly 90 rows.

### A harmless-but-alarming child process during `main.py`/`forecast.py`/`compare_models.py`

Running any of these scripts (or even just `import forecasting`) spawns a short-lived child `python.exe` process whose command line echoes the parent script's name (e.g. `python.exe forecast.py`), running from the **base** interpreter (`.venv`'s `pyvenv.cfg` → `home`/`base-executable`), not `.venv`'s own `python.exe`. This looks alarming — like the script re-executing itself and racing on the same output files — and it was investigated at length under that theory (including adding `if __name__ == "__main__":` guards to `main.py`/`forecast.py`/`compare_models.py`, which are harmless and were kept, but were not actually the fix for anything). A minimal repro (`import forecasting` alone, no loop) confirmed: the child process appears immediately at import time (before any model fitting) and exits on its own within ~1-2 seconds without duplicating any of the script's actual work or output. It's very likely a transient resource-tracker/capability-probe subprocess from one of `prophet`/`cmdstanpy`/`joblib` (scikit-learn's dependency) that happens to resolve `sys.executable` to the venv's base interpreter. **It is safe to ignore.** Don't re-diagnose this as a race condition without new evidence (e.g. actually-duplicated rows in an output file, or the child process still running seconds after the parent).
