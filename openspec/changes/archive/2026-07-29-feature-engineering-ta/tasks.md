## 1. Schema

- [x] 1.1 Add `CREATE_FEATURES_TABLE` to `backend/app/db/schema.py`: `features`
      table keyed `(ticker, date)` with columns for Ichimoku components,
      RSI, MACD, Bollinger Bands, ATR, OBV, `target`, `near_gap`
      (boolean/integer), and `computed_at` (timestamp, per design
      Decision 8), foreign-keyed conceptually to `ohlcv` on
      `(ticker, date)`.
- [x] 1.2 Wire the new table creation into whatever calls
      `CREATE_OHLCV_TABLE`/`CREATE_TICKERS_TABLE` today (e.g. app startup /
      DB init path) so `features` is created alongside the existing tables.

## 2. Indicator computation

- [x] 2.1 Choose and add an indicator computation approach (hand-rolled or a
      library such as `pandas-ta`) to `backend/requirements.txt` if a new
      dependency is introduced; document the choice.
- [x] 2.2 Implement Ichimoku: Tenkan-sen, Kijun-sen (no shift); Senkou Span
      A/B using the standard forward-shifted convention per design
      Decision 6 (computed from data as of date-26, stored against the
      current row); `chikou_signal` (current close vs. close 26 sessions
      ago) per design Decision 6 — do NOT implement a literal
      backward-shifted Chikou value; it requires future data and leaks
      into the feature row.
- [x] 2.3 Implement RSI, period 14 (design Decision 7 default).
- [x] 2.4 Implement MACD, periods 12/26/9 (design Decision 7 default).
- [x] 2.5 Implement Bollinger Bands (upper/mid/lower, or width) with
      explicit period and standard-deviation multiplier.
- [x] 2.6 Implement ATR, period 14 (design Decision 7 default).
- [x] 2.7 Implement OBV.
- [x] 2.8 Ensure all indicator computation is scoped per-ticker (no
      cross-ticker leakage) — process `ohlcv` grouped/sorted by
      `(ticker, date)`.

## 3. Target variable

- [x] 3.1 Compute `target = ln(close[t+5] / close[t])` per Rule 1, using
      5 trading sessions (row offset within the ticker's stored sequence),
      not a calendar-day lookahead.
- [x] 3.2 Leave `target` null for the last 5 stored sessions of each ticker
      (insufficient future data), and confirm the row is still written with
      feature columns populated.

## 4. Gap-aware quality flag

- [x] 4.1 Reuse or re-derive M1's gap-detection logic (session-to-session
      distance > 5 calendar days) against `ohlcv` per ticker.
- [x] 4.2 For each row, determine the longest indicator lookback window used
      in that row's computation (Ichimoku's Senkou Span B is expected to be
      longest) and check whether any input date in that window crosses a
      detected gap or precedes the ticker's first stored session.
- [x] 4.3 Set `near_gap = 1` when true, `0` otherwise; confirm indicator
      values are still computed and written regardless of `near_gap`.

## 5. Persistence

- [x] 5.1 Implement upsert (`ON CONFLICT(ticker, date) DO UPDATE`) into
      `features`, matching the upsert pattern used for `ohlcv`/`tickers` in
      `backend/app/services/ticker_ingestion.py`; set `computed_at` to the
      current timestamp on every upsert (design Decision 8).
- [x] 5.2 Add a function/entry point to (re)compute and upsert features
      for a given ticker. Per design Decision 5: recomputes the entire
      per-ticker `features` series from the earliest stored `ohlcv` row
      every time (not incremental) — required for OBV's correctness,
      applied uniformly across all indicators.
- [x] 5.3 Wire `recompute_features_for_ticker(ticker)` into `load_ticker()`,
      called after the ohlcv/tickers upsert commits. NOT in the original
      task list — added during implementation verification (design
      Decision 9).

## 6. Documentation

- [x] 6.1 Add a `features` table section to `docs/DATA_DICTIONARY.md`:
      column list, each indicator's parameters and warm-up window length,
      the target formula (Rule 1), and `near_gap` semantics (advisory flag,
      not a filter — mirrors M1's gap-detection posture).

## 7. Tests

- [x] 7.1 Unit tests for each indicator against known reference values
      (e.g. a small fixture series with hand-computed expected RSI/MACD/
      Bollinger/ATR/OBV/Ichimoku outputs).
- [x] 7.2 Test `target` computation: correct log-return value when 5 future
      sessions exist, null when they don't.
- [x] 7.3 Test `near_gap` flagging: rows within a lookback window of an
      injected gap are flagged `1`; rows with clean history are `0`; rows
      near the start of a short/tier-truncated series are flagged `1`.
- [x] 7.4 Test upsert idempotency: re-running feature computation for a
      ticker updates existing `(ticker, date)` rows without duplicating them.
- [x] 7.5 Test OBV correctness after a ticker reload adds new rows:
      re-running feature computation must update OBV for ALL existing
      rows consistently, not just append new ones (guards design
      Decision 5).
- [x] 7.6 Test that no Ichimoku-derived column at row (ticker, D) is
      computed from any `ohlcv` row dated after D — guards the Chikou
      leakage bug specifically (assert on construction/inputs, not just
      output values).
- [x] 7.7 Integration test: `POST /tickers/{ticker}/load` triggers feature
      computation as a side effect (mock `recompute_features_for_ticker`,
      assert called with correct ticker). Separately: a
      `recompute_features_for_ticker` failure must not propagate as a
      failed load — response should show `features_computed=false` with
      `rows_loaded` still populated (guards design Decision 9's failure
      handling).