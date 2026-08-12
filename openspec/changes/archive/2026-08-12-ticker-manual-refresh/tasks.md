## 1. Chip structure change (prerequisite for everything else)

- [x] 1.1 Restructure `TickerChip.jsx`: the whole chip is currently a
  single `<button className="ticker-chip">` (see current
  `TickerChip.jsx:76-99`). A refresh control cannot be a `<button>`
  nested inside another `<button>` (invalid HTML, breaks keyboard/screen
  reader semantics — design.md Risk 2). Change the chip's root element to
  a non-interactive container (e.g. `<div className="ticker-chip">` or
  `<li>`, matching whatever the parent list markup expects) with two
  sibling interactive children: the existing select behavior (now a
  `<button className="ticker-chip__select">` wrapping the symbol +
  freshness dot + status text) and the new refresh control (1.2/1.3
  below).
- [x] 1.2 Update `ticker-panel.css` for the new two-child chip layout —
  preserve existing visual sizing/spacing for the select button so this
  is a structural change only, not a visual redesign of the chip.
- [x] 1.3 Update `TickerPanel.test.jsx` and `TickerChip`'s own tests (or
  create `TickerChip.test.jsx` if chip behavior is currently only tested
  via `TickerPanel.test.jsx`) for the new DOM structure — selecting a
  ticker via the select button, `aria-pressed`, and `data-selected`
  behavior must all still pass unchanged in substance.

## 2. Refresh action UI

- [x] 2.1 Add a "Refresh" icon button (`<button
  className="ticker-chip__refresh">`) as a sibling of the select button,
  shown only when `isLoaded` is true (spec: "Refresh action available for
  any loaded ticker" / "not offered for a never-loaded ticker").
  `aria-label="Refresh <ticker>"` and a `title` for hover — icon-only
  control, so both are required (WCAG aria-labels rule), not color/icon
  alone.
- [x] 2.2 Wire the refresh button's `onClick` to the same
  `useLoadTicker(ticker)` mutation instance already used for the
  unloaded-chip path (design.md Decision 2) — no new hook, no new
  mutation key. Do not pass an `onSelect` callback in refresh's
  `mutate()` call (unlike the unloaded-chip path) — refresh must not
  change which ticker is selected.
- [x] 2.3 Disable the refresh button whenever
  `useIsTickerLoading(ticker)` is true (design.md Decision 3) — this
  already covers "disabled during its own request" and "disabled during
  a concurrent load from another entry point" (both spec scenarios)
  since it reads from the shared per-ticker mutation state, not
  component-local state.
- [x] 2.4 Show a distinct visual state (e.g. spinning icon) on the
  refresh button while `useIsTickerLoading(ticker)` is true, so a
  disabled-but-silent button doesn't read as broken.

## 3. Refresh outcome handling

- [x] 3.1 On refresh success (`status: "ok"`), rely on
  `useLoadTicker`'s existing `onSuccess` invalidation
  (`useLoadTicker.js:44-50`) — no new invalidation logic needed. Verify
  via test that history/prediction/insight queries are invalidated
  identically whether the mutation was triggered by refresh or original
  load.
- [x] 3.2 On a non-ok status (`rate_limited` / `invalid_symbol` /
  `no_data`) or thrown error from a refresh call, reuse
  `describeLoadStatus` (from `useLoadTicker.js`) for the message shown —
  same messages already used for first-load failures (spec: "Refresh
  failure is reported distinctly, reusing existing status messages").
  Confirm no invalidation fires for non-ok statuses (spec: "Non-ok
  refresh result does not silently discard the previous data") — this
  should already hold since `onSuccess`'s early `return` on non-ok status
  is unchanged, but add a regression test for the refresh call path
  specifically.
- [x] 3.3 Decide and implement where the refresh outcome message
  displays: reusing the chip's existing `statusText` slot risks
  colliding with the select button's own status text (e.g. "Not loaded",
  "Feature computation failed") now that they're siblings (post-1.1).
  Confirm in code review that only one status message renders at a time
  per chip, with refresh's message taking precedence while its mutation
  is pending/settled-with-error.

## 4. Last-loaded-at display

- [x] 4.1 Thread `last_loaded_at` from the `GET /tickers` catalog entry
  (already returned by the backend, currently unused — see
  `backend/app/api/tickers.py:65`) down to `TickerChip` — likely already
  available via the existing `catalogEntry` prop; confirm no frontend
  type/shape currently strips it out before it reaches the chip.
- [x] 4.2 Add a small relative-time formatting utility (e.g. in
  `frontend/src/lib/`) that renders `last_loaded_at` as "Loaded Xd ago" /
  "Loaded just now" / etc., with the exact ISO timestamp available via a
  `title` attribute for the precise value on hover (design.md Decision
  5). Add unit tests for boundary cases (just now, 1 day, multiple days,
  null input).
- [x] 4.3 Render the relative-time string next to the refresh button.
  Omit it entirely when `last_loaded_at` is null (never loaded) — the
  existing "Not loaded" status text already covers that case (spec:
  "Last-loaded time absent for a never-loaded ticker").
- [x] 4.4 Confirm (via test) that after a successful refresh, the
  displayed last-loaded time updates to the new value once the
  invalidated catalog query refetches — no separate manual state needed
  if this reads directly from the (now invalidated) `GET /tickers` query
  data.

## 5. Test coverage

- [x] 5.1 Add/extend tests asserting: refresh button renders only when
  `isLoaded`; disabled while `useIsTickerLoading` is true; calls `POST
  /tickers/{ticker}/load` on click; does not call `onSelect`.
- [x] 5.2 Add a test for the "Refresh is disabled during a concurrent
  load from another entry point" scenario — trigger a load via search
  for a ticker, assert that same ticker's chip (if rendered) shows its
  refresh control disabled for the duration.
- [x] 5.3 Add a test confirming a non-ok refresh result leaves the
  previously rendered chart/prediction data untouched (per spec scenario
  "Non-ok refresh result does not silently discard the previous data") —
  likely at the `TickerPanel`/integration level rather than unit-testing
  `TickerChip` alone, since the chart/prediction panels are siblings.

## 6. Manual verification

- [x] 6.1 Live-verify against the running dev server + backend: load a
  ticker, wait, click Refresh, confirm the chart/prediction/insight
  panels update and `last_loaded_at` in the DB
  (`backend/data/app.db`, `tickers.last_loaded_at`) advances.
- [x] 6.2 Live-verify the disabled state is visually distinguishable
  (not just `disabled` attribute with no styling change) and passes a
  quick contrast/touch-target check (44×44px minimum per the UI/UX
  guidelines already applied elsewhere in this dashboard, e.g. the chart
  panel's reset-zoom button).
