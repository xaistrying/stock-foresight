## 1. Model loading at startup

- [x] 1.1 In `backend/app/main.py`'s `lifespan` handler, load the persisted
      XGBoost booster (`backend/data/models/pooled_xgb_model.json`, matching
      `training.py`'s `MODEL_PATH`) into `app.state.model` alongside the
      existing `init_db()` call. Let `xgb.Booster.load_model` raise
      uncaught on a missing/corrupt file so application startup fails
      (design.md Decision 5).
- [x] 1.2 Add a test confirming `TestClient(app)` (used as a context manager,
      per the existing pattern in `test_tickers_api.py`) fails to start when
      the model path points at a missing file (e.g. via monkeypatching the
      model path constant).
- [x] 1.3 Add a test confirming a valid model file loads successfully at
      startup and `app.state.model` is populated and reusable across
      requests without reloading.

## 2. Prediction endpoint — happy path

- [x] 2.1 Create `backend/app/api/predictions.py` with a router exposing
      `GET /tickers/{ticker}/prediction`.
- [x] 2.2 Implement the query for the ticker's most recent `features` row
      (`ORDER BY date DESC LIMIT 1`), reusing `assemble_feature_matrix`'s
      column selection (`training.FEATURE_COLUMNS`) — do not recompute any
      indicator from `ohlcv` (design.md Decision 1).
- [x] 2.3 When the row exists and `near_gap = 0`, run it through
      `app.state.model` and return `200` with `{"ticker", "as_of", "status":
      "ok", "predicted_log_return"}`. Confirm the response contains no
      `confidence_score`, `sentiment_proxy`, or `advice_text` field (design.md
      Decision 6).
- [x] 2.4 Register the new router in `backend/app/main.py` alongside the
      existing `tickers_router`.
- [x] 2.5 Add a test: clean latest row -> `200`, `status: "ok"`,
      `predicted_log_return` present and no AI-insight-panel fields present.

## 3. Persist features_computed (closes a gap found while designing M4)

- [x] 3.0 Add a migration step (in `init_db()` or a dedicated migration
      function it calls) that runs
      `ALTER TABLE tickers ADD COLUMN features_computed INTEGER` if the
      column doesn't already exist — check via `PRAGMA table_info(tickers)`
      or catch the resulting "duplicate column" OperationalError.
      `CREATE TABLE IF NOT EXISTS` has no effect on a table that already
      exists, so this is required for the change to work against the
      actual, already-populated `app.db` — not just a fresh test database.
- [x] 3.1 Add a `features_computed` column to the `tickers` table in
      `backend/app/db/schema.py` (`1` = last load's feature recomputation
      succeeded, `0` = attempted and failed, `NULL` = migration-backfilled
      only — a genuinely never-loaded ticker has no `tickers` row at all, so
      there is nothing to set to `NULL` on a fresh load; see Decision 7).
- [x] 3.2 Move the existing `UPSERT_TICKER` call to after the
      feature-computation try/except resolves; include
      `features_computed` in that same upsert. No second write.
- [x] 3.3 Add/update a `ticker_ingestion` test confirming `features_computed`
      is persisted as `1` on a successful load and `0` when
      `recompute_features_for_ticker` raises (mirroring the existing
      try/except path), and that a never-loaded ticker has **no `tickers`
      row at all** — assert the row lookup itself returns nothing
      (`cursor.fetchone() is None`), not that a row exists with
      `features_computed` set to `NULL`.

## 4. Prediction endpoint — not-loaded and fault states

- [x] 4.0 Implement the gating checks in this fixed order (design.md
      Decision 3's table and ordering note): (1) `tickers.features_computed
      = 0` -> `5xx`, evaluated before any `features`-row lookup; (2) no
      `features` rows for the ticker -> `404`; (3)/(4) latest row's
      `near_gap` -> `near_gap`/`ok`. `features_computed IS NULL` or `= 1`
      both fall through check (1) into check (2) unchanged.
- [x] 4.1 Return `404` when the ticker has zero `features` rows (check 2,
      only reached after check 1 passes). Add a test confirming this path
      never calls `load_ticker` or reaches `ticker_ingestion.mkt` (assert via
      monkeypatch/spy, matching this endpoint's read-only contract —
      design.md Decision 2).
- [x] 4.2 Return a `5xx` status when the ticker's `tickers` row has
      `features_computed = 0`, reading the column added in task 3.1. This
      check MUST run before the `features`-row lookup in 4.1 — do not
      restructure this into "check features rows, then check
      features_computed," since that ordering lets a fault be masked by
      stale `features` rows surviving a failed recomputation (design.md's
      ordering note under Decision 3).
- [x] 4.3 Add a test for the `features_computed = 0` -> `5xx` path, distinct
      from the `404` and `near_gap` tests. Include the specific regression
      case: seed `features` rows for a ticker (simulating an earlier
      successful load), then set `features_computed = 0` (simulating a later
      failed reload) — confirm the response is `5xx`, not a prediction served
      from the seeded rows.
- [x] 4.4a `features_computed IS NULL` (ticker loaded only before this
      migration — the only way to reach this state while a `features` row
      still exists), latest row `near_gap = 0` -> falls through check 1,
      responds `status: "ok"` as normal.
- [x] 4.4b Same setup, latest row `near_gap = 1` -> falls through check 1,
      responds `status: "near_gap"` as normal.

## 5. Prediction endpoint — near_gap handling

- [x] 5.1 When the latest `features` row has `near_gap = 1`, return `200`
      with `{"ticker", "as_of", "status": "near_gap"}` and no
      `predicted_log_return` field — do not call the model at all in this
      path.
- [x] 5.2 Confirm no fallback/walk-back query to an older `near_gap = 0` row
      exists anywhere in this path (design.md Decision 4).
- [x] 5.3 Add a test: latest row `near_gap = 1` -> `200`, `status:
      "near_gap"`, `predicted_log_return` absent from the response body.
- [x] 5.4 Add a test: latest row `near_gap = 1` but an older row for the same
      ticker has `near_gap = 0` -> response is still `status: "near_gap"`,
      confirming no walk-back occurs even when an eligible older row exists.

## 6. Verification

- [x] 6.1 Run `pytest backend/tests` and confirm the full suite passes,
      including all new tests from sections 1-5.
- [x] 6.2 Manually verify with `uvicorn app.main:app --reload --app-dir
      backend`: load a real ticker via the existing `POST
      /tickers/{ticker}/load`, then call `GET /tickers/{ticker}/prediction`
      and confirm the response shape matches design.md's tagged-union
      contract.
