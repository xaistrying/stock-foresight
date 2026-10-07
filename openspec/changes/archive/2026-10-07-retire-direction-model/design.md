## Context

`multi-agent-debate-analyst` (archived 2026-10-05) retired the XGBoost direction model "from the live serving path" but left it in place: its Decision "Option 1 (do nothing to XGBoost direction) for the retired endpoint" kept `/prediction`, `/insight`, the startup load and the old panel behind a flag, with removal deferred to "a later change". The 2026-10-06 review (`docs/DISCUSSION_post_pivot_review.md`, Finding 5) lists what that left behind. Its numbers are the reviewers' measurements. This change re-checked every item it relies on against commit e77986e (the uncommitted debate edits are committed) and read-only against `backend/data/app.db`:

| Review claim | Re-checked | Result |
| --- | --- | --- |
| `main.py:33-34` loads the booster; the model file is gitignored; a fresh clone cannot start | Code read; `git clone --local` of e77986e into a scratch directory, project venv, `pytest backend/tests` | Confirmed: 1 failed, 368 passed, 1 skipped, 49 errors. Every error is an `XGBoostError` from the lifespan load in a `TestClient(app)` test. The failure is the real-database test `test_filter_clean_labeled_excludes_near_gap_and_null_target_rows` (the second real-database test skips) |
| Page load makes about 1 + 3 x 599 = 1,800 requests | `GET /tickers` SQL (`CATALOG_UNIVERSE_ROWS`) run read-only; `TickerPanel.jsx:34`, `TickerChip.jsx` | **Corrected.** The catalog has 208 entries (204 listed, 4 delisted), all loaded, none with `features_computed = 0`. Each chip fires 3 requests, so 1 + 3 x 208 = **625** (derived from code, not measured in a browser). 599 is the row count of `tickers`; the other 391 loaded symbols fail the liquidity or history filter and are not rendered |
| "229 of the loaded symbols are delisted" | `ticker_universe`, `tickers` | **Corrected.** 229 is the delisted count in `ticker_universe` (which includes 35 `no_data` symbols); among the 599 loaded it is 194; among the 208 catalog entries (the rendered Watchlist) it is 4 |
| `backtest_predictions`: 10,191 rows, 10 tickers, last date 2026-08-05 | Read-only query | Confirmed |
| `baseline_model_diagnostics.py` is dead | Docstring and imports read | **Partly.** Findings 1 and 2 (backtest table, booster importance) are model-specific; Finding 7 (cross-ticker return correlation and portfolio-volatility understatement) reads only OHLCV and feeds the undecided "portfolio risk" option |
| `get_latest_features_row` / `get_features_computed` are imported by `debate.py` and `technical.py` | grep | Confirmed (`debate.py:21`, `technical.py:19`); `insight.py` also imports them |
| The tests that encode old behaviour (frontend) | Test names listed | Confirmed and enumerated in the replacement table below |

**Evidence recorded at implementation (2026-10-07, `backend/scripts/verify_retirement_claims.py`, read-only):** catalog 208 entries, all loaded, 0 with `features_computed = 0`; derived page-load requests 1 + 3 x 208 = 625; `backtest_predictions` 10,191 rows / 10 tickers / max date 2026-08-05; files importing `xgboost`: `app/api/insight.py`, `app/api/predictions.py`, `app/main.py`, `app/ml/backtest.py`, `app/ml/training.py`, `scripts/baseline_model_diagnostics.py`, `tests/test_training.py`. **Baselines:** backend on a fresh `git clone --local` of e77986e: 1 failed, 368 passed, 1 skipped, 49 errors (63 s); frontend on the working tree: 17 files, 265 tests passed, no worker start-up timeouts (29 s). `scripts/verify_quality_gate.py` did not assert VHM's blackout; task 1.4 added it (11 rows, 2018-11-16 to 2018-11-30; passes). Its separate, pre-existing soft-flag check reads 25 for ACB/VIB/VND where the script expects 24 (data drift unrelated to this change; left alone).

A re-run in a real browser (request count before and after) is a task (5.8, 7.5); the 625 figure is not yet measured.

**Dead / harmless / still needed** (backend, verified by grep over `app/`, `scripts/`, `tests/`):

| Item | Verdict | Why |
| --- | --- | --- |
| `main.py` lifespan load, `import xgboost`, `MODEL_PATH` import | Dead | The only readers of `app.state.model` are `predictions.py` and `insight.py` |
| `GET /prediction` (`get_prediction`) | Dead | Replaced by `GET /range` |
| `GET /insight`, `_compute_advice`, `_load_recent_closes`, `_load_hard_flagged`, `_compute_sentiment` | Dead | `technical.py` has its own stance function; it only mentions `insight.py` in comments (`technical.py:26,35`) |
| `neutralise_hard_flagged_returns` (quality gate) | Harmless, orphaned | Only caller was `insight.py`; has its own tests; `calibrate-volatility-range` may reuse it for HAR features. Left in place |
| `POST /backtest` and its imports in `tickers.py` | Dead | Only caller is `useBacktestTicker` |
| `ml/backtest.py` (all of it, including `compute_rolling_hit_rate`, `is_hit`, `SINGLE_TICKER_BACKTEST_MIN_ROWS`) | Dead | Callers: `tickers.py`, `insight.py`, tests |
| `training.py`: `XGB_PARAMS`, `MAX_BOOST_ROUNDS`, `EARLY_STOPPING_ROUNDS`, `MODEL_PATH`, `train_xgb_model`, `train_final_model`, `assemble_feature_matrix`, `load_training_features` | Dead | Callers: `backtest.py`, `main.py`, `baseline_model_diagnostics.py` (`MODEL_PATH` only), `test_training.py` |
| `training.py`: `compute_fold_boundaries`, `N_FOLDS`, `TARGET_HORIZON`, `_label_dates_by_ticker`, `purge_training_rows` | **Still needed** | `evaluate_cross_sectional_momentum.py` imports `N_FOLDS`, `compute_fold_boundaries`; its test uses the other two as the oracle for its own horizon-generalised purge |
| `training.py`: `filter_clean_labeled`, `FEATURE_COLUMNS` | **Still needed** | The fold tests build their clean frame with it; `FEATURE_COLUMNS` (14 indicators) is the column list the feature-row reader selects. `feature_engineering.FEATURE_COLUMNS` is a different list of the same name (those 14 plus `target`, `near_gap`) |
| `training.py`: `TRAINING_TICKERS` | **Still needed (legacy)** | `tickers.py` uses it for `in_training_set` and catalog ordering; `baseline_model_diagnostics.py` uses it as a default |
| `get_features_computed`, `get_latest_features_row`, the two SQL constants | **Still needed, relocate** | Imported by `debate.py`, `technical.py` |
| `backtest_predictions` table and `CREATE_BACKTEST_PREDICTIONS_TABLE` | Table: harmless data. Constant and `init_db()` creation: dead | Readers and writers are all in dead code |
| `features.target`, `near_gap`, the ten indicator columns the debate does not read | Harmless | Written by `feature_engineering`; `near_gap` is read by `debate-data-guards`; no change |
| `pooled_xgb_model.json`, `har_rv_model.pkl` | Harmless (gitignored) | The first is no longer read; not deleted by this change |
| `xgboost` in `requirements.txt` | Dead | Imported only by the code above |
| `scripts/verify_backtest_predictions.py` | Dead | Checks a table nothing writes |
| `scripts/baseline_model_diagnostics.py` | Partly dead | See table above; trimmed to Finding 7 |
| `ticker_universe.py:353-360` rationale comment | Stale text | Names Advice and the single-ticker backtest as reasons for `MINIMUM_HISTORY_SESSIONS = 250`; the value stays (HAR needs 65 sessions plus 78 of warm-up) |

## Goals / Non-Goals

**Goals:**
- The app boots on a fresh clone with no model artifact; `pytest backend/tests` has no error from a missing file.
- No endpoint, hook or component serves or displays `predicted_log_return`, Confidence from `backtest_predictions`, Advice or the Fresh/Stale dot.
- The selected ticker's chart and card show the calibrated range; unselected tickers cost no request.
- Keep the purged walk-forward helpers and everything the debate reads, in a place that does not carry the word "prediction".
- No destructive data operation.

**Non-Goals:**
- The range endpoint, its semantics, coverage, model artifact and hit-rate computation (`calibrate-volatility-range`).
- Eligibility rules (`debate-data-guards`), rule and disclaimer text, labels, docs (`align-rules-and-disclaimer`).
- The new Rail / Stage / Verdict layout, Watchlist curation (not decided by anyone), a quantile-XGBoost challenger, a scheduler.
- Deleting `backtest_predictions` or the model file; renaming `training.py`.

## Decisions

### Decision 1: remove `/prediction` entirely; the chart and card read `/range`

**Chosen**: delete the route, `get_prediction`, `predictions.py` and the `ticker-prediction` spec's requirements. Both consumers (chart, card) move to `GET /tickers/{ticker}/range` from `calibrate-volatility-range`.

**Alternatives considered**
- *Keep `/prediction` returning only `volatility_range_pct`*: preserves a name that now means nothing, and its semantics are the per-session sigma the review showed to be mislabelled. Two endpoints for one number.
- *Alias `/prediction` to `/range`*: the response shapes differ (`status` vocabularies, no `predicted_log_return`), so an alias is a break wearing a compatibility costume.

### Decision 2: remove `/insight` and `POST /backtest` now, not at "a later change"

The archived change deprecated `/insight` with a `Deprecation` header and deferred removal until "the debate panel is validated in production"; the owner has since decided to stop serving XGBoost. `/insight` Advice runs the retired model and its Confidence reads a table that has 10 tickers (so 589 of 599 read N/A, review Finding 4). `POST /backtest` exists only to fill that table. Keeping them keeps the startup dependency.

**Alternative considered**: keep them returning a static 410. Rejected: nothing calls them once the frontend is updated; a 404 is the honest answer, and a 410 stub is code to maintain.

### Decision 3: keep the fold helpers in `app/ml/training.py`, in place

**Chosen**: trim the file to `TRAINING_TICKERS`, `N_FOLDS`, `TARGET_HORIZON`, `FEATURE_COLUMNS`, `filter_clean_labeled`, `compute_fold_boundaries`, `_label_dates_by_ticker`, `purge_training_rows`, with a module docstring saying it holds walk-forward split helpers only and no model.

**Alternatives considered**
- *Rename to `app/ml/walk_forward.py`*: a better name, but `cross-sectional-momentum-evaluation`'s main spec cites `backend/app/ml/training.py` by path, so a rename needs a delta on a capability this change otherwise does not touch, plus edits to the script and its test, for a cosmetic gain.
- *Copy the helpers into `evaluate_cross_sectional_momentum.py`*: the script already carries a horizon-generalised copy of the purge on purpose, and its test checks that copy against these. Deleting the originals removes the oracle.

### Decision 4: relocate the feature-row readers to `app/services/feature_rows.py`

**Chosen**: move `get_features_computed`, `get_latest_features_row` and their two SQL constants unchanged to `app/services/feature_rows.py` (own `get_connection` import); `debate.py` and `technical.py` import from there. Their existing tests patch the importing module's name (`debate_mod.get_features_computed`, `tech_mod.get_latest_features_row`), which keeps working.

**Alternatives considered**
- *Leave them in `predictions.py` and delete only the route*: leaves a module named after a retired feature that is the first thing a reader opens to find the feature row.
- *Put them in `app/ml/` or `app/db/`*: they are queries over `features` and `tickers` used by services and the debate, which is what `app/services/` already holds. `app/db/` holds schema and connection only.
- *Fold them into `debate-data-guards`'s `assess_eligibility` module*: that change is drafted in parallel and may not land first; a plain move has no dependency.

### Decision 5: `backtest_predictions`: stop writing, leave the data, stop creating it on new databases

**Chosen**: no code writes or reads the table. `CREATE_BACKTEST_PREDICTIONS_TABLE` and its line in `init_db()` are removed, so a new database does not get an empty orphan table; an existing database keeps the table and its 10,191 rows untouched. `DATA_DICTIONARY.md` gets a "legacy" note from `align-rules-and-disclaimer`. A `DROP` is deferred until the owner decides whether the rows are worth archiving (they are the only per-row record of the 47.8% finding).

**Alternatives considered**
- *Keep the constant and the creation*: harmless but dead code that suggests the table is live.
- *Drop the table in `init_db()`*: destructive, irreversible, and contradicts "no destructive migration".
- *Export to CSV then drop*: a reasonable later step; not needed to retire serving.

A test seeds a temporary database with `backtest_predictions` rows, runs `init_db()`, and asserts the rows are unchanged; a second test asserts a fresh database has no such table.

### Decision 6: keep `TRAINING_TICKERS` and the `in_training_set` field

**Chosen**: keep the constant in `training.py` and the field in `GET /tickers` unchanged; the `ticker-catalog` requirement is reworded so `in_training_set` means "one of the nine tickers the retired direction model was trained on, kept as a legacy marker", with no validation claim. The catalog's ordering (those nine first, in declared order, then the rest alphabetically) and the guarantee that they always appear are unchanged.

**Why**: nothing in the frontend reads `in_training_set` (only fixtures set it), so removing it would break no client, but the same constant also pins the first nine Watchlist chips in order. Watchlist curation is undecided and out of scope for every sibling; deleting the pin would curate the Watchlist as a side effect. Renaming the field is an API break for no behaviour gain.

**Alternatives considered**
- *Remove the field and the pin*: the cleaner end state; right once the owner decides the Watchlist. Recorded in Open Questions.
- *Rename to `legacy_training_set`*: breaks the API and four test assertions to fix a name.

### Decision 7: remove the `xgboost` requirement; keep the artifact file

After this change nothing imports `xgboost`, so `xgboost==3.3.0` leaves `requirements.txt` (a heavy wheel on every CI install). `scikit-learn==1.9.0` stays (the HAR model). The 40-odd line `test_saved_model_reloads_from_disk_and_predicts` test goes with `train_xgb_model`. `pooled_xgb_model.json` stays on disk, gitignored: deleting a user file is not part of retiring a serving path, and `cross-sectional-momentum-evaluation` already promises not to modify it.

**Alternative considered**: keep `xgboost` for a possible quantile challenger. Rejected as speculative; the challenger is undecided, and re-adding a pinned dependency is a one-line change.

### Decision 8: scripts

`verify_backtest_predictions.py` is deleted. `baseline_model_diagnostics.py` is trimmed to its model-independent Finding 7 section (and loses the `MODEL_PATH` and lazy `xgboost` imports); Findings 1 and 2 stay reproducible from git history and `DISCUSSION_model_direction.md`. **Alternative**: delete the whole script as the review lists it. Rejected because Finding 7 supports the "portfolio risk" option, which is still open, and the script is how it is re-measured.

### Decision 9: the Fresh/Stale dot, its legend and `useTickerFreshness` are removed

`DISCUSSION_calendar_staleness.md` records that Stale is unreachable (prediction and stored history move in lockstep by construction), that near_gap is invisible on the chip, and lists "delete the dot with its legend and most of `useTickerFreshness`" as a legitimate option. The dot's only input was `/prediction`, which is gone, and the review found it wrong for nearly every ticker. This change takes the removal option.

**What replaces the signal**: "Loaded Nd ago" and the Refresh icon stay on every chip (`ticker-manual-refresh`); the range card shows the `as_of` date; `debate-data-guards` adds `data_as_of` and `data_age_sessions` to the debate result. A calendar-aware chip indicator (the discussion's "cross-ticker max" option) is not built; it can be added later without `/prediction`. The chip's in-flight state needs no dot: the Refresh button already disables and spins while the ticker's load runs, and an unloaded ticker has no chip (it is reached by search). The "Feature computation failed" footer (catalog data, no request) stays.

**Alternative considered**: repoint the dot at the max session date across loaded tickers. It needs the same `/history` prefetch this change removes, and its output would be "Stale" for 205 of the 208 modelling tickers today (the review's staleness count), which is information for the range card and the debate guard, not a per-chip colour.

### Decision 10: no per-chip prefetch, and no per-chip `/range`

**Chosen**: `TickerChip` issues no query. `GET /tickers` is the only request on load. Selecting a ticker issues `GET /history` and `GET /range` for that ticker (both through React Query, so re-selecting uses the cache). The new requirement fixes this budget.

`/range` re-runs the HAR model for each past window it scores (about a year of non-overlapping five-session windows, `calibrate-volatility-range`) on every call, so it is heavier than `/history`. A per-chip prefetch of it would repeat the problem at 208 times that cost; this is why the budget is a requirement, not an implementation habit.

**Cost**: the first paint after selecting a ticker is no longer instant (history and prediction used to share cache keys with the chart, review Finding 5). Accepted: one ticker's two requests, not 625.

**Alternatives considered**: prefetch on chip hover or focus (extra code and still a request burst when scrubbing the list; add only if the selection latency is felt); keep the `/history` prefetch (208 requests of up to 750 rows for nothing a chip shows).

### Decision 11: the `DebatePanel` is unconditional; the flag is removed

Delete `DEBATE_PANEL_ENABLED` from `App.jsx`, the "behind a feature flag" section of `README.md`, the `debate-panel-ui` requirement "Feature flag gates the DebatePanel rollout" and `dashboard-ui` "Dashboard renders AI insight panel for selected ticker" (replaced by "Dashboard renders the debate panel for the selected ticker"). The tracked `frontend/.env*` files also name the flag (found by `git grep -l`; their contents were not read) and are deliberately not edited, by the owner's instruction: a leftover `VITE_` variable nothing reads is inert. The rollback path the flag existed for is the old panel, which this change deletes; the archived design's Open Question 4 ("ship with debate panel on or off by default") is answered: on.

### Decision 12: the range card and the chart band

**Range card (`RangeDisplay`, replaces `PredictionDisplay`)** shows, for the selected ticker, from `GET /range`:
- `range_5s_pct` as `±X.X%`, labelled "Typical 5-session move", never signed, never coloured up/down;
- the `as_of` date;
- the nominal coverage in words taken from `range_coverage` (about 2 in 3 for 0.68); when `range_coverage` is null (`uncalibrated`) it makes no coverage claim;
- `range_hit_rate` (non-overlapping five-session windows over about the last year, per `calibrate-volatility-range`) as "N of the last M five-session moves", M being the `n` that `/range` returns, or "Not enough history to measure" when it is missing or n is 0. This card is the only surface that renders the hit-rate (owner ruling); the chart band and the debate panel do not, and the requirement is owned here;
- the disclaimer in force, beside the coverage figure (see Open Questions 3).

It never shows `sigma_daily_pct`. States: unselected (N/A placeholders, same three-line shape so selection does not shift layout), loading, available, unavailable (a `status` other than a served one, or `range_5s_pct` null: the card names the reason from `reasons` when the response carries it, else a generic line, and shows no number), not loaded (404), failed (5xx). The component keys on "is `range_5s_pct` a number" and treats the `status` text as display only, so a status the sibling change adds later cannot show a stale figure or crash the card.

**Chart band**. The old point line (two valued points, four whitespace points) becomes a band at the t+5 date only: `upper = close x (1 + r/100)`, `lower = close x (1 - r/100)`, `r = range_5s_pct`, `close` the last historical close, `t+5` from `approximateTargetDate(as_of)` (weekday approximation, kept). It is drawn as dashed upper and lower bounds with a light fill between them, in the chart's neutral ink colour (not the positive or negative colour), symmetric about the close.

**Chosen implementation**: a lightweight-charts series primitive (`attachPrimitive`, `autoscaleInfo` available in the installed 5.2.0 typings) attached to a whitespace-only `LineSeries` that keeps reserving the t+1..t+5 slots on the time axis (as the current code does with whitespace points). The primitive draws the fill and the two dashed segments across one session width centred on the t+5 coordinate, and reports the bounds through `autoscaleInfo` so the price scale includes them. Band geometry is a pure function (`rangeBand(lastClose, asOf, rangePct)` returning `{time, upper, lower}`) so it is unit-tested without a canvas.

**Alternatives considered**
- *Two dashed `LineSeries` from the last close to each bound (a wedge)*: easy, but it draws an envelope for t+1..t+4 that no model produced, which the existing spec forbids for the point ("no interpolated, smoothed or otherwise fabricated point") and invites reading the band as a per-session path.
- *Two single-point series plus an `AreaSeries` masked with the background colour for the fill*: no dashed line, and the mask hides grid lines and overlaps the volume pane's time axis.
- *No fill*: the owner asked for a light fill; kept as the fallback if the primitive proves unworkable at implementation (task 5.4 records the choice).

**Recorded at implementation (task 5.4):** the primitive worked, so the fill stays. Two details differ from the sketch above. (1) The primitive is attached to the *candlestick* series, not the whitespace series: a series with no data cannot convert a price to a coordinate (`priceToCoordinate` returns null), so a primitive on the whitespace-only series drew nothing. The whitespace series still exists, only to reserve the t+1..t+5 slots. (2) The band is one bar wide, `timeScale().options().barSpacing` centred on the t+5 coordinate; `logicalToCoordinate` returns 0 for a fractional logical, so it cannot be used for the half-bar edges.

**Risks**: the primitive's draw code cannot run in jsdom, so its pixels are checked by hand in a browser (task 5.8); the unit tests assert the geometry function, that the primitive is attached once, that it is cleared on every non-served state, and that no series receives a valued point between the last close and t+5.

### Decision 13: `lib/logReturn.js` becomes `lib/sessionDates.js`; the conversions go

`logReturnToPercent` and `logReturnToPrice` have no caller once the card and point are gone (the band is a plain multiplication of a percentage). `approximateTargetDate` and `intermediateSessionDates` stay (they position t+5 and reserve the axis slots). The file is renamed so a log-return helper file does not remain in a codebase whose Rule 2 is about never showing log returns; its test file shrinks to the two date helpers. **Alternative**: keep the name. Rejected; one import line per caller.

### Decision 14: what happens to `model-training-pipeline` and `model-backtest`

**Chosen**: remove the XGBoost requirements and keep what the retained helpers still do.
- `model-training-pipeline`: five requirements REMOVED (fixed training set, ticker-free features, pooled single model, untuned hyperparameters, persisted artifact). "Row filtering excludes unknown-quality rows" is MODIFIED to describe the clean-row filter used to build walk-forward folds; it is the only requirement left.
- `model-backtest`: "Directional hit-rate metric", "Persisted per-ticker rolling hit-rate", "No simulated trading return or P&L reporting" and "Model Card documents backtest methodology and results" REMOVED. "Leakage-safe pooled walk-forward split" MODIFIED to name no model; its four scenarios are the leakage guard the cross-sectional evaluation relies on.

**Alternatives considered**: mark both specs "retired" in prose and leave every requirement (the specs would keep promising a model artifact and a persisted hit-rate that no longer exist, and `openspec validate --specs` would still pass, which is the problem); remove every requirement from both (loses the leakage-safe split requirement that a kept helper still implements). The result leaves `model-training-pipeline` with one requirement; folding it into `model-backtest` later is cosmetic and listed under Open Questions.

### Decision 15: test strategy (tests first)

Backend, written before the removals:
1. `test_app_boots_without_model_artifact`: starts `TestClient(app)` with `data/models` empty and asserts `GET /tickers` answers and `app.state` has no `model` attribute. Replaces the two startup tests in `test_tickers_api.py`.
2. `test_removed_routes_are_gone`: `GET /tickers/X/prediction`, `GET /tickers/X/insight`, `POST /tickers/X/backtest` answer 404.
3. `test_feature_rows.py`: the newest row wins and an older clean row is not substituted; a never-loaded ticker returns `None` / 404 input; `features_computed` is `None`, 0 or 1 as stored. These keep the "no walk-back" and "failed features" behaviours the removed `ticker-prediction` tests held (`test_prediction_endpoint_does_not_walk_back_to_older_clean_row`, `..._returns_5xx_when_features_computed_failed`) as unit tests of the reader, because `debate-data-guards` and `/range` build on that behaviour.
4. `test_init_db_leaves_backtest_predictions_rows_untouched` and `test_fresh_db_has_no_backtest_predictions_table`.
5. The two real-database tests in `test_training.py` become synthetic-fixture tests (or are removed where `filter_clean_labeled`'s synthetic tests already cover the same invariant); the VHM known-answer case is checked by `verify_quality_gate.py` (task 1.4 confirms or adds it), so nothing in the suite needs `app.db`.

Frontend, written before the removals: `fetchTickerRange` and `useTickerRange`; `RangeDisplay` states; `rangeBand` geometry; chart band wiring; the request-budget test (spy on every fetcher: one call on mount, two more on selection, none per chip); chip renders no dot and no legend; `App` renders `DebatePanel` with no env var set.

**Tests that encode old behaviour, and what replaces them**

| File (location) | Becomes |
| --- | --- |
| `App.test.jsx` (all but the "heading names the ticker", "no leftover controls" and "fills the viewport" cases) | Rewritten around `RangeDisplay` and `DebatePanel`: placeholders in the range card with no ticker; selecting a chip drives chart and range card; search-load drives them without a manual refresh; no flag needed for the debate panel. The "no leftover controls" test keeps its disclaimer-visibility assertion against the new text |
| `PredictionDisplay.test.jsx` (all 10 tests) | Deleted. `RangeDisplay.test.jsx` covers the same states: unselected shape, loading, available (percent shown, never signed), unavailable with reason, 404, 5xx, distinct states, no `sigma_daily_pct`, coverage wording follows the response |
| `AIInsightPanel.test.jsx` (all 15 tests) | Deleted. The Rule 5 / Rule 6 intents live in `DebatePanel.test.jsx` (labels, disclaimer in all states) and the new range-card disclaimer test. The case-sensitive `/\bBUY\b/` guard is not carried over (align-rules-and-disclaimer adds case-insensitive guards) |
| `ChartPanel.test.jsx` `:282` (renders no overlay once history and prediction load), `:307` (two valued points), `:398` (cleared on near_gap) | Mock `fetchTickerRange`; assert the band geometry, the single attached primitive, no valued point between last close and t+5, cleared on non-served states |
| `TickerPanel.test.jsx` `:232` (freshness dot), `:252` (legend), `:578` and `:597` (insight prefetch) | Dot and legend tests deleted; prefetch tests replaced by "renders chips and issues no per-chip request". `:685` and `:710` (invalidation after refresh) assert history and range instead of history, prediction, insight |
| `useLoadTicker.test.jsx:76` | Asserts tickers / history / range invalidation |
| `lib/logReturn.test.js` | Renamed `sessionDates.test.js`; the two conversion test groups deleted |
| `test_predictions_api.py` (9), `test_ai_insight_api.py` (11), `test_backtest.py` (6), `test_single_ticker_backtest.py` (3) | Deleted (see Decision 15 items 2-4 for what replaces their reusable intent) |
| `test_training.py` | Keep the purge, fold-order and clean-filter tests; delete `assemble_feature_matrix` and `saved_model_reloads` tests |
| `test_tickers_api.py:82-98` | Replaced by item 1 above; the rest (catalog, history) is unchanged |

### Decision 16: sequencing

Backend removal (sections 2-3 of tasks.md) is independent of every sibling except that `debate.py` and `technical.py` must be repointed before `predictions.py` is deleted (task 3.2 precedes 3.5). Frontend removal can land with it. The range card and band (section 5) need `GET /range`; they are developed against the response shape in the shared contract with `fetchTickerRange` mocked, and finish against the real endpoint once `calibrate-volatility-range` has landed. **Recommended order**: `debate-data-guards` and `calibrate-volatility-range`, then this change, then the doc and rule sync. If the owner wants the retirement earlier, deploy sections 2-3 first: the dashboard then loses the Prediction card and the chart point before the range card exists, which is the honest state (nothing is displayed that should not be) but leaves an empty slot until section 5 lands.

### Decision 17: delta mechanics learned from an archive dry run

`openspec archive` applies RENAMED, then REMOVED, then MODIFIED, then ADDED, and refuses a MODIFIED block that omits any scenario name present in the current requirement. Where this change drops or renames scenarios (the Prediction and Insight states, the freshness scenarios, the feature-flag scenarios) it therefore uses REMOVED for the old requirement and ADDED under a new header, not MODIFIED or RENAMED. `ticker-catalog`, `model-backtest`, `model-training-pipeline` and the `dashboard-ui` legend keep all scenario names and use MODIFIED (the catalog one with a RENAMED header). The dry run (a scratch copy, not the repository) archived the change cleanly: 12 added, 4 modified, 34 removed, 1 renamed.

**Alternative considered**: `--skip-specs` or `--no-validate` at archive. Rejected: it would leave the main specs describing the retired panel and endpoint.

## Risks / Trade-offs

- **[Rules 3 and 4 become wholly unimplemented before their rulings]** -> by design the display is removed, not the rule text (not edited here); the proposal states the dependency and recommends landing `align-rules-and-disclaimer`'s rulings in the same release.
- **[Rule 5's inline basis line disappears]** -> the debate's Technical Signal card carries the reasoning bullets, shown at Level 2; whether Level 1 needs the basis is part of the Rule 5 ruling. Noted in the removed requirement's migration text.
- **[Loses the instant first paint after selecting a ticker]** -> accepted, Decision 10.
- **[A chart band built on a mislabelled number would repeat Finding 1]** -> the band uses `range_5s_pct` only, from the calibrated endpoint; it must not be wired to the old `volatility_range_pct`. Hence the dependency ordering.
- **[Environment files are tracked in git]** -> `git ls-files` lists `frontend/.env`, `.env.example` and `.env.test`. This session did not read them (the secrets policy blocked it) and this change does not edit them. Vite exposes every `VITE_*` variable in the bundle, so they should hold only public values; the owner should confirm that separately.
- **[The `xgboost` removal surprises a developer with an old venv]** -> nothing imports it; leaving it installed is harmless.
- **[Fresh clone has no `har_rv_model`]** -> after this change the app boots, but `predict_volatility_range` and the future `/range` return no number until `train_har_rv.py` has run. The distinct "model not trained" status belongs to `calibrate-volatility-range`; the README step is task 6.2's.
- **[Vitest worker startup timeouts in this environment]** -> a baseline `npx vitest run` in this session finished with 5 files and 27 tests passing but 7 "failed to start worker" errors after 228 s (the WSL host had just restarted). No frontend baseline is claimed; task 1.3 records one.

## Migration Plan

1. Evidence script and baselines (tasks 1.x). 2. Backend tests first, then the relocation, then the removals (2.x, 3.x); run the backend suite on a fresh clone. 3. Frontend tests first, then removals, then the range card and band (4.x-5.x). 4. README and `.env` edits, stale-comment sweep (6.x). 5. Verification (7.x).

**Rollback**: git revert. No data is changed, so reverting restores the old serving path as long as `pooled_xgb_model.json` is still on disk (it is not deleted).

## Open Questions

1. **Watchlist and the legacy pin.** When the owner decides Watchlist curation, drop `in_training_set` and the nine-first ordering (or replace them with an explicit list). This change deliberately does not.
2. **`technical-agent` spec wording.** The requirement "Technical Agent reads indicator feature row and computes a stance" says the stance uses "the same signals as the existing `_compute_sentiment` function in `backend/app/api/insight.py`". That file is deleted here. `calibrate-volatility-range` owns `technical-agent`; its MODIFIED requirement set should reword this sentence, or the main spec will cite a missing file after archive. The code comments at `technical.py:26,35` are fixed in task 3.3.
3. **Disclaimer next to the coverage figure** (resolved by the owner). Showing the range check beside the disclaimer is accepted. The disclaimer string lives in `frontend/src/lib/disclaimer.js`, with a drift test against `docs/DISCLAIMER.md`; `align-rules-and-disclaimer` owns the text and that test. This change only imports the constant in `RangeDisplay`; the module lands with that change (task 5.5 adds a one-line placeholder export if this change lands first).
4. **`/range` status vocabulary.** `calibrate-volatility-range` names `range_out_of_bounds` and `uncalibrated` and an eligibility refusal; this change keys on whether `range_5s_pct` is a number and uses `status` and `reasons` as display text only. If that change makes a served range carry a non-null `range_5s_pct` with a refusing status, the card and band must also check `status`; reconcile when both exist.
5. **`range_hit_rate` shape.** The owner's ruling: non-overlapping five-session windows over about the last year, shown as "N of the last M five-session moves", with `n` (= M) returned by `/range`. The exact field carrying N (a hit count, or `rate` with `n`) and the empty form are `calibrate-volatility-range`'s; this change computes N as `rate x n` rounded when only those are present, and treats a missing object, `n` of 0 or no usable rate as "not enough history". The range card is the only surface that renders it; the chart band and the debate panel do not.
6. **Empty main specs at archive** (checked, resolved). An archive run on a scratch copy of the specs (`openspec archive retire-direction-model --yes`) rejected a `ticker-prediction` emptied of all requirements ("Spec must have at least one requirement") and aborted without writing. The delta therefore removes the nine requirements one by one and ADDS a stub requirement ("The direction prediction endpoints are retired") with two testable scenarios; the same run then archived the whole change cleanly. It also showed that a MODIFIED block must keep every existing scenario name, so `dashboard-ui` and `ticker-manual-refresh` requirements whose scenarios change are REMOVED and re-added under new names (Decision 17).
7. **Stale `dashboard-ui` text.** The "Ticker panel shows the fixed set plus search" requirement still says the panel renders the 9 `TRAINING_TICKERS`; the code has shown every loaded catalog entry for some time. Pre-existing drift tied to Watchlist curation; not touched.
8. **`ohlcv-quality-gate` scenarios.** Two scenarios ("A prediction is never served from missing features", "Exclusion ... from training and from serving") speak of predictions. They stay true of `filter_clean_labeled` and are vacuous for serving; the serving-side intent is carried by `debate-data-guards`' `indicators_missing`. No delta here.
9. **Request count in a browser.** 625 (this change) versus about 1,800 (review) is derived from code and the database; a Playwright network count before and after (tasks 5.8, 7.5) settles it. (After-change count measured; the before-change count was not, see the implementation record.)

## Implementation record (2026-10-07)

**Browser check (tasks 5.8 and 7.5)**, Playwright against `make up` (backend and Vite dev server) and the real `app.db`: page load with nothing selected made **1** API request (`GET /tickers`); selecting a chip brought the total to **3** (`/tickers`, `/history`, `/range` for that ticker), with no `/prediction`, `/insight` or `/backtest` request. The pre-change request count was not measured in a browser (the old tree was not run); the 625 stays a figure derived from the code and the catalog query, and the review's ~1,800 is not reproduced. Every real ticker was `ineligible` / `stale` on the day (stored data ends 2026-09-07), so the unavailable state with its reason was seen live; the available state and the band were seen with a stubbed `/range` response (`range_5s_pct` 7.5, 2.0 and 25) injected in the page. Observed: dashed upper and lower bounds with a light fill, one bar wide at t+5, symmetric about the last close, neutral ink, nothing drawn between the last close and t+5; the price scale expanded to include the bounds at 25% (16.1 to 26.9); light and dark themes both read correctly. The theme is read once when the chart is created, as before.

**Dry run (task 7.6)** in a scratch copy of `openspec/specs`, `config.yaml` and this change: `openspec archive retire-direction-model --yes` archived cleanly with 12 added, 4 modified, 34 removed, 1 renamed (the Decision 17 figures). `openspec validate retire-direction-model` passes. Both siblings named in the ordering note (`calibrate-volatility-range`, `debate-data-guards`) were already archived on 2026-10-07 when this change was applied.

**Final checks.** Backend: 899 passed on the working tree and on a data-less copy of it (no `data/models`) with `xgboost` made un-importable; the backend boots from that copy, `GET /tickers` answers 200 and `GET /tickers/TCB/prediction` 404. The copy is a snapshot of the working tree, not a `git clone`, because the sibling changes' work is still uncommitted. Frontend: 17 files, 271 tests; `npm run lint` and `npm run build` pass. `verify_retirement_claims.py --expect-xgboost-files none` reports no importer.

**`backtest_predictions` changed during the session (task 7.4).** Task 1.2 recorded 10,191 rows / 10 tickers / max date 2026-08-05. By the end the table held **10,240 rows, max date 2026-09-25**: VIB went from 973 to 1,022 rows, no other ticker changed, and `backend/data/app.db` was last modified at 17:02:21 local time, during this session. This session issued no backtest request and nothing this change adds writes the table, so the cause is the old "Backtest this ticker" action used against the real database from another process; the owner confirmed this after the fact (this session did not observe it). The retirement code never touches the rows (a unit test seeds a temporary database to prove `init_db()` leaves them alone), so the figure to compare against from here on is 10,240. `pooled_xgb_model.json` is still on disk, unmodified (2026-07-30).

**Hand-offs (tasks 6.4, 6.5), for `align-rules-and-disclaimer` and the owner; none of these files were edited here:**
- `docs/MODEL_CARD.md`: add a retirement note for the removal of serving and of the `xgboost` requirement.
- `docs/DATA_DICTIONARY.md`: `backtest_predictions` is legacy, no longer created on a new database.
- `docs/DISCUSSION_calendar_staleness.md`: resolved by removing the dot, legend and `useTickerFreshness` (Decision 9).
- `docs/KNOWN_ISSUES.md` (the text about `filter_clean_labeled` and `/prediction` gating): `/prediction` is gone.
- `openspec/config.yaml` and `CLAUDE.md`: Rules 3 (Advice) and 4 (Confidence) now have no implementation; `config.yaml` still lists XGBoost in the stack and the freshness dot as fed by `/prediction`.
- `openspec/specs/technical-agent/spec.md` (owned by `calibrate-volatility-range`, already archived): "same row used by the existing insight endpoint" refers to a removed endpoint and needs rewording (Open Question 2). The code comments that cited `insight.py` were fixed in task 3.3.
- The tracked environment files under `frontend/` still name `VITE_DEBATE_PANEL_ENABLED`, which nothing reads now. They were not read or edited here (owner instruction, task 6.1). Vite exposes every `VITE_*` value in the bundle, so check them for non-public values.
- `backend/scripts/baseline_model_diagnostics.py` Finding 7 builds its wide frame with `DataFrame.pivot`, which the project's memory notes as giving wrong date labels on this Python 3.14 venv; left as it was.
- `backend/scripts/verify_quality_gate.py`: its soft-flag check (ACB/VIB/VND expected 24) reads 25; pre-existing data drift, separate from the VHM blackout check added in task 1.4.
