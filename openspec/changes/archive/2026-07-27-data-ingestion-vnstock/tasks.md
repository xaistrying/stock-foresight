## 0. Environment setup

- [x] 0.1 Create Python venv at `backend/.venv` (Python 3.10+, 3.12+ recommended
      per vnstock's requirements)
- [x] 0.2 Install dependencies: `pip install -r requirements.txt` (run from
      inside `backend/`, with `.venv` activated)

## 1. Database schema

- [x] 1.1 Create `backend/app/db/` module with a SQLite connection helper
      pointed at `backend/data/app.db`
- [x] 1.2 Add schema creation (DDL) for `ohlcv` (`ticker`, `date`, `open`,
      `high`, `low`, `close`, `volume`, primary key `(ticker, date)`)
- [x] 1.3 Add schema creation (DDL) for `tickers` (`ticker` primary key,
      `available_since`, `possibly_truncated_by_tier`, `last_loaded_at`)
- [x] 1.4 Wire schema creation to run on app startup (create tables if not
      exist)

## 2. Ingestion service

- [x] 2.0 Run `backend/scripts/verify_vnstock_tier_limit.py` and confirm no `!!`
      output before implementing 2.1–2.9. If any check fails, vendor
      behavior has drifted since 2026-07 — revisit D1–D4 before proceeding.
- [x] 2.1 Add `backend/app/services/ticker_ingestion.py` with
      `load_ticker(ticker: str)`, using `vnstock.ui.Market` per the
      project's vnstock skill (Unified UI, not Legacy API)
- [x] 2.2 Call `mkt.equity(ticker).ohlcv(start="2000-01-01", end=today,
      count=5000, source="vci")` as the single fetch — no chunking or
      walk-back
- [x] 2.3 Wrap the fetch call in try/except for
      `vnstock.core.exceptions.RateLimitError` (scaffolding only, per design
      D9 — no retry/backoff logic)
- [x] 2.4 Strip the 07:00:00 time-of-day component from returned
      timestamps and normalize to date-only ISO TEXT before storing
- [x] 2.5 Implement the >5-calendar-day gap check across consecutive
      stored sessions for the ticker; log detected gaps, do not raise or
      fail the request on them
- [x] 2.6 Compute `available_since` as `min(date)` from the fetched rows
- [x] 2.7 Compute `possibly_truncated_by_tier` as `abs(available_since -
      (end - 8y)) <= 30 days`; ensure this value never filters or blocks
      any row from being written to `ohlcv`
- [x] 2.8 Upsert fetched rows into `ohlcv` via
      `ON CONFLICT(ticker, date) DO UPDATE`
- [x] 2.9 Upsert the computed `available_since`,
      `possibly_truncated_by_tier`, and current `last_loaded_at` into
      `tickers` (same upsert path for first load and reload)

## 3. API endpoint

- [x] 3.1 Add `backend/app/api/tickers.py` with
      `POST /tickers/{ticker}/load` calling `load_ticker(ticker)`
- [x] 3.2 Register the router in the FastAPI app
- [x] 3.3 Return a response indicating rows loaded, `available_since`, and
      `possibly_truncated_by_tier` for the ticker

## 4. Tests

- [x] 4.1 Unit test: upsert on reload updates existing `(ticker, date)`
      rows without creating duplicates
- [x] 4.2 Unit test: 07:00:00 time-of-day stripped correctly to date-only
      ISO TEXT
- [x] 4.3 Unit test: gap >5 calendar days is logged but does not raise or
      fail the load
- [x] 4.4 Unit test: `possibly_truncated_by_tier` computed correctly at
      and outside the 30-day boundary, and never excludes rows from
      `ohlcv`
- [x] 4.5 Integration test: `POST /tickers/{ticker}/load` succeeds on
      first load and on reload for the same ticker (mock the vnstock
      fetch call, do not hit the live API in tests)

## 5. Documentation

- [x] 5.1 Create `docs/DATA_DICTIONARY.md` documenting the `ohlcv` and
      `tickers` schemas
- [x] 5.2 Document the 07:00:00 time-of-day quirk in
      `docs/DATA_DICTIONARY.md`
- [x] 5.3 Document the `available_since` ambiguity (true listing date vs.
      tier boundary) in `docs/DATA_DICTIONARY.md`
- [x] 5.4 Document the `possibly_truncated_by_tier` calibration caveat
      (30-day tolerance, calibrated on 2 tickers, over-flagging bias) in
      `docs/DATA_DICTIONARY.md`
- [x] 5.5 Document the count-truncates-from-end fetch behavior in
      `docs/DATA_DICTIONARY.md`, cross-referencing the vnstock skill
