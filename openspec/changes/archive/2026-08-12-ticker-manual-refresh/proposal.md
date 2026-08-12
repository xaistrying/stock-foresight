## Why

Once a ticker has been loaded once, selecting it again (chip click or
search) never re-calls `POST /tickers/{ticker}/load` — by design, per the
existing `dashboard-ui` spec ("Searching an already-loaded ticker selects
it directly, without issuing a new /load request"). `load_ticker` itself
has no staleness guard and is safe to call again at any time — it simply
re-fetches OHLCV, recomputes features, and updates `last_loaded_at`. The
result is a ticker can sit for weeks without new trading sessions while
its freshness dot still shows Fresh (Fresh/Stale only compares the stored
prediction against the ticker's own stored latest session, never against
real-world today), and a user has no way to ask for newer data short of
restarting the app or clearing the database. This adds an explicit,
user-triggered way to re-run the existing load flow for an
already-loaded ticker, plus visibility into when it was last loaded so
the action is discoverable and its value is legible.

## What Changes

- Add a "Refresh" action, surfaced per ticker (chip or chart panel), that
  calls the same `POST /tickers/{ticker}/load` endpoint already used for
  first-time loads — no new backend endpoint or ingestion logic.
- Surface `last_loaded_at` (already returned by `GET /tickers`, currently
  unused in the UI) somewhere visible near the refresh action, so a user
  has a concrete reason to refresh rather than a bare icon.
- On successful refresh, invalidate the same history/prediction/insight
  queries the initial load invalidates today, so the chart, prediction,
  and AI insight panel reflect the newly fetched data without a page
  reload.
- Client-side debounce/disable on the refresh action while a request is
  in flight, so repeated clicks cannot issue overlapping `/load` calls
  for the same ticker.
- **Explicitly out of scope**: changing what Fresh/Stale/Loading mean or
  how they're computed; any automatic/scheduled refresh; rate-limiting
  or backoff logic beyond the existing `rate_limited` status handling;
  any change to `load_ticker`'s fetch parameters, error classification,
  or DB writes.

## Capabilities

### New Capabilities
- `ticker-manual-refresh`: A user-triggered action per already-loaded
  ticker that re-runs the existing load flow, surfaces `last_loaded_at`,
  and refreshes dependent chart/prediction/insight data on success.

### Modified Capabilities
- None. `openspec/specs/ticker-data-ingestion/spec.md` already specifies
  and the backend already implements everything this change needs at the
  ingestion layer — see "Reload of an already-loaded ticker": `POST
  /tickers/{ticker}/load` "works identically whether the ticker has never
  been loaded before or is being reloaded" and upserts without requiring
  a separate refresh endpoint. The gap this change closes is entirely
  that no UI ever calls that already-correct endpoint a second time.

## Impact

- **Backend**: no changes. `POST /tickers/{ticker}/load` and
  `load_ticker` (`backend/app/services/ticker_ingestion.py`) are reused
  as-is, exactly as already specified by `ticker-data-ingestion`.
- **Frontend**: `TickerChip.jsx` (or a new small component near the
  chart) gains a refresh control; `useLoadTicker.js` gains a variant (or
  reused hook) callable for an already-loaded ticker; `TickerPanel`'s
  `GET /tickers` consumption starts reading `last_loaded_at` for display.
- **Domain rules**: none of the six non-negotiable rules are touched.
  This change does not affect prediction math (Rule 1), log-return
  display (Rule 2), advice thresholds (Rule 3), confidence computation
  (Rule 4), sentiment framing (Rule 5), or advice/disclaimer framing
  (Rule 6) — it only adds a way to re-trigger already-existing ingestion
  and surfaces an already-existing timestamp field.
