# Model Card: Pooled XGBoost Regressor (M3)

Documents the first-pass model trained by
`openspec/changes/xgboost-training-pipeline/`: `backend/app/ml/training.py`
and `backend/app/ml/backtest.py`. Design rationale:
`openspec/changes/xgboost-training-pipeline/design.md`.

This is a first pass proving the pipeline (features -> training ->
walk-forward backtest -> persisted model) works end-to-end, not a tuned or
final model. All results below are **technical observations from a
walk-forward backtest** — directional accuracy and standard regression
error metrics only. They are not investment advice, predicted returns, or a
performance guarantee (Rule 6), and there is no simulated P&L/trading-return
layer in this pipeline by design.

## Training data

- **Tickers (9, fixed set)**: TCB, VIB, VHM, VND, MWG, HPG, MSN, VNM, SAB —
  selected by empirical realized-volatility/stale-price screening, not
  sector-label assumption (design.md Decision 1).
- **Row filtering**: `features` rows with `near_gap = 0 AND target IS NOT
  NULL` only ("clean+labeled" rows, design.md Decision 2). See
  [Known blind spot](#known-blind-spot-post-tet-holiday-period-excluded)
  below.
- **Clean+labeled row counts and date ranges** (current `app.db`, will grow
  as more history accumulates):

  | Ticker | Rows | Date range |
  | --- | --- | --- |
  | TCB | 1292 | 2018-11-16 to 2026-07-22 |
  | VIB | 1232 | 2018-11-15 to 2026-07-20 |
  | VHM | 1292 | 2018-11-16 to 2026-07-22 |
  | VND | 1204 | 2018-11-16 to 2026-07-22 |
  | MWG | 1292 | 2018-11-16 to 2026-07-22 |
  | HPG | 1292 | 2018-11-16 to 2026-07-22 |
  | MSN | 1292 | 2018-11-16 to 2026-07-22 |
  | VNM | 1292 | 2018-11-16 to 2026-07-22 |
  | SAB | 1292 | 2018-11-16 to 2026-07-22 |
  | **Pooled** | **11,480** | 2018-11-15 to 2026-07-22 |

## Features

Pure OHLCV-derived indicator columns only — no ticker identity, one-hot
encoding, or per-ticker target encoding (design.md Decision 3). Definitions:
`docs/DATA_DICTIONARY.md` (`features` table).

`tenkan_sen`, `kijun_sen`, `senkou_span_a`, `senkou_span_b`, `chikou_signal`,
`rsi`, `macd_line`, `macd_signal`, `macd_histogram`, `bb_upper`, `bb_middle`,
`bb_lower`, `atr`, `obv` (14 columns).

Target: `target_t = ln(close[t+5] / close[t])` — log return, 5 trading
sessions ahead (Rule 1).

## Split methodology

Leakage-safe pooled walk-forward validation (design.md Decision 4):

- **Pooled fold boundaries**: shared calendar-date cutoffs across all 9
  tickers, not independent per-ticker boundaries.
- **Expanding window**: each successive fold's training set includes all
  prior folds' data, never a fixed-width sliding window.
- **5 conceptual chunks -> 4 boundaries -> 4 test folds.** The first chunk
  has no prior data to validate against and serves purely as initial
  training history; folds 0-3 below are the 4 walk-forward test windows.
- **Explicit purge gap**: for each fold boundary at date `T`, training rows
  at ticker-relative positions `T-5` through `T-1` are excluded, since
  `target`'s 5-session horizon means even row `T-5`'s label reads
  `close[T]` — the test set's first value (design.md Decision 4).
- **No shuffled k-fold** — rejected outright as a leakage risk given the
  forward-looking target.

Fold boundaries (current data): `2020-07-17`, `2021-10-12`, `2023-01-06`,
`2024-11-19`.

## Hyperparameters

Fixed, conservative, untuned configuration (design.md Decision 5) — no
hyperparameter search was performed:

| Parameter | Value |
| --- | --- |
| `objective` | `reg:squarederror` |
| `max_depth` | 3 |
| `eta` (learning rate) | 0.05 |
| `subsample` | 0.8 |
| `colsample_bytree` | 0.8 |
| `min_child_weight` | 5 |
| `seed` | 0 |
| `num_boost_round` (max) | 500 |
| `early_stopping_rounds` | 20 |

Early stopping is evaluated against a held-out validation fold; the actual
number of boosting rounds used is determined by early stopping, not fixed
in advance. The final persisted model (trained on the full clean+labeled
dataset, purged against the most recent fold boundary) stopped at
iteration 81.

## Hit-rate definition

A prediction is a **hit** if `sign(predicted_target) == sign(actual_target)`
— directional accuracy only, no magnitude/interval matching (design.md
Decision 6, implementing Rule 4).

**Zero-crossing edge case**: when `actual_target == 0` exactly, sign is
undefined; this is always recorded as a **miss**, regardless of the
predicted value's sign.

Rolling hit-rate for a ticker = fraction of hits over that ticker's most
recent ~60 out-of-fold (backtested) predictions — this is the value M6's
confidence score (Rule 4) reads.

## Backtest results

All figures below are from the walk-forward backtest's out-of-fold
predictions only (9,157 pooled predictions across 4 folds) — never
in-sample. No simulated trading return, P&L, or win-rate-in-currency-terms
figure is computed or reported anywhere in this pipeline.

### Pooled

- **Hit-rate**: 47.8% (0.4778) over 9,157 out-of-fold predictions.
- **MAE**: 0.0362 (log-return units).
- **RMSE**: 0.0512 (log-return units).

A ~50% hit-rate on this directional binary outcome is worth flagging
explicitly, not silently reported as a success: pooled across all folds,
this model's out-of-fold directional accuracy is statistically close to a
coin flip. See [Interpretation](#interpretation) below.

### Per fold

| Fold | Test date range | n | Hit-rate | MAE | RMSE |
| --- | --- | --- | --- | --- | --- |
| 0 | 2020-07-17 to 2021-10-11 | 2227 | 42.2% | 0.0380 | 0.0525 |
| 1 | 2021-10-12 to 2023-01-05 | 2279 | 45.5% | 0.0427 | 0.0615 |
| 2 | 2023-01-06 to 2024-11-18 | 2322 | 50.1% | 0.0325 | 0.0439 |
| 3 | 2024-11-19 to 2026-07-22 | 2329 | 53.0% | 0.0320 | 0.0453 |
| Pooled | — | 9157 | 47.8% | 0.0362 | 0.0512 |

Hit-rate trends upward across folds (42.2% -> 53.0%) as the expanding
training window grows; error metrics improve similarly. Whether this
reflects the model benefiting from more training data, or a change in
market regime across the ~6-year test span, cannot be distinguished from
this backtest alone.

### Per ticker (pooled across all folds)

| Ticker | n | Hit-rate |
| --- | --- | --- |
| HPG | 1034 | 44.5% |
| MSN | 1034 | 49.2% |
| MWG | 1034 | 45.3% |
| SAB | 1034 | 47.8% |
| TCB | 1034 | 47.8% |
| VHM | 1034 | 49.4% |
| VIB | 973 | 48.3% |
| VND | 946 | 49.7% |
| VNM | 1034 | 48.1% |

No ticker's pooled hit-rate is materially above 50%; all sit within a
roughly 44.5%-49.7% band.

### Most recent ~60 predictions per ticker (Rule 4 confidence-score basis)

For reference, the rolling hit-rate each ticker's confidence score would
currently read (computed the same way M6 will consume it — not wired into
any API/UI in this change):

| Ticker | Rolling hit-rate (last ~60) |
| --- | --- |
| TCB | 55.0% |
| VIB | 65.0% |
| VHM | 53.3% |
| VND | 63.3% |
| MWG | 63.3% |
| HPG | 53.3% |
| MSN | 60.0% |
| VNM | 65.0% |
| SAB | 51.7% |

These are higher than the pooled 47.8% figure above because they're drawn
from fold 3 (the most recent, best-performing test window) rather than the
full backtest history — expected given fold 3's own 53.0% hit-rate, and a
reminder that this rolling window will shift as new predictions are
recorded over time; it is not a stable, permanent number.

### Interpretation

Pooled out-of-fold hit-rate (47.8%) is statistically indistinguishable from
chance on this first-pass, untuned pipeline — this is a genuine technical
observation, not something to gloss over. Later folds show directional
accuracy meaningfully above 50%, which may reflect the expanding window
providing more training data over time, changing market conditions, or
noise from a modest number of folds; this backtest cannot distinguish
between those explanations. No conclusion about the model's real-world
predictive value should be drawn from a single first-pass, untuned training
run — this Model Card documents what was measured, not a recommendation to
rely on these predictions.

## Known blind spot: post-Tet holiday period excluded

Excluding `near_gap = 1` rows (design.md Decision 2) removes ~35-39% of
otherwise-available rows, concentrated in bands following each recurring
HOSE exchange holiday closure — consistent with the ~2-3 month period
following Lunar New Year (Tet) each year, not randomly distributed through
the calendar. This is driven by `near_gap` triggering on the single longest
indicator lookback (Senkou Span B's 78-row window), so one ~1-week annual
exchange closure gets amplified into a ~78-session exclusion band, applied
uniformly even to indicators with much shorter windows (RSI/ATR: 14-15
rows, MACD: 34, Bollinger: 20).

**Consequence**: this model is neither trained nor backtested on the
recurring post-Tet period each year. If Vietnamese equities exhibit a
distinct volume/volatility regime in that window, this pipeline has no
evidence about how the model performs there. Not fixed in this change; a
per-column reliability flag (rather than one blanket `near_gap` per row)
is a possible future lever if this blind spot becomes a real concern, but
adds real complexity not attempted here.

## Persistence

- **Model artifact**: `backend/data/models/pooled_xgb_model.json`
  (XGBoost's native booster JSON format), gitignored — matches
  `backend/data/app.db`'s existing not-checked-in pattern.
- **Backtest results**: `backtest_predictions` SQLite table (one row per
  out-of-fold `(ticker, date)` prediction, with `fold`, `predicted`,
  `actual`, and precomputed `hit`), queryable per ticker ordered by date —
  supports the rolling ~60-prediction hit-rate M6 will read.

## Scope and non-goals

- No hyperparameter tuning — conservative, untuned defaults only. A future
  iteration once this pipeline is proven.
- No ticker-identity feature — deferred until enough tickers exist for a
  meaningful held-out-ticker generalization test (design.md Decision 3).
- No simulated trading returns or P&L — directional accuracy and standard
  regression error metrics only, to avoid any framing implying realized
  investment performance (Rule 6).
- All 9 tickers are large-cap, liquid VN30 constituents — this model and
  backtest are unvalidated on small/mid-cap or recently-listed tickers.
- No FastAPI prediction endpoints or UI — this change stops at a persisted
  model, persisted backtest results, and this document.
