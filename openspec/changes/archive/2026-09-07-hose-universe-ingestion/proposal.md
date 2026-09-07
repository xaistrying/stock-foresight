## Why

The database holds 15 hand-picked large-cap tickers chosen for M3 training.
That set cannot answer the questions the project now wants to ask: it is too
small for cross-sectional work (a top decile is 1.5 stocks), too homogeneous
to estimate sector structure, and — because every ticker in it is a survivor
still listed today — it would make any historical backtest optimistic in a way
that cannot be detected after the fact.

Verified this session: vnstock exposes **405 HOSE ordinary stocks** plus
**229 delisted ordinary stocks whose OHLCV history is still retrievable**
(e.g. `VSP` returns 1,634 rows ending 2022-07-28, its delisting date).
Point-in-time, survivorship-bias-free universe construction is therefore
possible — which is unusual for retail-tier data and is the reason to do this
now rather than after building on a survivor-only base. Retrofitting
survivorship correction later means discarding and re-ingesting everything.

## What Changes

- **New**: build the ticker universe from
  `Listing().symbols_by_exchange()`, filtered to `exchange = HSX` and
  `type = STOCK` (excludes the covered-warrant, ETF, bond, and futures rows
  that share the listing). Persist `icb_code2` (ICB industry classification)
  per ticker for later sector/factor work.
- **New**: ingest delisted symbols alongside listed ones, recording listing
  status and observed first/last session dates, so a backtest as of any past
  date can reconstruct the universe that actually existed then.
- **New**: dated exchange membership rather than current-state. Verified
  migrations in the existing data: `ACB` and `VND` moved HNX -> HOSE and
  `VIB` moved UPCOM -> HOSE around 2020-21, and their pre-move rows legally
  exceed HOSE's price limit.
- **New**: an OHLCV quality gate at ingestion, using each exchange's daily
  price limit as ground truth (HOSE ±7%, HNX ±10%, UPCOM ±15%) — evaluated
  against the exchange the ticker was on *at that date*, not today's.
- **New**: a liquidity/stale-price filter promoted from advisory to
  enforced, reusing the existing check in
  `backend/scripts/screen_ticker_volatility.py`
  (`STALE_PRICE_WARN_THRESHOLD = 0.15`, the fraction of sessions where
  `close == prev close`).
- **New**: a batch ingestion entry point that can walk 600+ symbols under
  vnstock rate limiting, outside any HTTP request lifecycle.
- **BREAKING**: `GET /tickers` no longer returns exactly `TRAINING_TICKERS`.
  The catalog becomes universe-derived. The current `ticker-catalog`
  requirement forbidding "any second, independently-edited list" is
  satisfied differently — by deriving from the universe table rather than
  from `training.py`.
- **New**: a refusal state for the prediction and insight endpoints when
  the latest `features` row has null indicator columns. Discovered in
  review of task groups 4-5: the quality gate's blackout nulls indicators
  without setting `near_gap`, and every consumer gated on `near_gap` alone,
  so a blacked-out row would enter training as an all-null feature vector
  with a valid label, and serve a confident-looking percentage (and Rule 3
  Advice) computed from missing values. Not reachable before this change;
  reachable as soon as the batch ingest finds a mid-life missed split.
- **Not changed**: the model itself and the training set. `TRAINING_TICKERS`
  continues to define what the model was trained on; this change decouples
  "tickers the system knows about" from "tickers the model was trained on",
  which are currently the same list. The dashboard gains one prediction
  state and no redesign.

## Capabilities

### New Capabilities
- `ticker-universe`: point-in-time universe construction — which symbols
  existed, on which exchange, over which date range, with industry
  classification; including delisted symbols so historical universes are
  reconstructable.
- `ohlcv-quality-gate`: validation applied to fetched OHLCV before it is
  persisted — exchange-and-date-aware price-limit violation detection, and
  stale-price/illiquidity measurement.
- `bulk-ticker-ingestion`: batch ingestion of the full universe outside the
  request lifecycle, resumable and rate-limit aware.

### Modified Capabilities
- `ticker-catalog`: the requirement that `GET /tickers` returns exactly
  `TRAINING_TICKERS` is replaced — the catalog is derived from the universe
  table, and each entry gains exchange, industry, listing status, and
  observed date range. The prohibition on a second hand-edited list is
  retained.
- `ticker-data-ingestion`: `load_ticker` gains the quality gate before
  persistence, and gains the ability to be driven in batch. The existing
  single-call fetch contract (`count=5000`, `source="vci"`, ~8-year
  community-tier cap) is unchanged.
- `ticker-prediction`: `GET /tickers/{ticker}/prediction` gains an
  `indicators_unavailable` refusal for a latest row with null indicator
  columns, and `GET /tickers/{ticker}/insight` withholds `advice_text` in
  the same case. Neither previously checked anything but `near_gap`.
- `dashboard-ui`: the prediction display's four distinct states become
  five, covering the new refusal. No redesign — the chart panel already
  gates its predicted point on `status: "ok"` and needs no change.

## Impact

**Code**
- `backend/app/services/ticker_ingestion.py` — quality gate, batch driver.
- `backend/app/api/tickers.py` — catalog derived from universe, not
  `TRAINING_TICKERS`.
- New: universe construction service, quality-gate module, batch CLI entry
  point under `backend/scripts/` (matching where
  `screen_ticker_volatility.py` actually lives).
- `backend/app/ml/training.py` — `TRAINING_TICKERS` stays as the training
  set definition but stops being the catalog source; `filter_clean_labeled`
  additionally requires non-null indicator columns.
- `backend/app/api/predictions.py`, `backend/app/api/insight.py`, and
  `frontend/src/components/PredictionDisplay/` — the null-indicator refusal
  and its dashboard state.

**Database**
- New universe/membership table (symbol, exchange, ICB code, listing status,
  first/last observed session).
- `ohlcv` or a sidecar table gains quality flags for rows failing the price
  limit.
- Growth from ~30k to ~800k+ `ohlcv` rows; DB from ~10 MB to ~250-300 MB.
  SQLite handles this, but full-table feature recomputation does not scale
  the same way — see below.

**Cost / performance**
- 600+ sequential vnstock calls under rate limiting; this is a long-running
  batch, not a request.
- Feature recomputation currently runs from each ticker's earliest row on
  every load, required for `obv` correctness
  (`docs/DATA_DICTIONARY.md`, design Decision 5). At this scale that full
  pass becomes the dominant cost and needs an explicit decision in design.

**Dependencies**
- `Vnstock().stock(...)` was deprecated 2025-08-31 in favour of
  `vnstock.api.quote.Quote`. Existing code uses `vnstock.ui.Market`, which
  still works; this change should confirm which surface to standardise on
  rather than mixing them.
- **Prerequisite**: `docs/KNOWN_ISSUES.md` records that the `vnstock`/`vnai`
  prompt-injection patch lives only inside the gitignored `backend/.venv`
  and silently regresses on any reinstall or upgrade. This change involves
  heavy vnstock use and likely environment work, so the durable fix should
  land first rather than being rediscovered mid-ingest.

**Domain rules**
This change touches **none of the non-negotiable domain rules 1-6**. It is
data ingestion only: no change to the prediction target (Rule 1), no UI
display of returns (Rule 2), no advice thresholds (Rule 3), no confidence
definition (Rule 4), no sentiment labelling (Rule 5), and no output framing
(Rule 6). All six are honored unchanged; none require sign-off.

**Explicitly out of scope**
The model pivot (volatility target, interval output), holdings/portfolio
risk, and cross-sectional strategy work. Those are open and undecided —
see `docs/DISCUSSION_model_direction.md`, which is the evidence base this
change draws on.
