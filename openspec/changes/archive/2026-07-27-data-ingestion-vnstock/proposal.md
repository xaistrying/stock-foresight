## Why

M1 needs a way to get Vietnamese stock OHLCV history off `vnstock` and into
local SQLite before any feature engineering (M2) or model training (M3) can
start. There is no ingestion path yet — the ticker panel has nothing to call.
A single on-demand endpoint that works for both first-load and reload keeps
M1 scoped to "get data in reliably," deferring universe seeding and
delta-fetch optimization to M5 when batch scale actually matters.

## What Changes

- Add `POST /tickers/{ticker}/load`, calling a new `load_ticker(ticker)`
  service function.
- Fetch OHLCV via `mkt.equity(ticker).ohlcv(start="2000-01-01", end=today,
  count=5000, source="vci")` — one call, explicit large `count`, fixed
  `start` constant, `vci` source only. No chunking or walk-back beyond this
  single call.
- Wrap the fetch's `RateLimitError` in try/except as scaffolding only
  (not enforced/exercised at M1 scale).
- Post-fetch: strip the 07:00:00 time-of-day quirk to date-only ISO TEXT;
  log (not fail) when a gap between consecutive stored sessions exceeds 5
  calendar days.
- Create SQLite tables `ohlcv` and `tickers` per the schema below, both
  upserted (`ON CONFLICT ... DO UPDATE`) on every call, first load and
  reload alike.
- Derive `tickers.available_since` (min date from the load) and
  `tickers.possibly_truncated_by_tier` (heuristic flag, does not gate or
  block any write to `ohlcv`).
- Create `docs/DATA_DICTIONARY.md` documenting the schema and the quirks
  above.

## Capabilities

### New Capabilities
- `ticker-data-ingestion`: on-demand fetch of a ticker's OHLCV history from
  vnstock into SQLite, with upsert semantics, gap/truncation detection, and
  the `tickers`/`ohlcv` schema. Covers both first-load and reload through one
  endpoint.

### Modified Capabilities
(none — no existing specs)

## Impact

- **New code**: `backend/app/api/` route for
  `POST /tickers/{ticker}/load`; `backend/app/services/` `load_ticker`;
  `backend/app/db/` schema/migration for `ohlcv` and `tickers` tables.
- **New dependency surface**: `vnstock` package (`source="vci"`), per the
  project's vnstock skill.
- **DB**: creates `backend/data/app.db` tables `ohlcv`, `tickers` — first
  schema committed for this project (M1).
- **Docs**: creates `docs/DATA_DICTIONARY.md`.
- **Domain rules**: none of the 6 non-negotiable rules apply to this
  change — it is pure ingestion, upstream of the prediction target (rule 1),
  UI display (rules 2, 5, 6), and advice/confidence logic (rules 3, 4). No
  sign-off needed.
- **Explicitly out of scope** (deferred): VN30/index universe seeding (M5),
  delta-fetch/staleness-aware refresh (M5), fetching beyond the ~8-year
  community-tier limit via walk-back (shelved pending root-causing a prior
  `ValueError`), capturing the library's tier-limit warning as a structural
  signal instead of the calibrated heuristic.
