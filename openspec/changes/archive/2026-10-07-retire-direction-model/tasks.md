## 1. Evidence and baselines (before any removal)

- [x] 1.1 Write `backend/scripts/verify_retirement_claims.py` (read-only, `mode=ro`): print the `GET /tickers` catalog size using the same SQL as `CATALOG_UNIVERSE_ROWS` plus the nine `TRAINING_TICKERS`, how many are loaded and how many have `features_computed = 0`, the derived page-load count `1 + 3 x chips`, the `backtest_predictions` row, ticker and max-date counts, and the list of files that import `xgboost`; exit non-zero if the catalog is not 208 / the row count is not 10,191 / `xgboost` is imported outside the expected set (so it can be re-run after the change with different expected values via flags)
- [x] 1.2 Run it and record the output in design.md Context (expected today: 208 entries, 625 derived requests, 10,191 rows / 10 tickers / 2026-08-05)
- [x] 1.3 Baselines: backend suite on a fresh `git clone --local` (expected 1 failed, 368 passed, 1 skipped, 49 errors at e77986e) and `cd frontend && npm run test` on the working tree (rerun until it completes without worker start-up timeouts, then record file and test counts)
- [x] 1.4 Check `backend/scripts/verify_quality_gate.py` already asserts VHM's 2018-08-14 blackout (11 rows, 2018-11-16 to 2018-11-30); if not, add the known-answer check there so it can leave `test_training.py`

## 2. Backend tests first (RED)

- [x] 2.1 `tests/test_feature_rows.py`: newest row is returned and an older clean row is not substituted; a ticker with no rows returns `None`; `get_features_computed` returns `None`, `0` or `1` as stored (replaces the reusable intent of the removed `/prediction` no-walk-back and failed-features tests)
- [x] 2.2 `tests/test_tickers_api.py`: replace `test_startup_fails_when_model_file_missing` and `test_startup_loads_model_and_reuses_it_across_requests` with `test_app_boots_without_model_artifact` (empty models directory, `GET /tickers` answers 200, `app.state` has no `model`)
- [x] 2.3 `tests/test_tickers_api.py`: `test_removed_routes_are_gone` (`GET /tickers/X/prediction`, `GET /tickers/X/insight`, `POST /tickers/X/backtest` answer 404)
- [x] 2.4 `tests/test_db_init.py`: `init_db()` on a temporary database that already holds `backtest_predictions` rows leaves them unchanged; `init_db()` on a new database creates no `backtest_predictions` table
- [x] 2.5 `tests/test_training.py`: replace the two real-database tests (`..._excludes_near_gap_and_null_target_rows`, `..._excludes_blackout_rows_in_the_real_database`) with synthetic-fixture equivalents, or delete them where the existing synthetic tests already cover the invariant; confirm nothing in the suite opens `data/app.db`
- [x] 2.6 Run the new tests and confirm they fail for the right reasons

## 3. Backend removal (GREEN)

- [x] 3.1 Create `app/services/feature_rows.py` with `get_features_computed`, `get_latest_features_row` and the two SQL constants moved unchanged from `predictions.py` (its own `get_connection` import; `FEATURE_COLUMNS` from `app.ml.training`); tests from 2.1 pass
- [x] 3.2 Repoint `app/api/debate.py` and `app/services/debate/technical.py` to `app.services.feature_rows`; existing monkeypatching tests (`test_debate_export_api.py`, `test_technical_agent.py`) pass unchanged
- [x] 3.3 Fix the comments at `technical.py:26,35` that cite `app.api.insight._compute_sentiment`; leave the stance logic as is
- [x] 3.4 Remove the XGBoost load, `import xgboost`, the `MODEL_PATH` import and the `insight` and `predictions` routers from `app/main.py`
- [x] 3.5 Delete `app/api/predictions.py` and `app/api/insight.py`; delete `POST /tickers/{ticker}/backtest` and its imports from `app/api/tickers.py`
- [x] 3.6 Delete `app/ml/backtest.py`; trim `app/ml/training.py` to `TRAINING_TICKERS`, `N_FOLDS`, `TARGET_HORIZON`, `FEATURE_COLUMNS`, `filter_clean_labeled`, `compute_fold_boundaries`, `_label_dates_by_ticker`, `purge_training_rows` plus a docstring stating it holds walk-forward split helpers and no model; remove the `xgboost` import
- [x] 3.7 Remove `CREATE_BACKTEST_PREDICTIONS_TABLE` from `app/db/schema.py` and its use in `init_db()`; do not drop or alter any existing table
- [x] 3.8 Delete `tests/test_predictions_api.py`, `test_ai_insight_api.py`, `test_backtest.py`, `test_single_ticker_backtest.py`; in `test_training.py` delete `test_assemble_feature_matrix_excludes_ticker_identity` and `test_saved_model_reloads_from_disk_and_predicts` (keep purge, fold-order and clean-filter tests)
- [x] 3.9 Delete `scripts/verify_backtest_predictions.py`; trim `scripts/baseline_model_diagnostics.py` to its Finding 7 section (drop the `backtest_predictions` and booster parts and the `MODEL_PATH` and `xgboost` imports) and update its docstring
- [x] 3.10 Remove `xgboost==3.3.0` from `backend/requirements.txt`; `grep -rn "xgboost\|xgb" backend/app backend/scripts backend/tests` returns nothing
- [x] 3.11 Update the stale rationale comment at `app/services/ticker_universe.py:353-360` and the module docstring's "what the model was trained on" (the 250-session value is unchanged)
- [x] 3.12 Backend suite passes on the working tree and on a fresh `git clone --local` with no `data/models` content (zero errors from a missing model file)

## 4. Frontend tests first (RED)

- [x] 4.1 `src/api/tickers.test.js` / hook test: `fetchTickerRange` calls `GET /tickers/{ticker}/range`; `useTickerRange` is enabled only with a selected ticker
- [x] 4.2 `components/RangeDisplay/RangeDisplay.test.jsx`: unselected N/A shape; loading; available (`±X.X%`, unsigned, "Typical 5-session move", as-of, coverage words from `range_coverage`, hit-rate worded "N of the last M five-session moves" from `n`; the hit-rate appears in the card only); `range_coverage` null makes no claim; unmeasurable hit-rate; unavailable with and without `reasons`; 404; 5xx; distinct states; `sigma_daily_pct` never in the DOM; disclaimer visible beside coverage figures
- [x] 4.2b `App.test.jsx`: with a `/range` response carrying `range_hit_rate`, the hit-rate wording is present in the range card and absent from the chart panel and the debate panel
- [x] 4.3 `lib/sessionDates.test.js` (renamed from `logReturn.test.js`, conversions dropped) and a pure `rangeBand(lastClose, asOf, rangePct)` test: bounds `close x (1 +/- r/100)`, t+5 date, symmetric
- [x] 4.4 `ChartPanel.test.jsx`: mock `fetchTickerRange`; band primitive attached once for a numeric range; no valued point between last close and t+5; band cleared for null range, 404 and 5xx; legend never shows a band bound; neutral colour (not positive or negative)
- [x] 4.5 Request-budget test (`App.test.jsx`): spy on every fetcher; mount issues one call (`fetchTickers`); selecting a chip adds one `fetchTickerHistory` and one `fetchTickerRange` for that ticker only; no `/prediction`, `/insight` or `/backtest` fetcher exists
- [x] 4.6 `TickerPanel.test.jsx`: chips render with no freshness dot and no legend; chips issue no query; refresh and search-load invalidate tickers, history and range (rewrite `:685`, `:710` and `useLoadTicker.test.jsx:76`); keep "Loaded Nd ago" and Refresh tests
- [x] 4.7 `App.test.jsx`: `DebatePanel` renders with no env var set and no Confidence, Advice or Backtest element exists; keep the disclaimer-visibility and no-leftover-controls assertions
- [x] 4.8 Run the new tests and confirm they fail for the right reasons

## 5. Frontend removal and range display (GREEN)

- [x] 5.1 Delete `components/PredictionDisplay/`, `components/AIInsightPanel/`, `hooks/useBacktestTicker.js`, `hooks/useTickerPrediction.js`, `hooks/useTickerInsight.js`, `hooks/useTickerFreshness.js`
- [x] 5.2 `api/tickers.js`: delete `fetchTickerPrediction`, `fetchTickerInsight`, `backtestTicker`; add `fetchTickerRange`; replace the dangling `import('./types').DebateResult` with a local `@typedef DebateResult` of the fields the backend serialises today; update the file header comment
- [x] 5.3 `lib/queryClient.js`: remove `prediction` and `insight` keys, add `range`; `hooks/useTickerRange.js`; `hooks/useLoadTicker.js` and `TickerPanel.jsx` invalidate tickers, history and range
- [x] 5.4 Chart band: rename `lib/logReturn.js` to `lib/sessionDates.js` keeping `approximateTargetDate` and `intermediateSessionDates` and deleting the conversions; add `rangeBand`; in `ChartPanel.jsx` replace the prediction line series with a whitespace-only series carrying a series primitive that draws the dashed bounds and light fill at t+5 and reports `autoscaleInfo`; if the primitive proves unworkable record the fallback chosen (two dashed bound lines without fill) in design.md Decision 12
- [x] 5.5 `components/RangeDisplay/RangeDisplay.jsx` and `range-display.css` (reuse the placeholder styling rule from the deleted card); import the disclaimer constant from `frontend/src/lib/disclaimer.js`, which `align-rules-and-disclaimer` owns together with its drift test against `docs/DISCLAIMER.md` (if this change lands first, add a one-line placeholder export that change then replaces; `DebatePanel` is not edited here)
- [x] 5.6 `TickerChip.jsx`: remove `useTickerFreshness`, `useTickerInsight`, `FRESHNESS_DESCRIPTION`, the dot, `data-freshness` and `effectiveFreshness`; keep "Loaded Nd ago", the Refresh icon and its spinning state, and the "Feature computation failed" footer. `TickerPanel.jsx`: remove the legend. `ticker-panel.css`: remove the dot, legend and `data-freshness` rules (keep `ticker-chip-spin`, still used by the Refresh icon)
- [x] 5.7 `App.jsx`: render `RangeDisplay` and the `DebatePanel` unconditionally, remove the flag and its comment; `DebatePanel.jsx`: delete the "Feature flag" doc line only (labels and range line belong to sibling changes)
- [x] 5.8 In a browser against a running app (after `calibrate-volatility-range` is in): count network requests on load and after selecting a ticker (expected 1, then 3 in total), eyeball the band (dashed bounds, light fill, symmetric, neutral, inside the price scale on a low-volatility and a high-volatility ticker, light and dark theme), and compare with the pre-change count from 1.3 run on the old tree (a Playwright script saved under `frontend/` is not required; record the numbers in design.md)
- [x] 5.9 Frontend suite and `npm run lint` pass; `npm run build` succeeds

## 6. Configuration, docs hand-off and stale text

- [x] 6.1 Do not edit any `frontend/.env*` file (owner instruction); they still name `VITE_DEBATE_PANEL_ENABLED`, which nothing reads after 5.7. Note in the final report that they are tracked and should be checked for non-public values
- [x] 6.2 `README.md`: delete the "behind a feature flag" instructions; add the step `python backend/scripts/train_har_rv.py` (a fresh clone has no HAR model, so no range is served until it runs)
- [x] 6.3 Sweep stale comments naming the removed pieces: `TickerPanel.jsx` header, `hooks/useTickers.js`, `hooks/useSearchedTickers.js`, `lib/queryClient.js`, `ChartPanel.jsx` comments about the predicted point
- [x] 6.4 Hand-off list for `align-rules-and-disclaimer` (do not edit these here): `MODEL_CARD.md` retirement note, `DATA_DICTIONARY.md` (`backtest_predictions` legacy, no longer created), `DISCUSSION_calendar_staleness.md` (resolved by removal, Decision 9), `KNOWN_ISSUES.md` (`filter_clean_labeled` and `/prediction` gating text), `config.yaml` and `CLAUDE.md` (Rules 3 and 4 have no implementation)
- [x] 6.5 Tell `calibrate-volatility-range` that the `technical-agent` sentence citing `insight.py` needs rewording (design.md Open Question 2)

## 7. Verification

- [x] 7.1 Re-run `scripts/verify_retirement_claims.py` with the post-change expectations (no importer of `xgboost`; `backtest_predictions` still 10,191 rows; catalog still 208)
- [x] 7.2 Grep for dead references returns nothing in `frontend/src` and `backend/`: `prediction`, `insight`, `backtest`, `Confidence`, `useTickerFreshness`, `FRESHNESS`, `DEBATE_PANEL_ENABLED`, `logReturnToPercent`, `app.state.model`
- [x] 7.3 Fresh-clone check: `git clone --local`, install requirements without `xgboost`, run `pytest backend/tests` (no error from a missing artifact) and start the backend; `GET /tickers` answers
- [x] 7.4 Confirm no data was changed: `backtest_predictions` count and max date equal the baseline, and `pooled_xgb_model.json` still on disk. The baseline is 10,240 rows / max date 2026-09-25, not the 1.2 record (10,191 / 2026-08-05): the owner confirmed the extra 49 VIB rows came from the old "Backtest this ticker" action used during the session (design.md, Implementation record). The model file is intact.
- [x] 7.5 Page-load request count measured in a browser (task 5.8) is recorded and compared with the 625 derived and about 1,800 reviewed figures
- [x] 7.6 Archive dry run: copy `openspec/specs`, `openspec/config.yaml` and this change into a scratch directory and run `openspec archive retire-direction-model --yes` there (never in the repository); confirm it archives with the stub-bearing `ticker-prediction` and no scenario-drop error, and re-run it after any edit to the delta specs or after a sibling change that touches `dashboard-ui` lands (a first run before the stub was added aborted: see design.md Decision 17 and Open Question 6)
- [x] 7.7 `openspec validate retire-direction-model` passes; confirm ordering against `calibrate-volatility-range` and `debate-data-guards` before archive
