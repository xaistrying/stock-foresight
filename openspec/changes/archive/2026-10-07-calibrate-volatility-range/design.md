## Context

`docs/DISCUSSION_post_pivot_review.md` (2026-10-06, six parallel read-only reviews) is the baseline. Its figures are the reviewers' measurements and have not been reproduced by the project; they are cited below as "measured in the 2026-10-06 review", and task 1 reproduces them before any later task relies on them. Where this document quotes a number that is not from the review it says so: a few were produced by a throwaway scratch script while drafting this change ("drafting-time scratch check", read-only on `backend/data/app.db`, not preserved). The scratch check agreed with the review's in-sample figures (32.3% as shipped and 61.0% at ×√5 on 385,909 windows of the 208 modelling tickers; 53.7% and 74.7% outside that universe). Every figure remains unverified until task 1.3 runs.

Current state (tree at commit e77986e):

- `backend/app/ml/volatility.py` predicts `log σ = −4.94 + 9.28·rv5 + 13.77·rv20 + 14.18·rv60` (review; coefficients confirmed in the drafting-time scratch check) on raw trailing standard deviations of daily log returns. The target is the std of the next five daily log returns (`:90-98`). `predict_volatility_range` returns `exp(pred) × 100` (`:154-155`), unclipped, and calls it a "±% range for the next 5 trading sessions". It unpickles the model on every call (`:138`) and reads the ticker's full OHLCV (`:141`, `_load_ohlcv` `:34-46`).
- Measured in the review: the shipped value contains `|ln(close[t+5]/close[t])|` 32.3% of the time in sample (31.2-34.8% across the other tests listed there) and 61.0-64.7% after multiplying by √5; coverage is flat across range quintiles, so the ranking is fine and the level is wrong. About ×2.75 would be needed for 69%.
- Measured in the review: 28 loaded tickers return more than 25% (all delisted; MTC 2818%), 49 above 15%; live tickers top out near 6.3%. The model is trained on the 208-symbol modelling universe and served to all 599 loaded symbols; outside the universe ×1 covers 53.7% and ×√5 covers 74.7%.
- Measured in the review: realised mean σ is about 14% above mean `exp(pred)` (median-type estimate). Shipped out-of-time corr 0.431 against a plain `log(rv20)` baseline of 0.424.
- `train_har_rv.py` checks only an in-sample correlation floor of 0.35 (`:33`, `:94-104`), writes the pickle non-atomically (`:106-108`) and records no version, date or universe. The artifact (`har_rv_model.pkl`, 653 B) is gitignored.
- The range reaches users only through the debate: `AgentPosition.volatility_range_pct` (`engine.py:39`), `DebateResult.volatility_range_pct` (`:59`, `:129`), the API (`debate.py:35,51`), the Technical prompt (`technical.py:98`), the export line (`export.py:101-102`) and the panel (`DebatePanel.jsx:231-234`). `/prediction` also returns it (`predictions.py:63,71,84`); no frontend component reads that copy.

The `file:line` cites in this Context were re-checked on 2026-10-07 against commit e77986e (`git show`): each matches. They describe the code this change replaces and are historical on the working tree (`volatility.py`, `train_har_rv.py`, `predictions.py` and the debate files have been rewritten); the one live cite is `ohlcv_quality_gate.py:35-38` (`DAILY_PRICE_LIMITS`), which still holds.

Constraints: the six domain rules in `CLAUDE.md` are not edited here; the shared `assess_eligibility` service comes from `debate-data-guards`; the volatility model itself (a pooled linear HAR on raw features) is not redesigned here.

## Goals / Non-Goals

**Goals:**
- A displayed band whose meaning is stated and whose coverage has been measured out of time.
- A bounded output: an absurd sigma yields a status, not a number.
- A per-ticker measurement (`range_hit_rate`) computed cheaply from OHLCV.
- A model artifact that carries its own version and validation evidence, is written atomically and is loaded once.
- One preserved, read-only script that reproduces the review's coverage figures.

**Non-Goals:**
- A quantile-XGBoost (or other direct quantile) challenger; per-ticker models; a 90% or other second band; log-feature HAR (see Follow-ups).
- Eligibility rules themselves (`debate-data-guards` owns thresholds for delisted, stale, `near_gap`, quality flags, history length).
- The Rule 4 ruling, verdict display labels, `DISCLAIMER.md` (`align-rules-and-disclaimer`); outcome logging (`debate-outcome-log`).
- Watchlist curation, a scheduler, cross-sectional work, a multi-ticker Rail (undecided, out of scope for every sibling).
- Fixing data staleness. Until the database is refreshed (about 21 sessions missing on 2026-10-06, review Finding 2) most tickers will read as ineligible; that is the guard working, not a defect of this change.

## Decisions

### Decision 1: the displayed band is `range_k × √5 × sigma_daily_pct`; the daily sigma is never labelled "5 sessions"

**Chosen**: `sigma_daily_pct = exp(pred) × 100` (what `predict_volatility_range` returns today, renamed and kept internal). `range_5s_pct = range_k × √5 × sigma_daily_pct` is the half-width of the band; the band is scored against `|ln(close[t+5]/close[t])| × 100`, the quantity Rule 1 defines (5 trading sessions, row-offset like `compute_target`). The label is "typical 5-session move".

`range_k` is expected to be near 1.2 rather than 1 for three reasons it deliberately absorbs together: the estimate is median-type (Decision 6), returns are fat-tailed and volatility clusters, and the model's target (a standard deviation of five daily returns) is not the size of the 5-session move. A drafting-time scratch check put the 0.68-quantile of `|r5| / (√5 × σ̂)` at about 1.19 pooled over all dates of the modelling universe; the review's "×2.75 for 69%" corresponds to 1.23 on this scale.

**Alternatives considered**
- *Fit one multiplier on the daily sigma (about ×2.7)*: equivalent arithmetic, but hides the √5 aggregation and makes a reader think the daily sigma is itself a 5-session number again.
- *Plain √5 × σ (k = 1)*: the review measured only 61-65% coverage, so a stated "about 2 in 3" would be false.
- *Retrain the HAR on `|r5|` or a 5-session quantile*: the right long-run fix, but it is the challenger recorded under Follow-ups and a different model.

Domain rules: implements Rule 1's horizon and measures against its target quantity; Rule 2 is addressed in Decision 12. `range_k` and `range_coverage` are new definitions, not covered by rules 1-6.

### Decision 2: nominal coverage 0.68, stated as "about 2 in 3", and always shown with its complement

**Chosen**: `range_coverage = 0.68`, a fixed constant in the training script, stored in the artifact and echoed by the API. The label says "about 2 in 3 recent 5-session moves stayed within this range" so the reader also learns that about 1 in 3 went beyond it. Coverage is not Confidence and the label never uses that word.

**Alternatives considered**
- *0.50*: "typical" in the strictest sense, but a band that fails half the time invites over-reading of the other half.
- *0.80 or 0.90*: a more cautious band, roughly 1.4× or 2× wider. Fat tails mean a 90% band is not the 68% band times the normal ratio 1.65: the scratch check put the 0.9 quantile of the same ratio at about 2.35 against 1.19 (ratio 2.0). A second band needs its own fitted multiplier; deferred (Non-Goals).
- *Show the model's own σ with no coverage statement*: the review's point is that a stated, measured coverage is what the number lacks.

New threshold, not covered by rules 1-6. The owner confirmed on 2026-10-07 that 0.68 stays; nothing else in the design depends on it except the label wording (Decision 12).

### Decision 3: `range_k` is one global multiplier

**Chosen**: a single pooled multiplier fitted on the calibration universe.

Evidence (reproduced by task 1.3, see Reproduced figures): per-ticker coverage at the pooled multiplier has a standard deviation of 0.044 over 208 tickers with about 371 non-overlapping windows each, against a binomial 0.024 for independent windows; the excess is real but not clearly a per-ticker effect, because a ticker's windows share volatility regimes and are not independent, so the binomial figure understates the noise. Per-ticker `k` stays rejected on that basis (the fitted quantile would be noisy and its in-sample hit-rate flattering); coverage by sigma quintile at the pooled multiplier runs 0.66-0.71, a spread of 5 points; a rolling three-year multiplier did not remove the year-to-year swing (coverage by year 0.62-0.75), so time-varying `k` buys nothing visible.

**Alternatives considered**
- *Per ticker*: roughly 130 independent windows per ticker over three years; the fitted quantile is mostly noise and would show a flattering in-sample hit-rate.
- *Per sigma bucket* (five multipliers for at most 5 points of coverage): not worth five parameters now; the evaluation script reports coverage by quintile so the case can be re-opened if a retrain shows a larger gap.
- *Per sector*: no sector index exists in free vnstock data (archived Decision 7).

### Decision 4: the fit is an empirical quantile over all windows whose outcome is known, validated out of time

**Chosen**: for each calibration ticker and each date `t` whose `t+5` row exists, compute `z = |ln(close[t+5]/close[t])| / (√5 × σ̂(t))`; `range_k` is the empirical `range_coverage`-quantile of `z` pooled over the calibration universe, using only windows whose outcome date is before the training cutoff (a 5-session purge, same rationale as `purge_training_rows`). The point estimate uses all overlapping windows: overlap changes the variance of the estimate, not the quantile estimator (the review's non-overlapping test gave 32.2% against 32.3% for all dates). Uncertainty is reported with a date-block (calendar-month) bootstrap, because windows overlap in time and across tickers move together on the same days (review: date-clustered coverage sd 0.25 across 2,456 dates at the shipped scale).

Out-of-time validation is an expanding walk-forward by calendar year: for each test year Y, refit the HAR coefficients and `range_k` on windows whose outcome date precedes Y-01-01 and measure coverage in Y. The artifact's `range_coverage` measurement is the pooled out-of-time coverage, not the in-sample coverage of the final multiplier.

Drafting-time scratch check, reusing the shipped σ̂ and refitting only `k`: years 2020-2026 gave per-year coverage 0.61, 0.62, 0.62, 0.73, 0.74, 0.72, 0.70 and a pooled 0.675. The multiplier moves with the volatility regime (fits of 1.06 to 1.28 across the folds), so "about 2 in 3" is an average: single years run roughly 7 points either side. That variation is stated in the artifact and in the label's "about", not hidden.

**Alternatives considered**
- *Non-overlapping subsample (every 5th date)*: same point estimate, 5× less data, no benefit for the quantile.
- *Equal weight per date*: stops a crash day dominating but changes the quantity being calibrated and over-weights thin early dates.
- *Fit `k` and σ̂ on all data and report in-sample coverage*: what the review criticised.
- *Normal-theory `k = 1`*: see Decision 1.

### Decision 5: training gates and what they gate

**Chosen**: `train_har_rv.py` refuses to write an artifact (non-zero exit, old file untouched) unless, over the walk-forward folds: (a) pooled out-of-time coverage is within ±0.05 of `range_coverage`; (b) no single test year is more than ±0.10 away; (c) the mean over test years of the HAR's out-of-time correlation with log realised volatility is not below the mean for a plain `log(rv20)` baseline (shipped: 0.431 against 0.424, review; per fold, not pooled, because each fold's refit intercept shifts the predictions and a pooled Pearson correlation would measure those shifts; owner ruling 2026-10-07, after the pooled version missed by 0.0033); (d) at least 100,000 pooled rows and 100 tickers were available. Per-year coverage, per-sigma-quintile coverage, the date-block bootstrap interval and both correlations are written into the artifact's `validation` block either way.

All four thresholds are new and provisional, not covered by rules 1-6. (b) is looser than (a) on purpose: the scratch check above shows a ±7 point swing by year on current history, so a per-year gate tighter than ±0.10 would fail on known data; (c) is a "no worse than baseline" check because the margin is only 0.007 today. A failed gate is escalated to the owner, not loosened.

**Alternatives considered**: keep the 0.35 in-sample floor (it checks nothing about calibration); gate on a single hold-out year (one regime, high variance); gate on log-feature HAR beating baseline by a margin (turns the retrain into a model-selection change).

### Decision 6: median-type bias and fat tails are absorbed by the empirical quantile, with no separate correction

**Chosen**: no smearing factor and no distributional assumption. The multiplier is fitted on the realised ratio, so the review's finding that realised mean σ sits about 14% above mean `exp(pred)` (the drafting-time scratch check saw about 17%; both unreproduced) is included in `range_k`. Fat tails are handled by using an empirical quantile instead of a multiple of a normal σ. What a single global multiplier cannot absorb is heteroscedastic bias (the band being too narrow at high sigma and too wide at low sigma); the evaluation script and the artifact report coverage by sigma quintile so it would be visible.

**Alternatives considered**: Duan smearing on `exp(pred)` then `k` (a second parameter doing the same job and counted twice if both were fitted); log-feature HAR (review: corr 0.450 against 0.431 for the shipped model; an improvement to σ̂, not to calibration; Follow-ups); a Student-t or normal quantile table (assumes the shape the data contradicts).

### Decision 7: bounds: a daily sigma above 7% is not served

**Chosen**: `SIGMA_DAILY_MAX_PCT = 7.0`. If `sigma_daily_pct` is above it, or not finite, the range service answers status `range_out_of_bounds` with `range_5s_pct: null`; it never clips. `sigma_daily_pct` is still returned so the operator can see why.

Why 7: HOSE enforces a ±7% daily price limit (`DAILY_PRICE_LIMITS["HSX"] = 0.07`, `ohlcv_quality_gate.py:35-38`), so a sustained daily standard deviation above about 7% is not a market state; the model reaches it only from artefacts (missed splits, reset prices, delisting tails). Drafting-time scratch check: 0.35% of windows of listed tickers and 13.2% of windows of delisted tickers exceed 7%; among modelling-universe windows above 7% the band is far too wide (coverage 94% at `range_k` ≈ 1.19), consistent with artefacts rather than real regimes; one listed ticker's latest sigma was 7.65% in the same check. The review's "live tickers top out near 6.3%" is on a different date and consistent with a cut at 7.

Clipping is rejected because a clipped band carries the stated coverage no longer; a status is honest and testable.

**Interaction with eligibility**: eligibility is evaluated first (Decision 8), so delisted and stale tickers never reach this check; `range_out_of_bounds` is the backstop for a listed, apparently fresh ticker whose recent closes are corrupt. There is no lower bound: at zero recent volatility the intercept alone gives `sigma_daily_pct` ≈ 0.71 and a band near 1.9%; a ticker with no recent movement is an eligibility question (stale/illiquid), not a range one.

**Alternatives considered**: cap at 15% (the review's count of 49 tickers; far above any limit in the exchange table); a ticker-relative cap such as 3× trailing `rv60` (more machinery, and the failure it targets is already a data-quality case); clip features at training time (changes the model, Follow-ups).

New threshold, not covered by rules 1-6; derived from a market fact (the same table the quality gate uses), not tuned.

### Decision 8: statuses, and eligibility is consumed, not re-implemented

**Chosen**: `GET /tickers/{ticker}/range` order of evaluation, first match wins:

1. no OHLCV rows for the ticker: HTTP 404 `{"detail": "Ticker has not been loaded"}` (same wording as `/prediction` and `/debate`);
2. `assess_eligibility(ticker)` returns `eligible: false` with at least one reason other than `indicators_missing`: status `ineligible`, `reasons` = the service's reasons verbatim minus `indicators_missing`, all numeric fields null. If `indicators_missing` is the only reason, evaluation continues (the range needs only closes);
3. artifact missing, unreadable or of an unsupported version: status `model_unavailable`, numeric fields null (logged once per file change);
4. fewer than 61 usable closes despite eligibility (the arithmetic precondition for `rv60`): status `ineligible`, `reasons: ["insufficient_history"]` and an error log, because it means the eligibility threshold is below 61 (a cross-check test pins `debate-data-guards`' threshold to at least 61 rather than duplicating it);
5. `sigma_daily_pct` above 7 or not finite: status `range_out_of_bounds` (Decision 7);
6. ticker not in the artifact's calibration universe: status `uncalibrated` (Decision 9), band served, `range_coverage: null`;
7. otherwise `ok`.

`reasons` is `[]` unless status is `ineligible`. The only range-specific vocabulary is the two statuses `range_out_of_bounds` and `model_unavailable`; the eligibility reasons stay as `debate-data-guards` defines them (`delisted, insufficient_history, stale, near_gap, hard_quality_flag, indicators_missing`).

**`indicators_missing` does not block the range (owner ruling, 2026-10-07).** The range reads only closes; a null RSI or Ichimoku value says nothing about `rv5/rv20/rv60`. `/range` therefore ignores that one reason, through a single constant (`RANGE_IGNORED_ELIGIBILITY_REASONS = {"indicators_missing"}`) applied to the service's output; it does not re-derive anything. Consequence: the band can be available for a ticker for which the debate reports `INSUFFICIENT_DATA`; the two guards answer different questions (is the debate's input complete; is the closes series usable).

**`near_gap` and `hard_quality_flag` still block, deliberately.** The coordinator's suggestion to ignore `near_gap` as well was considered and not taken: `debate-data-guards` redefines `near_gap` as more than 2 market sessions missing from the ticker's own series within its last 65 priced sessions, which is almost exactly the closes the range uses (61 for `rv60`); a gap there turns a multi-session move into one "daily" return and inflates sigma and the hit-rate windows. A hard price-limit flag inside that span has the same effect. If the owner finds the `near_gap` guard withholds too many bands once real data is refreshed, the constant above is the one place to extend.

**Alternatives considered**: HTTP 4xx for ineligible tickers (breaks the "status in a 200" convention `/prediction` uses and makes the frontend branch on error handling); re-deriving staleness inside the range module (the duplication the shared service exists to prevent).

### Decision 9: outside the calibration universe the band is served as `uncalibrated`

**Chosen**: the artifact stores the 208 symbols the fit used. A ticker that passes eligibility but is not in that set gets status `uncalibrated`: same `range_k`, band shown, `range_coverage: null`, and the label does not state a coverage. Delisted tickers never get here (they fail eligibility), though 4 delisted symbols are in the modelling universe (universe composition, drafting-time scratch check).

Evidence (reproduced by task 1.3): outside the universe the pooled multiplier covers 79.5% overall and 76.2% for listed tickers, i.e. the band is too wide there (safe side) and the stated "about 2 in 3" would be wrong. About 201 listed symbols are outside the universe, 195 of them because they fail the liquidity filter, so an illiquid stock's sigma is biased by stale closes, which is why the universe excludes them.

**Alternatives considered**
- *Refuse them* (`ineligible`): hides a usable, conservative band from roughly 200 live stocks on a product decision (Watchlist curation) that is not decided and out of scope.
- *A second multiplier fitted on the outside tickers*: a second calibration set with different data quality and a second claim to validate.
- *Train on every eligible ticker*: moves the calibration toward illiquid names and changes the 208-symbol basis the review's numbers rest on.
- *Re-read `ticker_universe` flags at serve time*: they can drift after training, so the served claim would no longer match the set the fit measured.

### Decision 10: `range_hit_rate` is computed from non-overlapping five-session windows over about a year, from at most 311 closes

**Chosen (owner ruling, 2026-10-07)**: the last `n` five-session moves, `n` up to `HIT_RATE_MAX_WINDOWS = 50`, taken at a stride of 5 rows so the windows do not overlap. The newest window is the latest date `t` that has a `t+5` row; the others step back 5 rows at a time. The ticker's latest `HISTORY_ROWS = 61 + 5 × 49 + 5 = 311` closes are read (`WHERE ticker = ? AND close > 0 ORDER BY date DESC LIMIT 311`, an index range scan on the `(ticker, date)` primary key), reversed, and computed vectorised: log returns, rolling std over 5/20/60, `σ̂(t) = exp(intercept + coef·rv(t)) × 100`, band `b(t) = range_k × √5 × σ̂(t)`, and `hit(t) = |ln(close[t+5]/close[t])| × 100 ≤ b(t)`. `rate` is hits over `n` as a fraction, and `n` is the number of windows actually scored, reported in the response (`{rate, n}`). Windows whose σ̂ is out of bounds or non-finite are excluded and `n` shrinks; fewer than `HIT_RATE_MIN_WINDOWS = 20` windows gives `{rate: null, n}`. No window uses a close after its own `t` for σ̂; the one close after `t` that is read is the outcome close `t+5`. The band uses today's `range_k` and today's coefficients for every past date. 50 windows span about 250 sessions, roughly a year.

**Why non-overlapping**: consecutive daily windows share four of five days, so 60 of them are roughly 12 independent observations (the review's own point about overlapping windows). At a true coverage near 0.68 the rate then has a standard deviation of about 0.13; with 50 independent windows it is `sqrt(0.68 × 0.32 / 50)`, about 0.07. The cost is that the number reflects a year rather than the last quarter and moves in steps of 1/n. The thresholds `HIT_RATE_MAX_WINDOWS = 50` and `HIT_RATE_MIN_WINDOWS = 20` (noise about ±0.10 at the minimum) are new and not covered by rules 1-6. This replaces the shared contract's "most recent ~60 windows" (and Rule 4's "~60 predictions" framing); the response shape `{rate, n}` is unchanged.

Limits that remain, stated in the spec and expected in any UI copy:
- the windows are still independent only to the extent that returns are; ticker-level volatility clusters, so ±0.07 is a floor, not a guarantee. A reading of 0.60 or 0.76 is not evidence about the ticker. It is a sanity measurement, not a score, and should not be thresholded or colour-coded;
- today's `range_k` was fitted on history that includes these windows, so the number is mildly in-sample.

**Alternatives considered**
- *60 consecutive (overlapping) windows*: the shared contract's original wording; about 12 independent observations, about ±0.13. Rejected by the owner.
- *Read the full OHLCV*: what `_load_ohlcv` does today; the full history is up to about 2,700 rows per ticker for no benefit.
- *Per-date `model.predict` calls*: the model is three coefficients; a dot product over the rolling-std matrix is the same arithmetic without per-row overhead.
- *Persist per-date σ̂ in a table*: a cache with staleness rules for a 311-row computation.

### Decision 11: the artifact is JSON, written atomically, loaded once, reloaded on change

**Chosen**: `backend/data/models/har_rv_model.json`:

```
schema_version, model_version, trained_at (UTC), data_through,
features ["rv5","rv20","rv60"], intercept, coef {rv5, rv20, rv60},
target "ln(std of next 5 daily log returns)",
range_k, range_coverage,
universe {criteria, n_tickers, symbols},
n_rows,
validation {scheme, folds [{test_year, n, coverage, k}], pooled_coverage,
            pooled_coverage_ci, coverage_by_sigma_quintile,
            oot_corr, baseline_log_rv20_corr}
```

`model_version` is `har-rv-<trained date>-<first 8 hex of the SHA-256 of the canonical coefficients and `range_k`>`, so two artifacts with the same numbers have the same version; `debate-outcome-log` stores it. The training script writes a temporary file in the same directory, `fsync`s it and `os.replace`s it over the target, so a reader never sees a partial file and a failed run leaves the old artifact. `load_model()` returns an immutable `HarModel`, caches it keyed on the file's `st_mtime_ns`, re-reads only if that changed (a retrain while the server runs is picked up without a restart; a stat per request is cheap), validates `schema_version`, key presence and finiteness, and returns `None` (status `model_unavailable`) on any failure instead of raising. Serving needs only numpy; scikit-learn is used by the training script only.

Why JSON over the pickle: the model is three numbers and an intercept; JSON removes a `pickle.load` of a file from disk (listed as an untrusted-input surface in review Finding 6), the sklearn import on the first call (2.8 s cold, about 20 ms warm per call, review), the version fragility of pickled estimators, and the absence of metadata. It is also loaded lazily, so unlike the XGBoost Booster it is not a hard startup dependency (review Finding 5).

**Alternatives considered**: keep the pickle plus a sidecar JSON (two files that can disagree; still a pickle load); load in the FastAPI lifespan (a startup dependency the review just flagged on the other model); `joblib` or ONNX (heavier than three coefficients); store the version only in the filename.

### Decision 12: label, precision and Rule 2

**Chosen**: wherever the band is shown it is "typical 5-session move" with a `±` and one decimal ("±5.3%"), followed by the coverage: "about 2 in 3 recent 5-session moves stayed within this range". The phrase is generated from `range_coverage`: 0.68 renders as "about 2 in 3"; any other value renders as "about N%" with N rounded to the nearest 5, so a retrain that changes the nominal level cannot leave a wrong sentence behind. When `range_coverage` is null (`uncalibrated`) the line reads "typical 5-session move ±X.X% (coverage not established for this stock)". The API keeps two decimals; display rounds to one so the number does not imply precision the calibration does not have. The words "expected", "confidence" and "forecast" are not used for it.

Rule 2 (owner ruling, 2026-10-07: no asymmetric interval for now): `range_5s_pct` is a half-width of a log-return band read as a percent. The band `|ln(close[t+5]/close[t])| ≤ r` is the simple-return interval `(e^−r − 1, e^r − 1)`, which differs from a symmetric ±r% by less than half a point at the band sizes seen in practice (r = 10% gives +10.5% / −9.5%). Honored unchanged: the UI shows a percentage, never a raw log value, and the half-width is a volatility statistic, not a return. Displaying the asymmetric simple-return interval instead is recorded as a follow-up, not done here. The wording here is a proposal for that change's copy review; Rule 6's disclaimer is unchanged by this change.

### Decision 13: the rename has no deprecated alias

**Chosen**: `volatility_range_pct` is removed outright and replaced by `range_5s_pct` (+ `sigma_daily_pct` and, on the debate result, `range_coverage`) in `AgentPosition`, `DebateResult`, `POST /debate`, the export and the panel. `/prediction`'s copy of the field is dropped (by `retire-direction-model`, or by task 6.3 if this lands first); `/range` supersedes it.

Reason: an alias that keeps the old name with the old (daily sigma) value perpetuates the bug; an alias with the new value silently changes the numbers under a name a consumer already trusts. The only in-repo consumer is the debate panel, behind `VITE_DEBATE_PANEL_ENABLED` (off by default), updated in the same change; a loud break is cheaper than a quiet change in meaning. Historical reports on disk are not rewritten (Risks).

**Alternatives considered**: dual-publish for one release (see above); rename only the label and keep the field (the field name is what carries the misreading into code and prompts).

### Decision 14: the Technical agent's prompt states what the number is

**Chosen**: the line `Volatility range: ±{vol_range}% expected over next 5 trading sessions` (`technical.py:98`) becomes `Typical 5-session move: ±{range_5s_pct}% (about {coverage phrase} of past 5-session moves stayed within this band; daily volatility forecast {sigma_daily_pct}%)`, with an instruction that it is a size, not a direction, not a ceiling and not a prediction. For `uncalibrated` the coverage clause is replaced by "coverage not established for this stock"; when no range is served the line is `Typical 5-session move: unavailable` and the agent must not estimate one. The Technical agent obtains the band from the range service and does not re-derive eligibility or bounds. `AgentPosition` carries `range_5s_pct`, `sigma_daily_pct`, `range_coverage`; the Round 2 copy and the engine's `DebateResult` take them from Round 1.

### Decision 15: the evaluation script is read-only and is task 1

**Chosen**: `backend/scripts/evaluate_vol_range.py` opens the database with `file:...?mode=ro`, never writes a table or a model file, and prints (and with `--json` writes) coverage at ×1 and ×√5 and at the shipped or current `range_k` for: all dates in sample, non-overlapping, last 12 months, time-split refit (train before 2024, test from 2024-02), inside and outside the modelling universe, by calendar year, by sigma quintile, date-clustered mean and sd; plus the realised/predicted sigma ratio, out-of-time correlation against the `log(rv20)` baseline, and the share of windows above 7% by listing status. It is first so that the claims in this document are checkable, and it is reused in the final verification. Until the JSON artifact exists it loads the legacy pickle (task 1.2); that branch is deleted in task 8.5.

## Reproduced figures

### 2026-10-07: `evaluate_vol_range.py` against the shipped pickle (task 1.3)

Run read-only on `backend/data/app.db`, model `har_rv_model.pkl` (intercept −4.941, coefficients 9.281 / 13.773 / 14.182, identical to the review's). The script prints coverage at ×1, ×√5 and `range_k` × √5 (`range_k` here is 1.192, fitted pooled in sample because the pickle carries none).

| Slice | n | ×1 | ×√5 | review |
|---|---|---|---|---|
| all dates, modelling universe (208) | 385,909 | 32.3% | 61.0% | 32.3% / 61.0%, 385,909 |
| non-overlapping | 77,240 | 32.2% | 60.8% | 32.2% |
| last 12 months | 46,485 | 33.9% | 63.6% | 33.8% |
| time split, refit before 2024, test from 2024-02 | 130,448 | 34.8% | 64.7% | 34.8% / 64.7% |
| outside the universe | 618,586 | 53.7% | 74.7% | 53.7% / 74.7% |

- Correlation with log realised sigma on the 2024-02 test set: shipped 0.432, refit 0.432, `log(rv20)` baseline 0.423 (review: 0.431 against 0.424).
- Latest sigma per loaded ticker (last 65 closes): 592 tickers, 28 above 25%, 49 above 15%, maximum 2818% (review: 28 above 25%, 49 above 15%, MTC 2818%).
- Share of windows with sigma above 7%: delisted 13.2%, listed 0.35%.
- Realised mean sigma over mean predicted sigma: 1.171.
- Date-clustered coverage (in universe, across dates): ×1 30.9% (sd 0.199), ×√5 59.9% (sd 0.248), `range_k` × √5 67.3% (sd 0.242).
- Coverage at `range_k` = 1.192 by sigma quintile: 71.2 / 68.2 / 66.3 / 66.0 / 68.3%.

Every headline coverage is within one percentage point of the review (largest difference 0.1 point), so the change continues.

### 2026-10-07: drafting-time scratch figures, confirmed or corrected (task 1.4)

| Cited in | Drafting-time figure | Reproduced | Status |
|---|---|---|---|
| Decision 1 | 0.68-quantile of `\|r5\| / (√5 σ̂)` about 1.19 pooled | 1.192 | confirmed |
| Decision 4 | walk-forward coverage by year 2020-2026: 0.61, 0.62, 0.62, 0.73, 0.74, 0.72, 0.70, pooled 0.675; `k` 1.06-1.28 | 0.610, 0.612, 0.618, 0.728, 0.739, 0.719, 0.701, pooled 0.675; `k` 1.062, 1.154, 1.226, 1.280, 1.248, 1.214, 1.198 | confirmed |
| Decision 3 | per-ticker coverage sd about 0.05 over 207 tickers with about 130 non-overlapping windows each, "close to binomial noise (about 0.04)" | sd 0.044 over 208 tickers, but 371 non-overlapping windows each, binomial sd 0.024 | **corrected**, see Decision 3 |
| Decision 3 | coverage by sigma quintile at the pooled `k` 0.68-0.73 | 0.660-0.712 (spread 5 points) | corrected (range moves down about 2 points, spread unchanged) |
| Decision 7 | share of sigma above 7%: 0.35% listed, 13.2% delisted; 94% coverage among universe windows above 7% | 0.35%, 13.2%; 94.3% on 406 windows | confirmed |
| Decision 7 | one listed ticker's latest sigma 7.65% | not re-checked | open |
| Decision 9 | outside-universe coverage at the pooled `k`: 80.6% overall, 77.7% listed | 79.5% overall, 76.2% listed | corrected (about 1 point lower) |
| Decision 9 | about 201 listed symbols outside the universe, 192 failing the liquidity filter; 4 delisted inside | 201, 195, 4 | 192 corrected to 195 |
| Decision 6 | realised mean sigma about 17% above mean `exp(pred)` | 1.171 | confirmed |

### 2026-10-07: first walk-forward training run, task 4.3: REFUSED by the baseline gate (narrowly)

`train_har_rv.py` against the real database (208 symbols, 385,909 windows, 7 test years 2020-2026). No artifact was written and the old pickle is untouched (the refusal path works as specified).

| Test year | n | coverage | `k` | HAR corr | `log(rv20)` corr |
|---|---|---|---|---|---|
| 2020 | 48,123 | 0.614 | 1.186 | 0.323 | 0.321 |
| 2021 | 49,671 | 0.613 | 1.219 | 0.407 | 0.393 |
| 2022 | 50,789 | 0.619 | 1.234 | 0.445 | 0.456 |
| 2023 | 50,791 | 0.729 | 1.260 | 0.461 | 0.460 |
| 2024 | 51,098 | 0.741 | 1.232 | 0.409 | 0.401 |
| 2025 | 51,071 | 0.720 | 1.209 | 0.420 | 0.410 |
| 2026 | 32,767 | 0.701 | 1.196 | 0.454 | 0.454 |

- Pooled out-of-time coverage 0.676 (month-block 95% interval 0.655-0.698); by sigma quintile 0.690 / 0.670 / 0.658 / 0.658 / 0.706. **Coverage gates (a) and (b) pass** (the largest single-year distance from 0.68 is 0.067).
- **Gate (c) fails, by 0.0033**: pooled out-of-time correlation 0.4500 against 0.4533 for the `log(rv20)` baseline. The per-year columns (a scratch check, not in the artifact) show the HAR at or above the baseline in six of seven years and below it by 0.011 in 2022; the mean of the per-fold correlations is 0.417 against 0.413, and the fold-demeaned pooled correlation is 0.4035 against 0.4036. So the HAR and the baseline are indistinguishable out of time on this history, consistent with the review's 0.431 against 0.424 and with Decision 5's remark that the margin is small.
- Owner ruling 2026-10-07: gate (c) compares the mean of the per-fold correlations (Decision 5 and the spec are updated). It is a redefinition of the statistic, not a tolerance. Before the ruling: Decision 5 says a failed gate goes to the owner. Candidate readings: (1) compare within folds (HAR ahead in 6 of 7 folds and on the mean of the per-fold correlations); (2) keep the pooled test with a stated tolerance (for example 0.01); (3) drop gate (c): coverage, which is what the label claims, is gated directly, and the HAR's only role beyond `log(rv20)` is a small ranking gain. The owner chose reading (1); see the next section.
- **Correction recorded on the same day.** An earlier run of this script reported a pooled correlation of 0.373 and a far larger shortfall. That was a defect in the script, not in the data: on NumPy 2.2.6 under CPython 3.14, `range_k * SQRT5 * sigma` reused the buffer of the local array `sigma` whenever it exceeded 32,768 elements (256 KiB), so `sigma` silently became the band and the predictions were shifted by `log(range_k * sqrt 5)` per fold. Coverage was unaffected (the comparison itself was right) but the correlation and the sigma quintiles were not. The script now builds the band with `np.multiply` (`scaled_band` in `volatility.py`) and a regression test with 40,000-row folds fails on the old pattern. The same hazard applies to any `scalar * local_array` in this codebase on that interpreter and NumPy; upgrading NumPy (or running Python 3.13) removes it.

### 2026-10-07: training run under the owner's ruling, tasks 4.3, 4.4, 8.1

Gate (c) now compares the mean of the per-fold correlations (Decision 5, spec updated). `train_har_rv.py` passes every gate and wrote `backend/data/models/har_rv_model.json` (gitignored): `har-rv-2026-10-07-7200f805`, data through 2026-10-06, 208 symbols, 385,909 rows, `range_k` 1.1927, `range_coverage` 0.68, intercept -4.943, coefficients 9.280 / 13.762 / 14.232.

- Validation: same seven folds and per-fold coverage and `k` as the refused run (coverage 0.614 to 0.741, `k` 1.186 to 1.260); pooled out-of-time coverage 0.676 (month-block 95% interval 0.655-0.698); by sigma quintile 0.695 / 0.675 / 0.661 / 0.661 / 0.689 (a spread of 3.4 points); mean per-fold correlation 0.4172 against 0.4133 for `log(rv20)`.
- `evaluate_vol_range.py --model har_rv_model.json` (task 8.1): in-universe coverage at `range_k` is 68.0% (non-overlapping 68.0%, last 12 months 70.7%); by year at `range_k` 60.6% (2022) to 72.8% (2019), the same walk-forward spread as above; outside the universe 79.5% (so `uncalibrated` bands are conservative); the review's ×1 and ×√5 figures reproduce unchanged. The latest-sigma count above 25% is now 29 (was 28 in the pickle run; the final coefficients and one more session of data differ slightly).
- Task 8.2, endpoint check against the real database and artifact: VCB (in universe), AAM (listed, outside it) and AGE (delisted) all answer `ineligible` with `stale` (AGE: `delisted, stale, near_gap, hard_quality_flag`), as expected until the data is refreshed; an unknown ticker is 404. With only eligibility stubbed, VCB serves `ok` (sigma 1.13%, band 3.01%, coverage 0.68, hit-rate 0.64 over 50 windows) and AAM serves `uncalibrated` (sigma 1.82%, band 4.84%, `range_coverage` null, hit-rate 0.72 over 50). The panel and exported-report lines were checked by their tests, not in a running app.

### 2026-10-07: `/range` latency (task 8.3)

Measured through FastAPI's `TestClient` against the real database (320 MB) with a scratch artifact that carries the shipped coefficients and `range_k` 1.192, because the real artifact is blocked at task 4.3; the figures time the code path and do not depend on the coefficients.

| Path | cold (first call) | warm |
|---|---|---|
| real eligibility (VCB reads `stale`, so the endpoint answers `ineligible` after the closes read) | 72 ms | 54 ms median |
| eligibility stubbed as eligible (model cache, sigma, band, 50-window hit-rate) | | 5.0 ms median, 6.3 ms max |

- The range computation is about 5 ms warm, against about 20 ms warm for the old per-request unpickle plus full-history read (review). The first call no longer imports scikit-learn: `app.services.range` and `app.ml.volatility` import numpy and pandas only (importing `app.main` still loads scikit-learn, through `xgboost`, which the app needs for `/prediction`).
- End to end the endpoint is slower than the old figure only because it now calls `assess_eligibility`, whose `SELECT DISTINCT date FROM ohlcv` scan costs about 50 ms (the `ponytail` note in `data_eligibility.py` already says so). That cost belongs to the shared service and to `debate-data-guards`, not to this change. Re-measure once the artifact exists.

## Reconciliation notes (for the author)

- **`debate-engine` spec** (owned by `debate-data-guards`): two requirements spell the old name: "Debate engine runs three agents in parallel for Round 1" (`AgentPosition { agent_id, stance, reasoning, volatility_range_pct }`) and "Debate engine produces a structured `DebateResult` object" (the result shape). Whoever MODIFIES them must substitute `range_5s_pct`, `sigma_daily_pct`, `range_coverage`. This change states the rename once, in `volatility-range`, and does not touch `debate-engine`.
- **`debate-report-export` spec**: the existing requirement "Markdown export structure is NotebookLM-optimised" still contains the template line `**Volatility range**: ±X.X% (5 trading sessions)` and the scenario "Volatility range is omitted when unavailable". This change ADDs a requirement that supersedes both, to avoid a second MODIFIED of a requirement `align-rules-and-disclaimer` / `debate-data-guards` also edit. After archive the old text would still be present, so the reconciled MODIFIED of that requirement should replace the template line with `**Typical 5-session move**: ±X.X% (about 2 in 3 recent 5-session moves stayed within this range)` and the scenario with the one in the ADDED requirement.
- **`ticker-prediction` spec** (owned by `retire-direction-model`): the requirement "Prediction endpoint returns volatility range in addition to model output" must be REMOVED there.
- **Verdict labels, disclaimer, Rule 4 ruling**: not touched here.

## Risks / Trade-offs

- **[Coverage varies by regime]** The scratch check shows single-year coverage between about 0.61 and 0.74 at one multiplier. → "about 2 in 3" in the label, per-year spread in the artifact, a ±0.10 per-year gate, and the label never promising a guarantee.
- **[The review's numbers are unreproduced]** Decisions here rest on them. → Task 1.3 reproduces them first and stops the change if any headline figure differs by more than one percentage point.
- **[`range_hit_rate` is noisy]** About ±0.07 at n = 50 (non-overlapping windows) and a mildly in-sample `range_k`. → `n` is always returned, copy must not threshold it, spec states the limits (Decision 10).
- **[A window across a data gap is not 5 sessions]** `t+5` is a row offset, like `compute_target`. → The `near_gap` and `stale` guards in `assess_eligibility` cover recent gaps; the hit-rate inherits Rule 1's row-offset convention and does not add a calendar check.
- **[Most tickers read `ineligible` until data is refreshed]** About 21 sessions are missing (review Finding 2). → Expected; the evaluation script and verification do not depend on freshness.
- **[Old reports mislead]** The six existing files in `reports/` print `**Volatility range**: ±1.10% (5 trading sessions)` and that number is the daily sigma. They are user-local and gitignored. → Not rewritten; the owner may wish to delete them or annotate any NotebookLM copy.
- **[Retrain required]** Without `har_rv_model.json` every range is `model_unavailable`. → Migration step 1; the debate still runs with the range omitted.
- **[Hard dependency on `assess_eligibility`]** → Land `debate-data-guards` first; the range service imports one function and the tests monkeypatch it.
- **[Another multiplier to maintain]** → It is refitted on every retrain and covered by the same gates.

## Migration Plan

1. Archive order: `debate-data-guards` first (it provides `assess_eligibility`), then this change. If `retire-direction-model` has not landed, task 6.3 removes `/prediction`'s copy of the field; if it has, task 6.3 is skipped.
2. Task 1 first: preserve and run `evaluate_vol_range.py` against the current pickle; record the reproduced figures.
3. Deploy the code with the loader reading the JSON artifact; run `python backend/scripts/train_har_rv.py`; the script validates and writes `har_rv_model.json` atomically. Until then `/range` answers `model_unavailable` and the debate omits the range line (no crash).
4. Run the evaluation script against the new artifact (task 8.1); confirm pooled out-of-time coverage is near 0.68.
5. Remove the legacy `har_rv_model.pkl` by hand once the JSON artifact is in service (it is gitignored; nothing reads it afterwards).

Rollback: the previous commit still reads the pickle; a retained `.pkl` is untouched by the new training script. No database schema change.

## Open Questions

Resolved by the owner on 2026-10-07 (recorded in the Decisions above): nominal coverage stays 0.68 (Decision 2); `range_hit_rate` uses non-overlapping windows (Decision 10); `indicators_missing` does not block the range (Decision 8); no asymmetric interval for now (Decision 12); `assess_eligibility` lives in `app/services/data_eligibility.py`; `retire-direction-model` removes `/prediction`'s field and task 6.3 is conditional on it not having landed.

1. **`near_gap` and the range.** Kept as blocking (Decision 8). Revisit after the data refresh if it withholds many bands.
2. **Whether and where the panel shows `range_hit_rate`** is `align-rules-and-disclaimer`'s Rule 4 ruling; the endpoint provides it with `n`.
3. **Shared-contract deviations (additive).** The `/range` response also carries `reasons`; the debate result and `AgentPosition` also carry `range_coverage` (the panel and export need it to state the coverage without a second call); `range_hit_rate` is over non-overlapping windows (Decision 10), not the contract's "most recent ~60 windows"; `/range` ignores `indicators_missing`. `model_version` is exposed by `load_model()`, not by the API.
4. **Thresholds to confirm after task 4.3 runs on real data:** the ±0.05 / ±0.10 gates, the 7% cap and the hit-rate window limits (50 / 20) are new and unmeasured on the final artifact.

## Follow-ups (not in this change)

- **Quantile challenger**: a quantile model (for example quantile XGBoost) trained directly on `|ln(close[t+5]/close[t])|`, evaluated with the purged walk-forward helpers in `app/ml/training.py` that `retire-direction-model` keeps, against this band on out-of-time coverage and width. It would remove `range_k` and the fat-tail argument. Not decided; out of scope for every sibling.
- Log-feature HAR (review: 0.450 against 0.431), feature clipping at training, a second (90%) band with its own multiplier, and a per-sector multiplier if sector data appears.
- **Asymmetric simple-return interval** `(−a%, +b%)` for the displayed band, if Rule 2 is later read to require it (Decision 12).
