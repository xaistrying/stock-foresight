## Context

M3 left three durable artifacts this design builds on directly:

- `backend/data/models/pooled_xgb_model.json` — a persisted XGBoost booster
  trained on `FEATURE_COLUMNS` (14 named indicator columns, fixed order) from
  `backend/app/ml/training.py`.
- The `features` SQLite table (`backend/app/db/schema.py`) — one row per
  `(ticker, date)`, holding the 14 indicator columns, `target`, and a
  `near_gap` flag. `near_gap = 1` rows were excluded from training entirely
  (`filter_clean_labeled`).
- `compute_rolling_hit_rate` (`backend/app/ml/backtest.py`) — already
  implements Rule 4's confidence-score definition exactly, but is not wired
  into anything.

`backend/app/main.py` currently has a single router (`tickers`, exposing only
`POST /tickers/{ticker}/load`) and a lifespan handler that calls `init_db()`.
There is no existing pattern in this repo for loading a non-DB artifact at
startup, so this design establishes that pattern for the first time.

One gap surfaced while writing this design, not carried over from M3:
`load_ticker`'s `features_computed` outcome (`backend/app/services/
ticker_ingestion.py`) is currently returned only in that call's HTTP response
body — it is never persisted anywhere. Once that response is sent, the
information is gone. This change's `5xx`-on-fault requirement (Decision 3)
cannot be implemented against a value that doesn't durably exist, so this
design also adds a small, explicit schema change to close that gap (Decision
7) rather than leaving it to be discovered mid-implementation.

This design was worked out through an explore-mode discussion that resolved
four open questions before any artifact was written; the decisions below
restate those conclusions with rationale, not fresh brainstorming.

## Goals / Non-Goals

**Goals:**
- Serve a single ticker's next-5-session prediction over HTTP, computed
  strictly from already-persisted state (trained model + persisted
  `features` row).
- Make the three possible "can't give you a normal prediction" states
  (ticker never loaded, feature computation previously failed, latest row is
  `near_gap`) explicit, distinct, and correctly categorized as either a real
  HTTP error or a routine data-availability outcome.
- Fail loud at startup if the model artifact is missing or corrupt, rather
  than at first request.

**Non-Goals:**
- Confidence, sentiment, or advice fields in the response (M6's
  `ai_insight_service.py` owns that contract exclusively; see Rule 4 note in
  Decisions below).
- Recomputing indicators live from `ohlcv` at request time.
- Triggering `load_ticker` on a cache-miss from this endpoint.
- Walking back to an older `near_gap = 0` row when the latest row is
  `near_gap = 1`.
- Batch or multi-ticker prediction.
- Any UI-facing concern (percentage conversion — Rule 2 — has no UI to apply
  to yet in this change).

## Decisions

### Decision 1: Predict from the persisted `features` row only, never recompute live

The endpoint reads the ticker's most recent `features` row and calls
`assemble_feature_matrix`-equivalent column selection against it directly. It
never re-derives Ichimoku/RSI/MACD/Bollinger/ATR/OBV from `ohlcv` inside the
request path.

**Why**: `docs/KNOWN_ISSUES.md` already documents a real bug
(`_wilder_smooth`'s short-series crash) that came from indicator computation
having edge cases not caught until M3. A second, independent
feature-computation code path inside the prediction endpoint would risk
silently drifting from `feature_engineering.py`'s stored values over time —
same inputs, two implementations, no guarantee they stay identical. Reading
the stored row is also strictly cheaper (no recomputation cost per request)
and is the only way to guarantee the fed feature vector matches what
`near_gap` was actually computed against.

**Alternatives considered**: Recomputing fresh from `ohlcv` at request time
was rejected — it would be more "real-time" in principle (a stored row could
theoretically be one load-cycle stale) but the drift risk and duplicated
logic cost were judged worse than that freshness gain, especially since
`POST /tickers/{ticker}/load` already keeps `features` current on every load.

### Decision 2: Ticker-not-loaded returns `404`; this endpoint never calls `load_ticker`

If no `features` rows exist for the ticker at all, the endpoint returns `404`
without attempting to load the ticker inline.

**Why**: `POST /tickers/{ticker}/load` (M1) is the established, sole entry
point for triggering a `vnstock` fetch — a rate-limited, multi-second,
external-API-calling, database-writing operation. Folding that into a `GET`
prediction endpoint would make a nominally lightweight read carry a much
heavier and slower contract than its verb implies, and would reintroduce
exactly the `vnstock` rate-limit exposure `load_ticker`'s own `RateLimitError`
handling already has to account for — multiplied by every consumer that
now might inadvertently trigger a load by requesting a prediction. Keeping
the endpoint a pure read also matches this repo's existing division: M1 owns
writes/ingestion, this change owns a read.

**Alternatives considered**: Inline lazy-load on cache miss was rejected for
the above reason. A `202 Accepted` + async load was also considered and
rejected as unnecessary complexity for a v1 single-ticker read endpoint — no
requirement calls for it, and it would need its own polling contract that
doesn't exist elsewhere in this API yet.

**Note**: a `RateLimitError` during a ticker's very first load attempt
produces the same outcome as a ticker that was never requested at all —
no `tickers` row, no `features` rows, `404` either way. This is existing
M1 behavior (the fetch fails before any write happens), not new risk from
this change; noted here only so a future reader doesn't mistake the
overlap for an oversight.

### Decision 3: Three-way response classification — `404` / `5xx` / `200` (tagged union)

Evaluated in this order — **not interchangeable** (see the ordering note
below the table):

| # | Check | Response | Category |
| --- | --- | --- | --- |
| 1 | `tickers.features_computed = 0` for this ticker | `5xx` | Unexpected fault — pageable |
| 2 | No `features` rows for ticker (having passed check 1) | `404` | Genuine missing resource |
| 3 | Latest `features` row has `near_gap = 1` | `200`, `status: "near_gap"`, no `predicted_log_return` | Routine, expected outcome |
| 4 | Latest `features` row has `near_gap = 0` | `200`, `status: "ok"`, `predicted_log_return` present | Routine, expected outcome |

`features_computed IS NULL` and `= 1` both pass check 1 through to check 2
(Decision 7 covers why `NULL` isn't treated as a fault).

**Why this split, not a simpler one**: the temptation is to collapse all
three "can't predict normally" states into one shape (either all as
non-2xx errors, or all as `200`-with-status). Both collapses were considered
and rejected during the explore-mode discussion:

- Collapsing `features_computed = False` into a `200`-with-status alongside
  `near_gap` was rejected because the two are not the same *kind* of thing.
  `near_gap = 1` is an expected, routine, data-driven state that will occur
  for any ticker near a real trading-calendar gap — the system is working as
  designed. `features_computed = False` means a previous computation attempt
  actually failed (an exception was caught and logged) — that is a fault in
  the system, not a property of the data, and specifically the kind of fault
  that should page/alert rather than be silently absorbed into a routine
  status value a client might not even branch on.
- Treating `near_gap = 1` as an HTTP-level error (4xx/5xx) was rejected
  because nothing is wrong with the request — the ticker is loaded, the data
  exists, the response is a legitimate, expected data-availability outcome.
  Modeling it as an error would make routine, common responses (recall:
  MODEL_CARD.md documents `near_gap = 1` covering ~35-39% of otherwise
  available rows, concentrated post-Tet) look like exceptional failures to
  monitoring and client error-handling alike.

**Response shape consequence**: the `200` response body is a **tagged union**
keyed by `status` (`"ok"` | `"near_gap"`), not one fixed schema —
`predicted_log_return` is present only when `status = "ok"`. Any consumer
(M5's frontend, in a later milestone) must branch on `status` before reading
`predicted_log_return`, rather than assuming its presence.

**Check order matters, and is not interchangeable**: the `features_computed`
gate MUST be evaluated before the `features`-row lookup (404 / near_gap / ok),
not after and not independently. `recompute_features_for_ticker` computes its
entire replacement feature series before upserting it (`feature_engineering.
py`), so when it raises, the upsert never runs and any `features` rows from
an earlier *successful* load are left in the table untouched — stale, but
present. Concretely: a ticker loaded successfully once (`features` rows
written, `features_computed = 1`), then reloaded and failing on
recomputation (`features_computed` now `0`, per task 3.2's write-after-
try/except ordering) still has those original `features` rows sitting there.
If the endpoint checked "does a `features` row exist" first, this ticker
would never reach the `5xx` branch at all — it would fall straight through to
serving `status: "ok"` or `"near_gap"` off data known to be stale relative to
the ticker's current `ohlcv`, silently masking a real, current fault behind a
routine-looking response. Checking `features_computed = 0` first closes that
gap: the fault is reported regardless of what stale rows happen to remain.
`features_computed IS NULL` (Decision 7) does not short-circuit this way — it
falls through to the ordinary `features`-row lookup, which is what lets a
migration-backfilled ticker still resolve to `404`/`near_gap`/`ok` normally.

### Decision 4: `near_gap = 1` on the latest row refuses to predict — no walk-back, no serve-with-flag

When the latest `features` row is `near_gap = 1`, the endpoint does not
predict at all (no `predicted_log_return`), and does not walk backward to an
older `near_gap = 0` row to serve a prediction from that instead.

**Why refuse rather than serve stale**: walking back to an older clean row
could be real-time-stale by up to ~78 sessions (Senkou Span B's lookback
tail, per `docs/KNOWN_ISSUES.md`'s discussion of `near_gap`'s width) during a
bad stretch. A prediction endpoint implicitly claims currency; serving a
~3-month-old prediction through what looks like a live endpoint, without
saying so, is a silent overclaim of currency that Rule 6 ("technical
observation, not investment advice framing") exists specifically to prevent.
Refusing cleanly keeps the endpoint's honesty properties simple: the response
is either current and valid, or explicitly says why not.

**Why refuse rather than serve-with-`near_gap: true`-flag**: this was
reconsidered mid-discussion and reversed. The initial instinct — "label,
don't gate," following M2's precedent of keeping `near_gap = 1` rows
queryable rather than deleting them — does not transfer cleanly here. M2's
precedent applies to *stored, historical* rows, where labeling-not-gating is
safe because a historical row never implicitly claims to be current. A live
prediction endpoint is different in the same way the walk-back case is
different: serving `predicted_log_return` next to a `near_gap: true` flag
would still risk implying the number means what it means on every other
prediction, when structurally it does not — `training.py`'s
`filter_clean_labeled` excludes `near_gap = 1` rows from training outright,
so the model has no training support for this input region at all. This is
not "less confident," it is genuinely out-of-distribution for this model.
`docs/MODEL_CARD.md`'s own framing ("this pipeline has no evidence about how
the model performs there") supports treating this as "we don't know what this
number would mean," not "here's a number, lightly discounted."

### Decision 5: Model loaded once at startup into `app.state`; missing/corrupt file fails startup

The XGBoost booster is loaded once, in `main.py`'s existing `lifespan`
handler, alongside `init_db()`:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    app.state.model = xgb.Booster()
    app.state.model.load_model(MODEL_PATH)   # raises -> app fails to start
    yield
```

**Why**: matches the existing `init_db()` pattern already in this file — one
lifespan-scoped setup step per durable dependency. A missing or corrupt model
file becomes a deploy-time signal (the app does not come up; ops notices
immediately) rather than a per-request failure mode that could be
misdiagnosed as a data problem (e.g. confused with the `features_computed =
False` case) rather than a deployment/packaging problem. Loading once also
avoids repeated file-parse cost per request.

**Alternatives considered**: lazy per-request load (rejected — defers a
knowable, static failure to an unpredictable point in traffic, and every
request would pay a repeated file-read/parse cost or need its own caching
layer to avoid that, which is strictly more complexity than a one-time
startup load for a single pooled model artifact).

### Decision 6: `confidence_score` (and all AI-insight-panel fields) excluded from this response, even though `compute_rolling_hit_rate` already exists

The response never includes `confidence_score`, `sentiment_proxy`,
`advice_text`, or any other field from the AI insight panel contract, despite
`compute_rolling_hit_rate` (Rule 4's exact definition) already existing and
being callable from M3.

**Why**: `openspec/config.yaml` already scopes this whole contract to M6's
`ai_insight_service.py` deliberately. Exposing `confidence_score` here for
convenience risks two concrete problems: (1) spec drift — M6 would either
duplicate a field this endpoint already exposes, or have to consume this
endpoint's response rather than owning its contract cleanly, and this project
has already hit exactly this failure mode once (`RateLimitError`'s import
path and `tier_floor`'s formula each having lived correctly in one file and
incorrectly in another, per prior-session history); (2) Rule 6 exposure risk
— a raw confidence float in a real, callable, curl-able API response is
exposed the moment it exists, regardless of whether any UI renders it yet.
M6 is specifically the layer that wraps this number in disclaimer/framing
before anything reads it; shipping the number a milestone early defeats that
ordering even with no UI attached.

### Decision 7: Persist `features_computed` as a new `tickers` column, not an inferred signal

`load_ticker`'s `features_computed` boolean is persisted onto the `tickers`
table as a new column, written on every `load_ticker` call. A ticker that
has genuinely never been loaded has no `tickers` row at all — there's no
column value to read, `NULL` or otherwise; that case is handled by the
`404` check (Decision 3, check 2), never by reading this column. The only
case where `features_computed` is queried and genuinely reads `NULL` is a
ticker whose only load attempt(s) happened before this column existed —
the `ALTER TABLE` migration (task 3.0) backfills existing rows to `NULL`,
since their actual outcome is unknown. This migration-backfill `NULL` is
routed the same as `features_computed = 1` (see Decision 3's ordering
note) — not because "never attempted" earns that treatment (it isn't the
case here), but because a migration-backfilled ticker's `features` row
presence is the only signal available.

**Why a stored column over inferring the fault from existing state**: the
alternative — treating "no `features` row as new as `tickers.last_loaded_at`"
as an implicit failure signal — was considered and rejected. It conflates two
different things this endpoint needs to tell apart: a ticker that has never
had feature computation attempted at all (should arguably still be a `404`-
or `near_gap`-shaped outcome, not a fault) versus one where computation was
attempted and threw an exception (a genuine fault). An explicit stored
boolean keeps that distinction unambiguous and makes the `5xx` condition a
simple, direct column read rather than a derived heuristic that could
misfire (e.g. immediately after a load, before any `features` row exists yet
for unrelated timing reasons).

**Alternatives considered**: inferring from `features` table absence/staleness
(rejected, per above — too easy to conflate "not attempted" with "attempted
and failed," and timing-dependent). A separate audit/log table recording
every load attempt's outcome was also considered and rejected as more
machinery than a single ticker-level flag justifies for v1 — nothing in this
change needs history of past attempts, only the most recent outcome.

## Risks / Trade-offs

- **[Risk]** A consumer of this endpoint could still screenshot or misuse a
  raw `predicted_log_return` (a log return, not a percentage — Rule 2 exists
  for exactly this reason) even without a `confidence_score` attached.
  **Mitigation**: none applied in this change by design — Rule 2 explicitly
  scopes to "the UI," and this change has no UI. Documented here so M5 does
  not assume the API response is display-ready; conversion is M5's
  responsibility at the point of rendering.
- **[Risk]** The tagged-union response shape (`status`-keyed, fields
  conditionally present) is more complex for API consumers than one fixed
  schema. **Mitigation**: `status` is an explicit, closed enum
  (`"ok" | "near_gap"`) documented in the spec; this is the minimum
  complexity needed to keep the three response states honestly distinct
  rather than overloading one shape or introducing misleading HTTP status
  codes for non-error states.
- **[Risk]** `5xx` for `features_computed = False` assumes some
  alerting/monitoring consumes 5xx rates; if nothing currently monitors this
  API's error rate, the "should page" intent has no effect yet.
  **Mitigation**: none in this change — no monitoring/alerting infrastructure
  exists in this repo yet. Recorded as the intent so a future
  observability milestone treats this endpoint's 5xx rate as meaningful.
- **[Trade-off]** Reading only the single latest `features` row (Decision 1
  and Decision 4 combined) means a ticker can go from `status: "ok"` to
  `status: "near_gap"` and back as new data loads shift which row is
  "latest," with no smoothing. Accepted as the simplest, most honest
  behavior for v1 — the alternative (any kind of look-back or smoothing) was
  the walk-back approach already rejected in Decision 4.

## Migration Plan

This change requires a live migration, not just a schema-file edit:
`ALTER TABLE tickers ADD COLUMN features_computed INTEGER` (task 3.0),
run idempotently against a database that may already have a populated
`tickers` table (true for this project's current `app.db`). Existing
rows default to `NULL` on migration, since their load outcome is
genuinely unknown under the old schema — not `0`, which would falsely
claim every one of them failed. Once task 3.2's reorder is in place, no
freshly-written row is ever left at `NULL`: `load_ticker`'s upsert
always sets `features_computed` to `0` or `1` on any completed database
write, first load or reload alike. `NULL` is reachable only through this
migration's backfill of pre-existing rows, not through any new load
(see spec.md's NULL-semantics scenario). Rollback: the added column can
be left in place harmlessly (SQLite has no simple `DROP COLUMN` before
3.35+; confirm SQLite version if a clean rollback is required) —
otherwise, revert the router/lifespan additions as before.

## Open Questions

None outstanding — all decisions above were resolved during the
explore-mode discussion that preceded this proposal. Naming/versioning of
individual response fields (e.g. whether to include `model_version` or an
`as_of` date field) is left to the spec and implementation as straightforward
detail, not a decision requiring sign-off.
