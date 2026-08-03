## Why

M3 produced a trained pooled XGBoost model, a persisted backtest, and a
`compute_rolling_hit_rate` helper — but nothing in the running application can
serve a prediction yet. M5's dashboard needs a single, well-defined HTTP
endpoint to call for a ticker's next-5-session prediction before frontend work
can start. This change adds that endpoint only: a read path from the already
trained model and already persisted `features` table, with no new
computation, no new model training, and no UI-facing framing (confidence,
sentiment, advice) attached yet.

## What Changes

- Add `GET /tickers/{ticker}/prediction`, returning the model's prediction for
  the ticker's most recently persisted `features` row.
- Load the persisted XGBoost booster (`backend/data/models/pooled_xgb_model.json`)
  once at FastAPI startup into `app.state`, alongside the existing `init_db()`
  call in `main.py`'s lifespan handler. A missing or corrupt model file fails
  application startup, not an individual request.
- Response is a **tagged-union shape** keyed by a `status` field, not a single
  fixed schema — `status` is one of `"ok"` or `"near_gap"`:
  - `status: "ok"`: latest `features` row has `near_gap = 0`; response
    includes `predicted_log_return` (raw model output, Rule 1's target
    definition, Rule 2 does not apply — no UI renders this response yet).
  - `status: "near_gap"`: latest `features` row has `near_gap = 1`; response
    omits `predicted_log_return` entirely. This is a routine, expected
    outcome (not an error) — the model was never trained or backtested on
    `near_gap = 1` rows (`training.py`'s `filter_clean_labeled` excludes them
    outright), so scoring one would be a genuinely out-of-distribution
    prediction presented as ordinary output.
- Ticker not yet loaded (no `features` rows at all) returns `404`. This
  endpoint never triggers `load_ticker` itself — loading stays owned by the
  existing `POST /tickers/{ticker}/load` endpoint, deliberately, so a
  prediction `GET` cannot trigger a rate-limited external `vnstock` fetch.
- Ticker loaded but its most recent feature-recomputation attempt failed
  (`features_computed = False`, per the existing `load_ticker` /
  `recompute_features_for_ticker` error path) surfaces as a `5xx` — an
  unexpected-fault signal meant to page/alert, not a routine data-availability
  state. This requires a small schema addition: `load_ticker`'s
  `features_computed` outcome is currently returned in its HTTP response
  only and never persisted, so this change adds a `features_computed`
  column to the existing `tickers` table, written on every load.
- Prediction is computed strictly from the persisted `features` row's stored
  indicator columns — no indicator is recomputed live from `ohlcv` at request
  time. This avoids a second feature-computation code path that could drift
  from `feature_engineering.py`'s stored values (the exact bug class
  `docs/KNOWN_ISSUES.md`'s `_wilder_smooth` entry already documents once).
- **Out of scope, explicitly**: `confidence_score`, `sentiment_proxy`,
  `advice_text`, and the rest of the AI insight panel contract stay entirely
  owned by M6's `ai_insight_service.py`, even though `compute_rolling_hit_rate`
  (Rule 4's exact confidence definition) already exists from M3. This
  endpoint's response never includes a confidence/sentiment/advice field.
- **Out of scope, explicitly**: no walk-back to an older `near_gap = 0` row
  when the latest row is `near_gap = 1`. A v1 prediction is either current
  and valid, or the endpoint says explicitly why not — never a stale
  prediction presented as current (Rule 6).
- **Out of scope, explicitly**: batch/multi-ticker prediction. Single-ticker
  only in this change.

## Capabilities

### New Capabilities
- `ticker-prediction`: serving a single ticker's next-5-session prediction
  from the persisted model and persisted features, including the
  ticker-not-loaded, feature-computation-failed, and near-gap response states.

### Modified Capabilities
- `ticker-data-ingestion`: `load_ticker` must persist its `features_computed`
  outcome onto the `tickers` row (new column) instead of only returning it in
  the HTTP response, so this endpoint can read a durable signal rather than a
  value that no longer exists once the load request completes.

## Impact

- **New**: `backend/app/api/predictions.py` (new router), registered in
  `backend/app/main.py`.
- **Modified**: `backend/app/main.py` — lifespan handler loads the booster
  into `app.state.model` alongside the existing `init_db()` call; new router
  included.
- **Reads**: `features` table (`near_gap`, the 14 `FEATURE_COLUMNS`),
  `tickers` table (existence check for the 404 case).
- **Schema change**: `tickers` table gains a `features_computed` column
  (nullable/absent = never attempted, distinguishing that from an attempted
  and failed computation), written by `load_ticker` on every load.
- **Domain rules touched**:
  - **Rule 1** (target definition): honored unchanged — `predicted_log_return`
    is the model's direct output against the existing `target_t =
    ln(close[t+5] / close[t])` definition; this change does not alter what
    the model predicts.
  - **Rule 2** (never show raw log return in the UI): not yet applicable —
    this change has no UI. Flagged explicitly because the response does carry
    a raw log return over HTTP; any future consumer (M5) must convert to a
    percentage before display, but that conversion is out of this change's
    scope by construction (no UI here).
  - **Rule 4** (confidence score definition): honored by *omission* — this
    change deliberately does not expose `compute_rolling_hit_rate`'s value
    even though the function exists, to keep the confidence/sentiment/advice
    contract solely owned by M6.
  - **Rules 3, 5, 6** (advice thresholds, sentiment proxy, investment-advice
    framing/disclaimer): not applicable — this change exposes no advice,
    sentiment, or confidence field, so there is nothing for Rule 6's
    disclaimer to attach to yet. Revisit at M6.
