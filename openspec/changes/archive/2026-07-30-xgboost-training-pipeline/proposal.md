## Why

M2 produced a `features` table (six indicator families, target, `near_gap`)
but no model consumes it yet. M3 closes that gap: train a first XGBoost
regressor against the persisted features, validate it with a leakage-safe
walk-forward backtest, and produce a Model Card documenting what was
trained and how it performed — so M4's prediction endpoints have a model
to call and M6's confidence score (Rule 4) has real hit-rate data to read.

This is a first-pass pipeline to prove the mechanics work end-to-end
(features -> training -> validation -> persisted model), not a tuned or
final model.

## What Changes

- Add a data-loading step that reads `features` rows for a fixed set of 9
  tickers (TCB, VIB, VHM, VND, MWG, HPG, MSN, VNM, SAB — chosen via
  empirical realized-volatility/stale-price screening for sector and
  volatility spread, not sector-label guessing alone) and filters to
  `near_gap = 0 AND target IS NOT NULL` ("clean+labeled" rows).
- Add a pooled (not per-ticker) walk-forward split: expanding training
  window, 4-6 folds, shared calendar-date fold boundaries across all
  tickers, with an explicit purge of the 5 rows immediately before each
  boundary on the training side (since `target` looks 5 sessions ahead —
  Rule 1 — any training row whose label window extends into the test
  period must be dropped to avoid leakage).
- Add an XGBoost training step: pure OHLCV-derived indicator features only
  (no ticker-identity column — see design.md Decision 3), conservative
  untuned hyperparameters (shallow trees, early stopping, regularization),
  single global model across all 9 tickers.
- Add a backtest evaluation step: walk-forward validation only (rolling-
  origin metrics per fold), no simulated P&L/trading-return layer.
- Add a persisted hit-rate definition feeding Rule 4's confidence score
  (backtested hit-rate over a ticker's most recent ~60 predictions) — see
  design.md for the precise "hit" criterion.
- Persist the trained model artifact and backtest results so M4 can load
  a model and M6 can read confidence/hit-rate data.
- Create `docs/MODEL_CARD.md` (referenced in `openspec/config.yaml`'s
  repository-structure line but not yet assigned to a milestone) —
  documents training data, features, split methodology, hyperparameters,
  and backtest results.

**Explicitly out of scope for this change:**
- Hyperparameter tuning (conservative defaults only; tuning is a future
  iteration once the pipeline is proven).
- A batch/bulk ticker-loading capability — the 9 tickers are loaded via
  M1's existing `POST /tickers/{ticker}/load`, called manually per ticker.
  No new ingestion code.
- Ticker-identity-as-feature ablation (deferred until more tickers exist —
  9 is too few for a meaningful held-out-ticker test).
- FastAPI prediction endpoints (M4) and any UI (M5/M6).
- Regime-adaptive (rolling-window) backtesting — expanding window only,
  since usable history is already thin after excluding `near_gap` rows;
  revisit if this becomes a real concern with more data.

## Capabilities

### New Capabilities
- `model-training-pipeline`: Trains an XGBoost regressor from persisted
  `features` rows across a fixed multi-ticker set, using a leakage-safe
  pooled walk-forward split, and persists the resulting model artifact.
- `model-backtest`: Runs walk-forward validation over the trained model,
  computes per-fold and rolling per-ticker hit-rate/error metrics (feeding
  Rule 4's confidence score), and persists results for later consumption.

### Modified Capabilities
- (none — `ticker-data-ingestion` and `feature-engineering` are read-only
  inputs to this change; no requirement changes to either)

## Impact

- New code: `backend/app/ml/training.py` (or similar), `backend/app/ml/
  backtest.py`, a persisted model artifact location (e.g.
  `backend/data/models/`), a training/backtest entry-point script.
- New doc: `docs/MODEL_CARD.md`.
- Reads (no schema changes): `features` table (M2), specifically the 9
  named tickers' `near_gap = 0 AND target IS NOT NULL` rows.
- Dependency: adds `xgboost` and `scikit-learn` (or equivalent) to
  `backend/requirements.txt` — confirm before adding a new dependency
  outside what's already listed.
- Non-negotiable domain rules touched:
  - **Rule 1** (target definition): honored unchanged — training reads
    the existing `target` column as-is, no redefinition.
  - **Rule 3** (volatility-relative advice threshold): not implemented by
    this change (that's M6 UI/advice logic) — but this change's backtest
    results are the evidence base the `0.5` coefficient may later be
    tuned against. Design remains volatility-relative regardless;
    coefficient stays provisional.
  - **Rule 4** (confidence score = hit-rate over last ~60 predictions):
    this change defines and computes the hit-rate this rule depends on —
    see design.md for the precise "hit" criterion, which is new (not yet
    specified anywhere else) and being decided here.
  - Rules 2, 5, 6: not touched — no UI, no sentiment labeling, no advice
    text is produced by this change.
