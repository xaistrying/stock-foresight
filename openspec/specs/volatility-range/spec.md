# volatility-range

## Purpose

TBD

## Requirements

### Requirement: The displayed range is a calibrated 5-session band (Rule 1, Rule 2)
The system SHALL compute `sigma_daily_pct`, the HAR-RV forecast of the daily standard deviation of log returns in percent (`exp(pred) × 100`), and from it the displayed band half-width `range_5s_pct = range_k × √5 × sigma_daily_pct`, in percent, for a horizon of 5 TRADING SESSIONS (Rule 1; a session is one stored OHLCV row, as in `compute_target`). `sigma_daily_pct` MUST NOT be labelled as a 5-session figure anywhere. `range_k` is the multiplier stored in the model artifact, fitted so that the band contains `|ln(close[t+5]/close[t])| × 100` with the artifact's nominal coverage `range_coverage` (0.68). The UI MUST show a percentage, never a raw log value (Rule 2). The band is called "typical 5-session move" and is described as a size, not a direction, a ceiling or a prediction.

#### Scenario: Band computed from the daily sigma
- **WHEN** `sigma_daily_pct` is 1.50 and the artifact's `range_k` is 1.20
- **THEN** `range_5s_pct` is `1.20 × √5 × 1.50`, about 4.02

#### Scenario: Daily sigma is never presented as the 5-session range
- **WHEN** any API response, prompt, export line or panel line shows `range_5s_pct`
- **THEN** its label says "typical 5-session move", and `sigma_daily_pct` appears only under its own name or as "daily volatility"

### Requirement: range_k is one global multiplier fitted out of time
The training script SHALL fit `range_k` as the empirical `range_coverage`-quantile of `z = |ln(close[t+5]/close[t])| / (√5 × sigma_daily_pct(t) / 100)` pooled over the calibration universe, using only windows whose outcome date (`t+5`) precedes the training cutoff. Overlapping windows MAY be used for the point estimate. The script SHALL validate by an expanding walk-forward over calendar years (for each test year, refit the HAR coefficients and `range_k` on windows whose outcome date precedes that year, then measure coverage in it) and SHALL record the pooled out-of-time coverage, per-year coverage, a date-block (calendar-month) bootstrap interval and coverage by sigma quintile in the artifact. The artifact's reported coverage MUST be the out-of-time figure, not the in-sample coverage of the final multiplier. `range_k` MUST NOT be fitted per ticker.

#### Scenario: Windows whose outcome is after the cutoff are excluded
- **WHEN** the fit runs with a cutoff date and a window at `t` has its `t+5` row on or after the cutoff
- **THEN** that window contributes to neither the HAR fit nor `range_k` for that fold

#### Scenario: Reported coverage is out of time
- **WHEN** the artifact is written
- **THEN** its `validation.pooled_coverage` is computed over the walk-forward test years only, and `validation.folds` lists each test year with its row count, coverage, `k` and the HAR and baseline correlations

### Requirement: Training refuses an artifact that fails its validation gates
`backend/scripts/train_har_rv.py` SHALL exit non-zero and leave any existing artifact untouched unless, over the walk-forward folds: pooled out-of-time coverage is within 0.05 of `range_coverage`; no test year is more than 0.10 from it; the mean over the test years of the HAR's out-of-time correlation with log realised volatility is not below the mean of the same correlation for a plain `log(rv20)` baseline (each fold has its own refit intercept, so a pooled correlation would measure fold-to-fold level shifts that the fixed baseline lacks); and at least 100,000 pooled rows from at least 100 tickers were available. The in-sample correlation floor SHALL be removed. These thresholds are provisional and not covered by domain rules 1-6.

#### Scenario: Coverage gate fails
- **WHEN** pooled out-of-time coverage is 0.60 against a nominal 0.68
- **THEN** the script prints the failing gate, exits non-zero and does not modify `har_rv_model.json`

#### Scenario: Baseline gate fails
- **WHEN** the mean per-fold out-of-time correlation of the HAR is below that of the `log(rv20)` baseline
- **THEN** the script exits non-zero and writes no artifact

### Requirement: Sigma above the exchange limit is out of bounds, never clipped
The system SHALL treat `sigma_daily_pct` above `SIGMA_DAILY_MAX_PCT = 7.0` (the HOSE daily price limit, `DAILY_PRICE_LIMITS["HSX"]`), or not finite, as out of bounds. It MUST NOT clip the value or serve a band computed from it. The range endpoint SHALL answer status `range_out_of_bounds` with `range_5s_pct` and `range_hit_rate` null and `sigma_daily_pct` returned as computed. There is no lower bound.

#### Scenario: Corrupt recent closes
- **WHEN** an eligible ticker's recent closes give `sigma_daily_pct` 41.7
- **THEN** status is `range_out_of_bounds`, `range_5s_pct` is null and `sigma_daily_pct` is 41.7

#### Scenario: At the limit
- **WHEN** `sigma_daily_pct` is exactly 7.0
- **THEN** it is within bounds and the band is served

### Requirement: GET /tickers/{ticker}/range returns the band, its coverage and its status
The API SHALL expose `GET /tickers/{ticker}/range` returning `{ticker, as_of, status, reasons, sigma_daily_pct, range_5s_pct, range_k, range_coverage, range_hit_rate}`. `as_of` is the date of the last close used. `status` is one of `ok`, `uncalibrated`, `ineligible`, `range_out_of_bounds`, `model_unavailable`, evaluated in this order, first match wins: no OHLCV rows (HTTP 404 `{"detail": "Ticker has not been loaded"}`); `assess_eligibility(ticker)` reporting any reason other than `indicators_missing` (`ineligible`, `reasons` copied from the service minus `indicators_missing`); artifact unavailable (`model_unavailable`); fewer than 61 usable closes (`ineligible`, `reasons: ["insufficient_history"]`); sigma out of bounds (`range_out_of_bounds`); ticker outside the artifact's calibration universe (`uncalibrated`); otherwise `ok`. `indicators_missing` is ignored because the range needs only closes; all other reasons (including `near_gap` and `hard_quality_flag`) block. The range module MUST NOT implement its own delisted, stale, gap or quality rules; `reasons` is empty unless status is `ineligible`. Fields that do not apply are null. The ticker is bound as a query parameter, never interpolated.

#### Scenario: Eligible, calibrated ticker
- **WHEN** an eligible ticker in the calibration universe is requested
- **THEN** status is `ok`, `range_5s_pct`, `range_k`, `range_coverage` (0.68) and `range_hit_rate` are populated and `reasons` is `[]`

#### Scenario: Ineligible ticker
- **WHEN** `assess_eligibility` returns `{eligible: false, reasons: ["stale", "indicators_missing"]}`
- **THEN** status is `ineligible`, `reasons` is `["stale"]` and every numeric field is null

#### Scenario: Missing indicators do not block the range
- **WHEN** `assess_eligibility` returns `{eligible: false, reasons: ["indicators_missing"]}` for a ticker with a full closes history
- **THEN** evaluation continues and status is `ok` (or `uncalibrated`), with `reasons` `[]`

#### Scenario: Ticker never loaded
- **WHEN** the ticker has no OHLCV rows
- **THEN** the response is HTTP 404 with detail "Ticker has not been loaded", and eligibility is not consulted

#### Scenario: Model artifact missing
- **WHEN** `har_rv_model.json` does not exist or fails validation
- **THEN** status is `model_unavailable`, numeric fields are null and no exception reaches the client

#### Scenario: Eligible ticker outside the calibration universe
- **WHEN** an eligible ticker is not in the artifact's `universe.symbols`
- **THEN** status is `uncalibrated`, the band is served with the global `range_k`, and `range_coverage` is null

#### Scenario: Eligibility threshold below the arithmetic minimum
- **WHEN** the eligibility service reports eligible but the ticker has 50 usable closes
- **THEN** status is `ineligible` with `reasons: ["insufficient_history"]` and an error is logged

### Requirement: range_hit_rate measures the band against the ticker's own recent history
`range_hit_rate` SHALL be `{rate, n}`. Over the ticker's last `n` five-session moves, taken as non-overlapping windows at a stride of 5 rows with the newest at the latest date `t` that has a `t+5` row, and at most 50 windows (about one year), `rate` is the fraction in which `|ln(close[t+5]/close[t])| × 100 ≤ range_k × √5 × sigma_daily_pct(t)`, with `sigma_daily_pct(t)` recomputed from closes up to and including `t` only, using the loaded model and the current `range_k`. `n` is the number of windows scored and SHALL be returned. Windows whose sigma is out of bounds or not finite SHALL be excluded from `n`. With fewer than 20 windows `rate` is null and `n` is returned. The computation SHALL read at most 311 OHLCV closes for the ticker (the latest, ordered by date, `close > 0`) and SHALL NOT read its full history. `range_k` was fitted on history that includes these windows, and 50 windows leave a standard deviation of about 0.07 in the rate; the rate is descriptive and MUST NOT be presented as a probability or as Confidence.

#### Scenario: Known fixture
- **WHEN** a fixture of closes yields 35 hits in 50 non-overlapping windows
- **THEN** `range_hit_rate` is `{rate: 0.7, n: 50}`

#### Scenario: Windows do not overlap
- **WHEN** `range_hit_rate` is computed
- **THEN** consecutive scored windows start 5 rows apart, so no close is the start of two windows

#### Scenario: No look-ahead
- **WHEN** a close after date `t+5` is changed
- **THEN** the hit or miss for window `t` is unchanged

#### Scenario: Short history reports its n
- **WHEN** the ticker has history for only 30 windows
- **THEN** `range_hit_rate` is `{rate: <fraction>, n: 30}`

#### Scenario: Too few windows
- **WHEN** the ticker has history for only 15 windows
- **THEN** `range_hit_rate` is `{rate: null, n: 15}`

#### Scenario: Bounded read
- **WHEN** the ticker has 2,500 stored sessions
- **THEN** at most 311 rows are read for the computation

### Requirement: The model artifact is a versioned JSON file, written atomically and loaded once
The HAR-RV model SHALL be stored in `backend/data/models/har_rv_model.json` containing `schema_version`, `model_version`, `trained_at`, `data_through`, `features`, `intercept`, `coef`, `target`, `range_k`, `range_coverage`, `universe` (`criteria`, `n_tickers`, `symbols`), `n_rows` and `validation`. `train_har_rv.py` SHALL write it to a temporary file in the same directory and replace the target atomically. Serving SHALL NOT unpickle any file and SHALL NOT import scikit-learn. `load_model()` SHALL read the file once, cache the result keyed on the file's modification time, re-read only when it changes, and return nothing (never raise) when the file is missing, malformed, has non-finite numbers or an unsupported `schema_version`.

#### Scenario: Loaded once across requests
- **WHEN** 100 range computations run against an unchanged artifact
- **THEN** the file is opened once

#### Scenario: Retrain picked up without restart
- **WHEN** the artifact is replaced while the server runs
- **THEN** the next computation uses the new coefficients and `model_version`

#### Scenario: Interrupted training leaves the old artifact
- **WHEN** the script fails after fitting but before the replace
- **THEN** the previous `har_rv_model.json` is byte-for-byte unchanged

### Requirement: Debate result and agent positions carry the calibrated range fields
`AgentPosition` (Technical agent only), `DebateResult` and the `POST /tickers/{ticker}/debate` JSON SHALL carry `range_5s_pct`, `sigma_daily_pct` and `range_coverage` in place of `volatility_range_pct`, which SHALL be removed with no deprecated alias. All three are null when the range service does not serve a band. `GET /tickers/{ticker}/prediction` SHALL NOT return `volatility_range_pct` either.

#### Scenario: Debate response shape
- **WHEN** a debate completes for a ticker with status `ok`
- **THEN** the JSON has `range_5s_pct`, `sigma_daily_pct` and `range_coverage` at the top level and in `round1.technical` and `round2.technical`, and no `volatility_range_pct` key anywhere

#### Scenario: No band served
- **WHEN** the range status is `range_out_of_bounds` or `model_unavailable`
- **THEN** the three fields are null and the debate still completes

### Requirement: Evaluation script reproduces the coverage figures read-only
`backend/scripts/evaluate_vol_range.py` SHALL open the database read-only (`mode=ro`), write no table and no model file, and report coverage of `|ln(close[t+5]/close[t])|` by the band at ×1 and ×√5 and at `range_k`, for: all dates in sample, non-overlapping dates, the last 12 months, a time-split refit (train before 2024, test from 2024-02), inside and outside the modelling universe, by calendar year and by sigma quintile; plus date-clustered mean and standard deviation, the realised to predicted sigma ratio, out-of-time correlation against the `log(rv20)` baseline, and the share of windows above `SIGMA_DAILY_MAX_PCT` by listing status.

#### Scenario: Read-only
- **WHEN** the script runs
- **THEN** the database file and the model file are unchanged afterwards and a write attempt on its connection fails

#### Scenario: Review figures are reproduced or flagged
- **WHEN** the script runs against the shipped pickle
- **THEN** it prints in-sample coverage over the modelling universe at ×1 and ×√5 next to the review's figures (32.3% and 61.0% on 385,909 windows) so a difference is visible
