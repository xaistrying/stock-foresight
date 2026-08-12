## Context

`POST /tickers/{ticker}/load` (`backend/app/services/ticker_ingestion.py`,
`load_ticker`) is unconditional and idempotent-by-upsert: it re-fetches
OHLCV from vnstock, recomputes features, and upserts `tickers.last_loaded_at`
every time it's called, with no staleness check gating the call itself.
This is not incidental — `openspec/specs/ticker-data-ingestion/spec.md`'s
"On-demand ticker load endpoint" requirement already specifies the
endpoint "works identically whether the ticker has never been loaded
before or is being reloaded," with an explicit "Reload of an
already-loaded ticker" scenario. The backend side of a refresh capability
is therefore already built and specified; nothing here changes it.

Today the endpoint is only ever reachable from two frontend call sites,
both gated on "this ticker is not yet loaded/known":

- `TickerChip.jsx:64-74` — `handleClick` only calls
  `loadMutation.mutate(...)` when `!isLoaded`; an already-loaded chip's
  click goes straight to `onSelect(ticker)`.
- `TickerSearch.jsx` — `handleSubmit` only calls `onLoad(symbol)` when the
  symbol isn't already in `knownTickers`; otherwise it resolves directly.

`GET /tickers` already returns `last_loaded_at` per ticker
(`tickers.py:32,51,65`) but no frontend component reads it today.
`useLoadTicker(ticker)` (frontend/src/hooks/useLoadTicker.js) already
wraps the load call generically — it is not itself gated on load state,
only its two current callers are — and its sibling
`useIsTickerLoading(ticker)` already exposes a per-ticker in-flight flag
via `useMutationState`, independent of which component triggered the
mutation.

This change adds a third, explicit call site for the same mutation:
a user-initiated "Refresh" action on an already-loaded ticker.

## Goals / Non-Goals

**Goals:**
- Let a user manually re-trigger `load_ticker` for a ticker that already
  has data, from the ticker panel, without reselecting/reloading the app.
- Show `last_loaded_at` somewhere visible so refreshing has a legible
  reason ("loaded 14 days ago") rather than being a bare, unexplained icon.
- Reuse the exact success/invalidation path `useLoadTicker` already
  performs on first load, so chart/prediction/insight refresh the same
  way regardless of which of the three call sites triggered the load.
- Prevent duplicate in-flight `/load` calls for the same ticker from
  repeated clicks.

**Non-Goals:**
- No scheduled/automatic refresh (cron, polling, background task). This
  stays a manual, user-initiated action only.
- No change to Fresh/Stale/Loading semantics (`useTickerFreshness.js`) —
  they continue to compare `prediction.as_of` against the ticker's own
  latest stored session, never against wall-clock "today". A future
  calendar-age indicator is explicitly out of scope for this change
  (was raised and deferred during the discussion that produced this
  proposal).
- No new backend endpoint, no change to `load_ticker`'s fetch
  parameters, error classification, or DB writes. `ticker-data-ingestion`
  gains a scenario documenting repeat-call behavior, not new behavior.
- No server-side rate limiting beyond what already exists
  (`RateLimitError` → `status: "rate_limited"`, unchanged).
- Does not touch any of the six domain rules (prediction math, log-return
  display, advice thresholds, confidence computation, sentiment framing,
  disclaimer) — this is a data-freshness/UX addition only.

## Decisions

### Decision 1: Refresh action lives on the ticker chip, not the chart panel
Placed as a small icon control on `TickerChip.jsx`, next to (not
replacing) the existing freshness dot, rather than near `ChartPanel`.
Rationale: freshness is a per-ticker property already surfaced on the
chip (the dot); refreshing is the corrective action for that same
per-ticker property, so co-locating them keeps the affordance next to
the state it changes. The chart panel only ever reflects the *currently
selected* ticker, whereas a chip exists for every ticker in the panel —
putting refresh there also lets a user refresh a ticker without
selecting it first.
**Alternative considered**: a "Refresh" button near the chart, scoped to
the selected ticker only. Rejected — it can't refresh a non-selected
ticker, and duplicates the chip's existing role as the per-ticker action
surface (load-to-select already lives there).

### Decision 2: Reuse `useLoadTicker`, no new hook or endpoint
The refresh control calls the same `useLoadTicker(ticker).mutate()` used
by the unloaded-chip path. No new mutation, no new query key, no backend
change. `onSuccess`'s existing invalidation of
`tickers`/`history(ticker)`/`prediction(ticker)`/`insight(ticker)`
(useLoadTicker.js:44-50) already does exactly what a refresh needs.
**Alternative considered**: a separate `useRefreshTicker` hook. Rejected
as needless duplication — the mutation body, success handling, and error
classification (`describeLoadStatus`) are identical; only the *caller's*
gating condition (`isLoaded` vs. always-allowed) differs, and that
belongs in the component, not a new hook.

### Decision 3: In-flight guard reuses `useIsTickerLoading`, not a new debounce
`useIsTickerLoading(ticker)` already derives "is this ticker's load
mutation pending" from React Query's mutation cache
(useLoadTicker.js:59-64), independent of caller. The refresh control is
simply `disabled` while this is true, exactly like the existing
`disabled={loadMutation.isPending}` on the chip button itself
(TickerChip.jsx:83). This fully satisfies the proposal's
"debounce/disable in-flight" requirement with existing infrastructure —
a second click while pending is inert (disabled), not queued or
throttled.
**Alternative considered**: a client-side cooldown timer (e.g. disable
for N seconds after a completed refresh) to reduce vnstock call volume
from rapid re-clicking after completion. Rejected for v1 — no evidence
of a real abuse pattern yet, and it would need a designed cooldown
duration with no clear default; the in-flight guard alone prevents the
concrete failure mode (overlapping requests for the same ticker). Can be
added later if usage shows it's needed.

### Decision 4: Refresh is available regardless of current freshness state
The action is shown whenever a ticker is loaded (`isLoaded === true`),
not only when `freshness === 'stale'`. Rationale: Fresh/Stale only
reflects internal consistency (prediction vs. stored data), never
calendar time (this was the exact gap that motivated this change) — a
ticker showing Fresh can still be calendar-stale, so gating the control
on `freshness === 'stale'` would hide it in precisely the case that
motivated the feature.
**Alternative considered**: only show refresh when `freshness ===
'stale'`. Rejected — would leave the original problem (Fresh-but-
calendar-old) with no corrective action available.

### Decision 5: `last_loaded_at` displayed as relative time, next to the refresh control
Rendered as a short relative string (e.g. "Loaded 14d ago") using the
already-fetched `catalogEntry.last_loaded_at` from `GET /tickers` — no
new API field. Placed adjacent to the refresh icon so the two read as
cause (staleness) and effect (action) together, consistent with
Decision 1's chip placement.
**Alternative considered**: showing an absolute date/time instead.
Rejected for the compact chip layout — relative phrasing ("14d ago")
communicates the same "is this old?" judgment in less space; an absolute
timestamp is available via `title`/tooltip for anyone who wants the
exact value, matching the existing hover-for-detail pattern already used
for the freshness dot's `title` attribute.

## Risks / Trade-offs

- **[Risk]** Repeated manual refreshes across many tickers could increase
  vnstock call volume beyond what M1's ingestion design anticipated. →
  **Mitigation**: the in-flight guard (Decision 3) prevents concurrent
  duplicate calls per ticker; broader rate-limiting is already handled
  server-side via the existing `rate_limited` status path, which this
  change does not alter. If real-world usage shows abuse, a cooldown
  (deferred in Decision 3) can be added without touching this change's
  core design.
- **[Risk]** Adding a second interactive control to the chip (refresh
  icon alongside the chip's own click-to-select behavior) risks a11y/
  touch-target conflicts — a chip is a `<button>`; nesting another
  clickable control inside it is invalid HTML (nested interactive
  elements) and would break keyboard/screen-reader semantics. →
  **Mitigation**: tasks.md must call out that the refresh control cannot
  be a descendant of the chip's own `<button>` — either restructure the
  chip to a non-button container with two sibling buttons (select +
  refresh), or place refresh as a sibling element next to the chip
  rather than inside it. This is an implementation detail to resolve in
  tasks.md, not a spec-level requirement change.
- **[Trade-off]** Showing refresh unconditionally (Decision 4) means the
  control appears even for a ticker refreshed seconds ago, which could
  read as always-actionable noise. Accepted — the alternative (hiding it
  based on freshness) reintroduces the exact gap this change exists to
  close, so an always-available action is preferred over a smarter but
  incomplete gating heuristic.

## Open Questions

- None blocking. The calendar-age Stale trigger and any cooldown/rate-
  limit beyond the in-flight guard were raised during scoping and
  explicitly deferred (see Non-Goals) — revisit only if the user asks
  for either in a future change.
