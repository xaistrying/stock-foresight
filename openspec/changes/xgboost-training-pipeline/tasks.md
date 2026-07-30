## 1. Setup

- [ ] 1.1 Add `xgboost` and `scikit-learn` (or equivalent split/metrics
      utilities) to `backend/requirements.txt`; reinstall and verify
      import works in the backend venv.
- [ ] 1.2 Create `backend/data/models/` directory; add it to
      `backend/.gitignore` (matches `backend/data/app.db`'s existing
      not-checked-in pattern).
- [ ] 1.3 Confirm all 9 training tickers (TCB, VIB, VHM, VND, MWG, HPG,
      MSN, VNM, SAB) are loaded in `ohlcv`/`features` (they are, per
      `screen_ticker_volatility.py`'s prior run) — no new ingestion code;
      if any are missing at implementation time, load via the existing
      `POST /tickers/{ticker}/load` endpoint, not a new script.

## 2. Data loading and filtering

- [ ] 2.1 Implement a function that reads `features` rows for the 9 named
      tickers from SQLite.
- [ ] 2.2 Filter to `near_gap = 0 AND target IS NOT NULL` ("clean+labeled"
      rows) per design.md Decision 2.
- [ ] 2.3 Assemble the model input feature matrix from the existing
      indicator columns only (Ichimoku, RSI, MACD, Bollinger, ATR, OBV) —
      explicitly exclude `ticker` and any ticker-derived column, per
      design.md Decision 3.
- [ ] 2.4 Add a data-loading test asserting the ticker column (and any
      ticker-identity encoding) is absent from the assembled feature
      matrix.
- [ ] 2.5 Add a data-loading test asserting no row with `near_gap = 1` or
      null `target` appears in the loaded set, using the current sqlite
      data (~11,480 expected clean+labeled rows pooled across all 9
      tickers — assert row count is in a sane range, not an exact literal,
      since ticker histories grow over time).

## 3. Walk-forward split

- [ ] 3.1 Implement pooled fold-boundary computation: shared calendar-date
      cutoffs across all 9 tickers, expanding training window, 4-6 folds
      (design.md Decision 4).
- [ ] 3.2 Implement the training-side purge: for each fold boundary at
      date T, exclude any training row whose target label date (t+5
      sessions, per Rule 1) falls at or after T — purge width is
      `TARGET_HORIZON = 5` rows per ticker immediately before the boundary
      (positions T-5 through T-1 inclusive; row T-5's label reads close[T],
      the test set's first value, so it must be excluded too, not just the
      4 rows closest to the boundary).
- [ ] 3.3 Add a leakage guard test: assert that for every fold, no
      training row's underlying `close[t+5]` date is `>= ` that fold's
      test start date.
- [ ] 3.4 Add a test confirming folds are NOT constructed via random
      shuffling — e.g. assert row dates within each fold's train/test
      split are monotonically non-decreasing per ticker.

## 4. Model training

- [ ] 4.1 Implement the XGBoost training function with a fixed,
      documented conservative hyperparameter configuration (shallow
      `max_depth`, early stopping against a validation fold, subsample/
      colsample_bytree < 1.0, `min_child_weight` above library default) —
      per design.md Decision 5. No hyperparameter search.
- [ ] 4.2 Train the final pooled model on the full clean+labeled dataset
      (all folds' data, following the same purge discipline against the
      most recent held-out period) and persist the resulting model
      artifact to `backend/data/models/`.
- [ ] 4.3 Add a test that a trained model artifact can be reloaded from
      disk and produce a prediction for a sample feature row.

## 5. Backtest evaluation

- [ ] 5.1 For each walk-forward fold, train on that fold's (purged)
      training set and predict on its held-out test set, collecting
      out-of-fold predictions across all folds.
- [ ] 5.2 Implement the hit-rate calculation: `sign(predicted) ==
      sign(actual)` is a hit; `actual == 0` is always a miss regardless of
      predicted sign (design.md Decision 6).
- [ ] 5.3 Implement standard regression error metrics (MAE, RMSE) on the
      log-return target, per fold and pooled, for the Model Card — no
      simulated P&L/trading-return metric (design.md Non-Goals).
- [ ] 5.4 Add a test for the hit-rate function covering: matching-sign
      hit, opposite-sign miss, and `actual == 0` miss regardless of
      predicted sign.

## 6. Backtest results persistence

- [ ] 6.1 Decide and implement the persistence mechanism for out-of-fold
      predictions (new SQLite table, e.g. `backtest_predictions`, or a
      results file) — must support, per ticker, retrieving predictions
      ordered by date and computing a rolling hit-rate over the most
      recent ~60.
- [ ] 6.2 If using a new SQLite table: add its `CREATE TABLE` to
      `backend/app/db/schema.py` alongside the existing `ohlcv`/`tickers`/
      `features` tables.
- [ ] 6.3 Implement a function to compute a given ticker's hit-rate over
      its most recent ~60 persisted backtested predictions (this is the
      value Rule 4's confidence score will read from in a future
      milestone — not wired into any API/UI in this change).
- [ ] 6.4 Add a test verifying the rolling hit-rate function returns a
      correct value against a small synthetic set of persisted
      predictions with known hits/misses.

## 7. Documentation

- [ ] 7.1 Create `docs/MODEL_CARD.md` documenting: training data (9
      tickers, row counts, date ranges), features used (list, referencing
      `docs/DATA_DICTIONARY.md` for definitions), the walk-forward split
      methodology (fold count, purge gap, expanding-window choice),
      hyperparameters used, the hit-rate definition (including the
      zero-actual-target edge case), and backtest results (per-ticker and
      pooled hit-rate, MAE/RMSE) — framed as technical observation, not
      investment performance (Rule 6).
- [ ] 7.2 Document, in `docs/MODEL_CARD.md`, the known blind spot from
      design.md Decision 2: excluding `near_gap` rows removes the
      recurring post-Tet-holiday period every year across all tickers: the
      model is neither trained nor backtested on this period.
- [ ] 7.3 Update `openspec/config.yaml`'s milestone status line to mark M3
      complete once this change is fully implemented and archived.

## 8. Verification

- [ ] 8.1 Run the full test suite (`pytest backend/tests`) and confirm all
      new and existing tests pass.
- [ ] 8.2 Run the training + backtest pipeline end-to-end against the
      current `app.db` and manually inspect: pooled hit-rate is
      meaningfully different from 50% in either direction (a ~50% result
      on a directional binary outcome would suggest the model has learned
      nothing beyond chance, worth flagging in the Model Card either way,
      not silently reported as success).
- [ ] 8.3 Confirm no code in this change frames results as investment
      advice, predicted returns, or performance guarantees (Rule 6) —
      spot-check `docs/MODEL_CARD.md` language specifically.
