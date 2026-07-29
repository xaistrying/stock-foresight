## Why

M1 leaves `ohlcv` as raw `(ticker, date, open, high, low, close, volume)` rows.
The M3 XGBoost pipeline needs engineered technical-analysis features and the
target variable computed and persisted before training can start. Nothing
downstream of M1 currently exists to turn raw OHLCV into a model-ready feature
table, so M3 is blocked until this exists.

## What Changes

- Add a feature computation pipeline that reads `ohlcv` and produces one row
  per `(ticker, date)` with: Ichimoku components, RSI, MACD, Bollinger Bands,
  ATR, OBV, the `target_t = ln(close[t+5] / close[t])` label (Rule 1), and a
  `near_gap` boolean flagging rows within each indicator's warm-up window of
  an advisory gap (per M1's gap-detection log) or the start of a ticker's
  series.
- Persist engineered features to a new SQLite table (`features`), upserted
  per `(ticker, date)`, separate from `ohlcv` so `ohlcv` stays a raw-data
  table per M1's spec.
- Document the new table, indicator parameters, warm-up windows, and
  `near_gap` semantics in `docs/DATA_DICTIONARY.md` (already exists since M1).
- No UI, no API endpoints, no training — this is the feature table only.
  M2 output is consumed by M3 (training) and M4 (serving), not built here.

## Capabilities

### New Capabilities
- `feature-engineering`: computes and persists technical-analysis indicators,
  the prediction target, and gap-aware quality flags from `ohlcv` into a new
  `features` table.

### Modified Capabilities
(none — `ticker-data-ingestion` and its `ohlcv`/`tickers` schema are
untouched; this change only reads from `ohlcv`)

## Impact

- **New code**: `backend/app/ml/` (or `backend/app/services/`) feature
  computation module; new `backend/app/db/schema.py` table (`features`).
- **Domain rules touched**:
  - **Rule 1** (target = `ln(close[t+5]/close[t])`, 5 trading sessions):
    honored unchanged — this is where the target column is first computed
    and persisted.
  - **Rule 3** (volatility-relative advice threshold, `0.5 x
    rolling_std(returns, 60)`): not implemented here (that's M6's advice
    logic), but this change computes ATR and Bollinger width, which are a
    *different* volatility measure than the rolling return std rule 3
    specifies. Design.md documents these as intentionally distinct
    quantities — ATR/Bollinger are model *features*, rolling_std(returns,60)
    is the *advice-threshold* calculation — not the same number reused.
  - **Rule 5** (Market Sentiment = technical proxy, not real sentiment):
    not implemented here (that's M6's UI), but RSI/MACD/Ichimoku computed in
    this change are the inputs that rule 5's sentiment proxy will read from
    later. No UI labeling concern yet since M2 has no UI surface.
  - Rules 2, 4, 6 are not touched by this change (no UI, no confidence
    score, no advice text is produced at the feature-engineering stage).
- **Dependencies**: reads `backend/app/db/schema.py` `ohlcv` table (M1).
  No new third-party packages assumed yet — indicator computation library
  choice (hand-rolled vs. `pandas-ta`/`ta`) is a design decision, not
  proposed here.
- **Docs**: `docs/DATA_DICTIONARY.md` gets a new section for the `features`
  table.
