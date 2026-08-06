## Context

`frontend/` is currently empty — this is a from-scratch build, not a
migration. The backend (M1-M4) exposes exactly two endpoints today:
`POST /tickers/{ticker}/load` and `GET /tickers/{ticker}/prediction`
(latest-row only, no history). Neither serves what a dashboard needs to
populate a ticker picker or draw a chart, so this change adds two small
read endpoints alongside the frontend build.

The model (`docs/MODEL_CARD.md`) was trained and backtested on exactly 9
tickers (`TRAINING_TICKERS` in `backend/app/ml/training.py`): TCB, VIB,
VHM, VND, MWG, HPG, MSN, VNM, SAB. Nothing at the API layer currently
stops a client from requesting a prediction for a ticker outside that
set — `GET /tickers/{ticker}/prediction` will happily serve a
`predicted_log_return` for any loaded ticker, validated or not.

## Goals / Non-Goals

**Goals:**
- Ship a working dashboard: ticker panel, chart panel, prediction
  display, reserved M6 placeholder.
- Add the minimum backend surface the dashboard needs (`GET /tickers`,
  `GET /tickers/{ticker}/history`) without touching the existing
  ingestion or prediction endpoints.
- Restrict the *prediction display* to the 9 validated tickers, closing
  the Rule 6 gap above, without restricting `/load` or ingestion.

**Non-Goals:**
- No indicator overlay (Ichimoku/RSI/MACD/etc.) on the chart in v1 —
  `near_gap` rows would render misleading indicator lines with no visual
  distinction from clean rows, and building that distinction is deferred.
- No predicted-vs-actual / track-record view — live predictions aren't
  logged anywhere yet; that's new infrastructure, not this endpoint's job.
- No free-text ticker search or arbitrary-ticker prediction display.
- No Confidence score, Advice text, or Sentiment proxy (Rules 3, 4, 5) —
  M6 scope. M5 only reserves layout space.
- No chart zoom/range controls or configurable window size — the
  300-session window is fixed.

## Decisions

### Decision 1: `GET /tickers` sources from `TRAINING_TICKERS`, not a new list
The endpoint imports `TRAINING_TICKERS` from `backend/app/ml/training.py`
as its ticker set and left-joins the `tickers` table for status
(`loaded`, `features_computed`, `last_loaded_at`) per ticker. No second
copy of the 9-ticker list is created anywhere in the codebase — training
code remains the single source of truth.

Alternative considered: duplicate the list as a config constant in the
API layer. Rejected — the two lists would drift silently if
`TRAINING_TICKERS` ever changes (e.g. a future retrain adds a 10th
ticker), and nothing would catch the mismatch since they serve different
layers of the same app.

### Decision 2: `GET /tickers/{ticker}/history` is OHLCV-only, fixed 300-session window
Returns `{ticker, rows: [{date, open, high, low, close, volume}, ...]}`
for the most recent 300 sessions in `ohlcv`, no `near_gap` field, no
indicator columns. Window size is a fixed backend constant, not a query
parameter.

Alternative considered: a `?sessions=` query param with a default and
max clamp. Rejected for v1 — nothing in the current UI plan (no zoom/pan
control) would use a variable window, so the param would be unused
surface area. Can be added later without a breaking change (adding an
optional param is additive).

Alternative considered: include `near_gap` per row so the chart could
visually mark gaps. Rejected for v1 — deferred along with the indicator
overlay decision above; scope stays OHLCV-only end to end for this
endpoint's first version.

### Decision 3: Prediction display restricted to `TRAINING_TICKERS`; `/load` stays open
The ticker panel only ever renders the 9 tickers from `GET /tickers` —
there is no free-text ticker entry in the UI. This is a *display-layer*
restriction: `POST /tickers/{ticker}/load` and `GET
/tickers/{ticker}/prediction` are unchanged and remain technically
callable for any ticker string. The frontend simply never constructs a
request for a ticker outside the fixed set.

This decision implements **Rule 6** (never frame output as investment
advice): a prediction rendered with the same confident UI chrome for a
ticker the model has no validated backtest history on would read as
advice with no basis. Restricting the *display* — not the ingestion
path — to the validated set closes that gap while leaving room for a
future milestone to load and validate additional tickers deliberately.

Alternative considered: free-text ticker input, calling `/load` on
submit. Rejected for two independent reasons: (a) `/load` is a
synchronous, potentially rate-limited live `vnstock` call — the UI would
stall for an unbounded time on every new ticker; (b) even if that were
solved, it reopens the Rule 6 gap by letting a user drive the prediction
display to an unvalidated ticker.

### Decision 4: `/load` response gains an explicit `status` field
Today `load_ticker` returns `rows_loaded: 0` for two distinct causes — a
caught `RateLimitError`, or a fetch that succeeds but returns an empty
result (invalid ticker symbol, delisted ticker, or a ticker vnstock
genuinely has no data for) — and the only way to tell them apart is
inferring from which other fields (`available_since`,
`possibly_truncated_by_tier`) are `None`. The ticker panel's
load-failure UI (tasks.md 4.4) needs to show a different message for
"rate-limited, retry later" versus "no data for this symbol" — a
distinction that already exists in `load_ticker`'s control flow but
isn't named in its return value.

This change adds `status: "ok" | "rate_limited" | "no_data"` to the
response, set explicitly at each return point in `load_ticker`. This is
a modification to the existing `ticker-data-ingestion` capability, not a
new one — see the `ticker-data-ingestion` delta spec in this change.

Alternative considered: leave the response as-is and have the frontend
show one generic "load failed, try again" message for any non-success
outcome. Rejected — it throws away signal `load_ticker` already computes
internally (the two failure branches are already separate code paths)
for no implementation savings; adding the field is a small, mechanical
change (one field, three values, one function, one call site) versus a
UI that gives users a less actionable message than the backend could
easily support.

**Note**: this decision originally assumed a fetch that succeeds but
returns zero rows would be the source of `no_data`. Testing (Decision 7)
found that's not what actually happens — a malformed symbol raises
`ValueError` directly (mapped to `"invalid_symbol"`), while a
well-formed ticker with genuinely no data raises `tenacity.RetryError`
wrapping a different `ValueError`, unwrapped via
`e.last_attempt.exception()` and mapped to `"no_data"`. The final enum
is `"ok" | "rate_limited" | "invalid_symbol" | "no_data"` — four values,
not the originally-assumed three; `no_data` survived as a name but its
actual trigger (a wrapped `RetryError`, not a bare empty result) wasn't
the one first assumed.

### Decision 5: React Query for data fetching
Chosen over SWR and over hand-rolled `useEffect` fetching. The dashboard
needs: (a) multiple distinct response shapes per endpoint (prediction's
ok/near_gap variants, load's success/rate-limited variants), and (b) a
write-then-invalidate flow — `POST /load` succeeding must invalidate and
refetch both `/prediction` and `/history` for that ticker. React Query's
mutation + query-invalidation primitives cover this directly; SWR has
weaker mutation support, and hand-rolling both cache invalidation and
loading/error states with `useEffect` is strictly more code for the same
behavior, not less.

### Decision 6: Charting library — deferred to task-time, not decided here
The proposal names "a charting library" as a new dependency but does not
pin one. Candidates: lightweight-charts (TradingView's, candlestick-native,
no React wrapper), Recharts (React-idiomatic, no candlestick primitive
out of the box), visx (low-level, more build effort). This design defers
the final choice to implementation, constrained to: must render OHLC
candles from the `/history` shape above, must not require a paid license,
must have current (non-abandoned) maintenance.

### Decision 7: `/load`'s response gains a `status` field; malformed
symbols and well-formed-but-empty tickers are now both caught, not left
to crash

Discovered while writing task 4.4 (surfacing `/load`'s failure states in
the ticker panel) — `rows_loaded: 0` alone couldn't distinguish a
rate-limited retry from a genuinely bad ticker string, and testing
found a malformed symbol wasn't even caught at all; it crashed
`load_ticker` with an unhandled `ValueError`.

Two confirmed message strings from `vnstock`'s symbol validation
("Invalid symbol. Your symbol format is not recognized!" and "Symbol
must be between 3 and 12 characters long.") are matched via a shared
`_classify_load_error` helper, returning `"invalid_symbol"` for either.
`RateLimitError`'s existing branch is unchanged apart from adding the
same `status` field for shape consistency.

**Also fixed, once confirmed**: a well-formed ticker with no real data
raises `tenacity.RetryError`, not a plain `ValueError` — confirmed live
that `e.last_attempt.exception()` returns the real underlying
`ValueError("Không tìm thấy dữ liệu...")`, and that this case is never
wrapped for the malformed-symbol case (that one stays a bare
`ValueError`), so the two remain distinguishable after unwrapping.
`load_ticker` now catches `(ValueError, RetryError)` together, unwraps
`RetryError` via `.last_attempt.exception()` before classifying, and
`_classify_load_error` gained a third match returning `"no_data"`. This
was deliberately *not* done speculatively in the same pass as the
`invalid_symbol` fix — the message string and the unwrap API were each
verified live first (matching this project's standard of testing before
writing message-based matching logic), then implemented once confirmed.

**Alternative considered**: unwrap and match on `RetryError`
speculatively without a confirmed message string, in the same pass as
the `invalid_symbol` fix. Rejected initially for that reason — implemented
in a follow-up pass once the message and the `.last_attempt.exception()`
API were both confirmed live, not guessed at.

## Risks / Trade-offs

- **[Risk]** Fixed 300-session window may be too short for tickers with
  sparse recent trading or too long to render crisply on small screens.
  → **Mitigation**: 300 is a named backend constant in one place; revisit
  after the dashboard ships and real usage is visible, no migration cost
  to change it later.
- **[Risk]** `TRAINING_TICKERS` import creates a dependency from
  `app.api` on `app.ml.training` — a module that also does model
  training I/O. → **Mitigation**: only the list constant is imported, not
  any training function; if this coupling becomes a problem, the constant
  can be hoisted to a shared config module without changing this
  endpoint's contract.
- **[Risk]** Restricting the prediction display to 9 tickers may read as
  an arbitrary limitation to a user who wants a ticker outside that set.
  → **Mitigation**: this is a deliberate Rule 6 mitigation, not an
  oversight — the ticker panel should state why (e.g. "predictions
  available for these validated tickers") rather than silently omitting
  others.
- **[Risk]** Rule 6's protection for unvalidated tickers exists only at the
  frontend display layer — `GET /tickers/{ticker}/prediction` remains
  fully callable for any ticker string at the API level. A direct API
  client bypasses the restriction entirely. **Mitigation**: accepted for
  v1 (no public deployment yet); if this API is ever exposed beyond the
  dashboard's own frontend, backend-level enforcement becomes necessary,
  not optional.
- **[Risk]** *(Resolved)* The `RetryError` gap (Decision 7) meant even a
  request against one of the 9 fixed, previously-successful tickers
  could theoretically crash `/load` ungracefully, if that ticker's data
  became temporarily unavailable from vnstock. Fixed: `load_ticker` now
  catches and unwraps `RetryError` alongside `ValueError`, returning
  `status: "no_data"` instead of crashing. `docs/KNOWN_ISSUES.md`'s
  entry is closed.
- **[Trade-off]** Deferring predicted-vs-actual tracking means the
  dashboard cannot show historical prediction accuracy inline on the
  chart in M5. Accepted — building a prediction log is real new
  infrastructure and belongs in its own change, not folded into a UI
  milestone.

## Open Questions

- Charting library choice (Decision 6) — resolve during `tasks.md` /
  implementation, not blocking design sign-off.
- Exact visual treatment for near_gap / 404 / 503 prediction states is a
  UI design detail for implementation (Hallmark skill), not a spec-level
  decision.
