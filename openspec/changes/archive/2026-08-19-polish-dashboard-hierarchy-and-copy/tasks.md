## 1. Ticker panel header hierarchy

- [x] 1.1 In `frontend/src/components/TickerPanel/ticker-panel.css`, change
      `.ticker-panel__title` from `--text-xl` to `--text-base`, keeping
      `font-family: var(--font-display)` and `font-weight: 600` (design.md
      Decision 1).
- [x] 1.2 Run the app locally (or via Playwright screenshot) and visually
      confirm the title still reads clearly as a heading next to the
      search box and chips, not as body text — if it reads too weak,
      apply the letter-spacing/weight nudge flagged in design.md's Open
      Questions before treating this task as done.

## 2. AI insight panel value/subtext rhythm

- [x] 2.1 In `frontend/src/components/AIInsightPanel/ai-insight-panel.css`,
      tighten the vertical gap between `.ai-insight-panel__value` and its
      following `.ai-insight-panel__subtext`/`__reasoning` so they read as
      one bound unit (design.md Decision 2).
- [x] 2.2 Increase `.ai-insight-panel__item`'s `padding-bottom` from
      `var(--space-md)` to `var(--space-lg)` so separate stat blocks
      (Confidence / Sentiment / Advice) read as distinct from one another
      once task 2.1 lands.
- [x] 2.3 Verify live (Playwright screenshot on a populated ticker, e.g.
      TCB) that all of Confidence, Sentiment ("Technical Signal"), Advice,
      and the disclaimer remain fully visible with no hidden/collapsed/
      conditional state introduced — this task must include confirming
      Sentiment is still labeled as a technical proxy (rule 5) and the
      disclaimer still renders unconditionally (rule 6), per this
      project's tasks-artifact rule for any change touching this panel.

## 3. Copy tightening

- [x] 3.1 Confirm final Advice reasoning wording with the user before
      editing `ADVICE_COPY` in `AIInsightPanel.jsx` — design.md leaves
      this as an explicit open checkpoint rather than a pre-decided
      string, since it is rule-3-load-bearing text. **Resolved: user
      chose to leave the wording unchanged.**
- [x] 3.2 In `backend/app/api/insight.py`, shorten the has-history
      `confidence_basis` string per design.md Decision 3's table (leave
      the no-history branch's string unchanged).
- [x] 3.3 In `AIInsightPanel.jsx`, shorten the Sentiment subtext per
      design.md Decision 3's table, keeping both the named indicators
      (`{sentiment_inputs}`) and the "not news or market sentiment"
      disclaimer intact (rule 5).
- [x] 3.4 Apply the user-confirmed Advice reasoning wording from 3.1 (or
      leave unchanged if the user chooses not to tighten it). **No edit
      made — user chose to leave `ADVICE_COPY` unchanged.**
- [x] 3.5 Leave `INLINE_DISCLAIMER` in `AIInsightPanel.jsx` untouched
      (design.md Decision 3 — explicitly out of scope for tightening).

## 4. Unified empty state

- [x] 4.1 Identify the shared parent component that renders
      `PredictionDisplay` and `AIInsightPanel` side by side (`App.jsx` or
      equivalent) and add one shared "select a ticker" empty-state region
      implementing the new `dashboard-ui` requirement added by this
      change (`specs/dashboard-ui/spec.md`: "Unselected-ticker state
      shows one shared empty message")
      for the no-ticker-selected case (design.md Decision 4).
- [x] 4.2 Remove the now-redundant individual empty-state branch from
      `PredictionDisplay` and `AIInsightPanel` for the no-ticker case only
      — leave each component's loading/404/error/populated states
      untouched.

## 5. Test updates

- [x] 5.1 Update `frontend/src/components/AIInsightPanel/
      AIInsightPanel.test.jsx` assertions that match today's exact
      Sentiment subtext and (if changed) Advice reasoning strings to the
      new copy from tasks 3.3/3.4.
- [x] 5.2 Update `frontend/src/components/TickerPanel/TickerPanel.test.jsx`
      (and any other test) that asserts on `.ticker-panel__title`'s text
      or classes if task 1.1's change affects any test selector. **No
      existing test asserted on the title's text/classes — no change
      needed.**
- [x] 5.3 Add or update a backend test in `backend/tests/
      test_ai_insight_api.py` asserting the new `confidence_basis` string
      from task 3.2.
- [x] 5.4 Run `pytest backend/tests` and `cd frontend && npm run test`;
      confirm both suites pass before considering this change complete.
      **78 backend tests passed; 91 frontend tests passed.**

## 6. Manual verification

- [x] 6.1 Load the app locally (backend on its default port so the
      frontend's CORS allowlist — `http://localhost:5173` /
      `http://127.0.0.1:5173` only — is satisfied) and visually verify,
      via Playwright screenshot, all four changes together on a real
      ticker: title hierarchy, insight panel rhythm, tightened copy, and
      the unified empty state before any ticker is selected.
- [x] 6.2 Spot-check one searched-in (non-`TRAINING_TICKERS`) ticker's
      insight panel (N/A confidence + "Backtest this ticker" state) to
      confirm the spacing/copy changes don't break that branch's layout.
      **Verified with FPT: N/A confidence, "Backtest this ticker" button,
      and the rest of the panel all render correctly.**

## 7. Search input redesign

- [x] 7.1 Run `npm install @phosphor-icons/react` in `frontend/` (design.md
      Decision 5 — new dependency).
- [x] 7.2 In `frontend/src/components/TickerPanel/TickerSearch.jsx`,
      replace the visible `<label>Search ticker</label>` with
      `aria-label="Search ticker"` on the `<input>` itself, keeping the
      input's accessible name unchanged from a screen-reader perspective.
- [x] 7.3 Add a `MagnifyingGlass` icon (`size={16} weight="regular"`)
      inside the `.ticker-search__input` wrapper in the same file,
      positioned at the input's left inset.
- [x] 7.4 In `ticker-panel.css`, increase `.ticker-search__input`'s
      `padding-left` to clear the new icon, remove or repurpose the now-
      unused `.ticker-search__label` rule (label element no longer
      rendered), and widen `.ticker-search__input` from `12rem` to
      `16rem`.
- [x] 7.5 Verify live via Playwright screenshot at a desktop width that
      the header row reads less sparse, the search input has clear icon
      affordance, and the `@media (max-width: 480px)` stacked layout still
      works (input still full-width there per the existing rule).
      **Verified at 1280px and 375px — icon renders correctly in both,
      header reads fuller at desktop width, mobile stacks cleanly with
      the input full-width.**
- [x] 7.6 Update `TickerPanel.test.jsx` (and `TickerSearch` tests if they
      exist) that query the input via `getByLabelText(/search ticker/i)`
      — must still resolve now that the accessible name comes from
      `aria-label` instead of a `<label for>` association; run the suite
      to confirm no test broke from the label removal. **All 91 frontend
      tests pass unchanged — `getByLabelText` resolves via `aria-label`
      with no test edits needed.**

## 8. AI insight panel vertical balance

- [x] 8.1 In `frontend/src/components/ChartPanel/chart-panel.css`, reduce
      `.chart-panel`'s `height` from `22rem` to `18rem`, and its
      `@media (max-width: 480px)` height from `16rem` to `14rem` (design.md
      Decision 6). No other chart-panel property changes.
- [x] 8.2 Verify live via Playwright screenshot on TCB (full training
      history) and one searched-in ticker with shorter history that the
      candlestick chart still renders legibly at the reduced height, with
      no visual regression to the reset-zoom button or the empty/loading/
      error overlay states. **Verified on TCB and FPT — chart fully
      legible, reset-zoom button and axis labels unaffected.**
- [x] 8.3 Verify live that the empty space beside the AI insight panel is
      visibly reduced compared to the pre-Decision-6 screenshot, on both a
      populated ticker (with Advice) and a `near_gap` ticker (no Advice
      block, shorter panel). **Verified on TCB (with Advice) and FPT (N/A
      confidence + Backtest button branch) — insight panel now ends close
      to the chart panel's bottom edge in both cases.**
- [x] 8.4 Confirm no test asserts on `.chart-panel`'s height (frontend
      tests use jsdom, which doesn't compute real layout from stylesheets
      — check for any test reading `chart-panel.css`'s rule text directly,
      the way `App.test.jsx`'s Decision-14 test does for `.app-shell`) and
      update it if one exists. **No test references `.chart-panel`'s
      height — nothing to update.**

## 9. Volume histogram pane

- [x] 9.1 In `ChartPanel.jsx`, add a `HistogramSeries` (import from
      `lightweight-charts`, already a dependency) via
      `chart.addSeries(HistogramSeries, options, 1)` — `paneIndex: 1`
      creates the second pane automatically. Size it via
      `chart.panes()[1].setStretchFactor(...)` (design.md Decision 7),
      not a fixed pixel height.
- [x] 9.2 Feed the series real data in the existing history-load effect:
      `row.volume` per row from the same `historyQuery.data.rows` already
      used for the candlestick series, with each point's `color` set to
      `theme.positive`/`theme.negative` based on that session's direction
      — match whichever up/down convention `CandlestickSeries` itself
      already uses for the same session, and state that convention
      explicitly in a code comment (design.md Risk mitigation).
      **Used `close >= open` (matching CandlestickSeries' own
      upColor/downColor convention), documented in a code comment.**
- [x] 9.3 In `chart-panel.css`, grow `.chart-panel`'s height from `18rem`
      to `24rem`, and its `@media (max-width: 480px)` height from `14rem`
      to `18rem` (design.md Decision 7, user-confirmed values). **Revised
      after 9.5's live re-check to `22rem`/`16rem` — see 9.5.**
- [x] 9.4 Verify live via Playwright screenshot on TCB that the volume
      pane renders below the price pane with correct per-bar coloring
      (green sessions vs. red sessions match the candles directly above
      them) and its own axis, and that the reset-zoom button and the
      empty/loading/error overlay states are visually unaffected.
      **Verified — volume pane renders correctly with matching colors and
      its own axis; reset-zoom button unaffected after a fresh page
      load (a stale-HMR artifact briefly misplaced it mid-edit, resolved
      by reloading — not a real bug).**
- [x] 9.5 **Re-verify the AI insight panel vertical balance** (Decision
      6's concern, reopened by growing the chart back to `24rem`) — via
      Playwright screenshot, on both a populated ticker (with Advice) and
      the N/A-confidence branch (e.g. a searched-in non-training ticker).
      Confirm the gap beside the AI insight panel doesn't read as
      "unfinished" again. If it does, pause and revisit Decision 6/7's
      height values together rather than shipping a known regression.
      **The risk materialized: at `24rem`/`18rem` the gap reopened
      visibly on both TCB and FPT. Paused per this task's own
      instruction, discussed with the user, revised `.chart-panel` to
      `22rem`/`16rem` (task 9.3), re-verified live — gap now reads as
      normal breathing room on both branches. design.md/proposal.md
      updated to record `22rem`/`16rem` as the final value.**
- [x] 9.6 Add a test to `ChartPanel.test.jsx` for the new series,
      following the existing `vi.mock('lightweight-charts', ...)`
      convention in that file (wrap the histogram series' `setData` the
      way the prediction line series' `setData` is already wrapped) —
      assert volume values and per-point colors are passed correctly for
      a mix of up and down sessions.
- [x] 9.7 Run `pytest backend/tests` (expected unaffected — no backend
      change in this section) and `cd frontend && npm run test`; confirm
      both suites pass before considering this section complete.
      **78 backend tests passed (unaffected); 92 frontend tests passed
      (91 previous + 1 new volume-coloring test).**

## 10. Reset zoom for volume pane, and corrected chart height

- [x] 10.1 In `ChartPanel.jsx`'s `handleResetZoom`, add
      `volumeSeriesRef.current?.priceScale().setAutoScale(true)` alongside
      the existing `candleSeriesRef.current?.priceScale().setAutoScale(true)`
      call (design.md Decision 8) — both panes' independent price scales
      reset together. The shared time-scale reset already covers both
      panes' x-axis; no change needed there.
- [x] 10.2 Verify live via Playwright: manually zoom/drag the volume
      pane's own y-axis on a populated ticker, click "Reset zoom", confirm
      the volume pane's scale returns to auto-fit (not just the price
      pane's). **Confirmed live that the button still functions correctly
      (no errors) after the fix; the precise per-pane assertion is covered
      by the automated test in 10.5, which directly asserts on the API
      calls — more reliable than simulating a canvas price-scale drag
      through browser automation.**
- [x] 10.3 In `chart-panel.css`, change `.chart-panel`'s height from
      `22rem` to `26rem`, and its `@media (max-width: 480px)` height from
      `16rem` to `18rem` (design.md Decision 9, user-confirmed values —
      not a full match to the true side-column height, see Decision 9).
- [x] 10.4 Verify live via Playwright screenshot on TCB and FPT (or
      another N/A-confidence ticker) that: the chart (both panes) still
      renders legibly at `26rem`; the visible gap below the chart panel
      versus the true side column (`PredictionDisplay` + `AIInsightPanel`
      together, not the AI insight panel alone — this change's earlier
      mistake, per design.md Decision 9's correction) is smaller than
      before but not fully closed, and that remaining gap is treated as
      expected, not a defect to keep shrinking the chart further to chase.
      **Verified — measured live via `getBoundingClientRect()`: chart grew
      354px→418px against a 657px side column (was: gap of 303px, now:
      239px). Both TCB and FPT render legibly with the volume pane
      intact.**
- [x] 10.5 Add or update a `ChartPanel.test.jsx` test asserting
      `handleResetZoom`'s effect on the volume pane's price scale — follow
      the existing `setAutoScaleCalls` wrapping convention in that file
      (currently wraps `CandlestickSeries`'s `priceScale().setAutoScale`;
      extend the same wrapping to `HistogramSeries` so both calls are
      observable), and assert clicking "Reset zoom" triggers
      `setAutoScale(true)` on both series' price scales, not just the
      candlestick series'. **Added `candleSetAutoScaleCalls`/
      `volumeSetAutoScaleCalls` tracking arrays and extended the existing
      reset-zoom test's assertions.**
- [x] 10.6 Run `pytest backend/tests` (expected unaffected) and
      `cd frontend && npm run test`; confirm both suites pass before
      considering this section complete. **78 backend tests passed
      (unaffected); 92 frontend tests passed (14/14 in ChartPanel.test.jsx
      including the extended reset-zoom assertion).**

## 11. Reset zoom also restores the pane split

- [x] 11.1 In `ChartPanel.jsx`, define the price/volume stretch-factor
      split (`3`/`1`) as named constants near `DEFAULT_VISIBLE_SESSIONS`,
      and use them both at chart-creation time (where
      `chart.panes()[0]?.setStretchFactor(3)` /
      `chart.panes()[1]?.setStretchFactor(1)` are currently called
      directly) and in `handleResetZoom` (design.md Decision 10) — one
      definition, not duplicated magic numbers. **Added
      `PRICE_PANE_STRETCH_FACTOR`/`VOLUME_PANE_STRETCH_FACTOR`.**
- [x] 11.2 In `handleResetZoom`, add the same two `setStretchFactor` calls
      (via the new constants) alongside the existing time-scale and
      price-scale resets, so a manually-dragged pane divider returns to
      the original split too.
- [x] 11.3 Verify live via Playwright: drag the pane divider (between the
      price pane and volume pane) to change the split, click "Reset
      zoom", confirm the divider returns to its original position.
      **Playwright's available tools have no raw-coordinate mouse-drag
      primitive for a canvas element (same limitation hit in task 10.2)
      — confirmed live instead that the button still functions with no
      console errors after the fix, and that the pane split renders at
      the correct 290:97≈3:1 ratio before and after clicking Reset zoom.
      The precise "was it dragged, then restored" assertion is covered by
      the automated test in 11.4, which asserts directly on the
      `setStretchFactor` API calls — more reliable than simulating a
      canvas drag through browser automation.**
- [x] 11.4 Add or update a `ChartPanel.test.jsx` test asserting
      `handleResetZoom` calls `setStretchFactor` with the original values
      on both panes — follow the existing wrapping conventions in that
      file (e.g. wrap `chart.panes()` or the pane objects it returns,
      similar to how `timeScale()`/`priceScale()` are already wrapped) so
      the calls are observable. **Added a `stretchFactorCallsByPane`
      tracking object (wrapping `chart.panes()` the same way
      `chart.timeScale()` is already wrapped) and extended the existing
      reset-zoom test's assertions.**
- [x] 11.5 Run `pytest backend/tests` (expected unaffected) and
      `cd frontend && npm run test`; confirm both suites pass before
      considering this section complete. **78 backend tests passed
      (unaffected); 92 frontend tests passed (14/14 in
      ChartPanel.test.jsx including the extended reset-zoom assertions).**

## 12. Ticker panel title — uppercase wordmark treatment

- [x] 12.1 In `ticker-panel.css`, add `text-transform: uppercase` to
      `.ticker-panel__title` and change its `letter-spacing` from
      `-0.01em` to `0.06em` (design.md Decision 11). Do not change
      `font-size`, `font-weight`, or `font-family` — those stay as
      Decision 1 set them. Do not change the JSX text content — it stays
      "Stock Foresight" in the DOM; only the CSS transforms how it
      renders visually.
- [x] 12.2 Verify live via Playwright screenshot that the title renders
      as an uppercase wordmark, reads clearly next to the search box and
      chips, and that the accessible name is unaffected (query it via
      `getByRole('heading', { name: /stock foresight/i })` — case-
      insensitive match against the real DOM text, not the visual
      rendering). **Verified — renders as "STOCK FORESIGHT" with clear
      letter-spacing; a11y snapshot confirms `heading "Stock Foresight"
      [level=1]` (real mixed-case DOM text), no console errors.**
- [x] 12.3 Confirm no existing test asserts on the title's literal
      rendered casing in a way that would break (e.g. an exact-string
      match against uppercase output) — `TickerPanel.test.jsx` and any
      snapshot tests. Frontend tests query the DOM text node directly, so
      a CSS-only `text-transform` should not affect any existing
      assertion; verify this holds rather than assuming it. **Confirmed
      — no test references "Stock Foresight", `.ticker-panel__title`, or
      any heading query in `TickerPanel.test.jsx`; nothing to update.**
- [x] 12.4 Run `pytest backend/tests` (expected unaffected) and
      `cd frontend && npm run test`; confirm both suites pass before
      considering this section complete. **78 backend tests passed
      (unaffected); 92 frontend tests passed (unaffected).**

## 13. Ticker panel title — Fraunces + accent rule, reversing uppercase

- [x] 13.1 In `frontend/index.html`'s `<head>`, add a Google Fonts
      `<link>` for Fraunces (weights 400/600/700, matching the weights
      actually used by `--font-display` consumers) — the first time
      either the old (`Source Serif 4`) or new (`Fraunces`)
      `--font-display` value is actually loaded rather than silently
      falling back to Georgia/`ui-serif` (design.md Decision 12). Do not
      add loading for any other font family while here — out of scope
      per this decision. **Added `preconnect` hints plus the Fraunces
      `css2?family=Fraunces:wght@400;600;700` stylesheet link.**
- [x] 13.2 In `frontend/src/styles/tokens.css`, change `--font-display`
      from `'Source Serif 4', ui-serif, Georgia, serif` to `'Fraunces',
      ui-serif, Georgia, serif` (design.md Decision 12). This is a
      single-token change — do not touch `--font-body`, `--font-mono`,
      or any other token.
- [x] 13.3 In `ticker-panel.css`, remove `text-transform: uppercase`
      from `.ticker-panel__title` (added in task 12.1, reversed by
      design.md Decision 12) — title reverts to Title Case as rendered
      in the JSX ("Stock Foresight"). Keep `letter-spacing` at a value
      appropriate for the restored Title Case (revert to something close
      to Decision 1's original `-0.01em`, or another value confirmed to
      read well live — not the `0.06em` tuned specifically for the
      now-removed uppercase treatment). **Reverted to `-0.01em`.**
- [x] 13.4 In `ticker-panel.css`, add a `::after` pseudo-element on
      `.ticker-panel__title` rendering a short horizontal rule in
      `var(--color-accent)` beneath the title (design.md Decision 12) —
      sized short (e.g. a fixed width narrower than the full title, not
      spanning the whole header row), not a full-width divider.
      **Added a `1.75rem`-wide, 2px-tall rule, positioned via
      `position: relative` on the title and `position: absolute` on the
      pseudo-element.**
- [x] 13.5 Verify live via Playwright screenshot that: the title renders
      in Title Case, in Fraunces (not falling back to Georgia — confirm
      the font actually loads, e.g. via a network request check or
      visually distinguishing Fraunces' letterforms from Georgia's), with
      the accent rule visible beneath it; and that the Prediction panel's
      percentage value and each AI-insight stat's headline value (visible
      once a ticker is selected) also render in Fraunces, confirming the
      token-level fan-out is working as designed, not accidentally scoped
      to only the title. **Verified — title renders "Stock Foresight" in
      Title Case with the accent rule beneath it; network requests
      confirm both the Fraunces CSS and woff2 file returned 200; on TCB,
      the Prediction percentage and Confidence value both render in
      Fraunces' distinctive letterforms, confirming the token fan-out.**
      **Follow-up correction (same day, user-reported "still lackluster,
      can't notice it"): a Hallmark audit found the actual defect — at
      `--text-base` (15px) with weight 600, Fraunces' expressive
      character is too small to resolve, and the weight didn't contrast
      against the body's own 600-weight chip symbols/button text. Fixed
      by sizing the title up to `--text-lg` (22px, an existing type-scale
      step, no new token) and weight 700, and widening the accent rule
      from `1.75rem`/2px to `2.5rem`/3px to match. Re-verified live via
      Playwright screenshot — title now reads as the clearly largest,
      boldest element in the header row while remaining secondary to the
      chips/search per Decision 1's original hierarchy goal. All 92
      frontend tests re-confirmed passing after the change.**
- [x] 13.6 Confirm no existing test asserts on `--font-display`'s value,
      `.ticker-panel__title`'s `letter-spacing`, or any font-rendering
      detail that would break from this token change (frontend tests use
      jsdom, which doesn't compute real font rendering, so this is
      expected to be a non-issue — verify rather than assume). **Confirmed
      via grep — no test references font-display, letter-spacing,
      Fraunces, or Source Serif.**
- [x] 13.7 Run `pytest backend/tests` (expected unaffected) and
      `cd frontend && npm run test`; confirm both suites pass before
      considering this section complete. **78 backend tests passed
      (unaffected); 92 frontend tests passed (unaffected).**

## 14. No-ticker-selected state — dash placeholders, reversing the shared empty message

- [x] 14.1 In `frontend/src/App.jsx`, remove the
      `selectedTicker ? (...) : (<section className="app-shell__empty">...)`
      conditional (Decision 4) — render `<PredictionDisplay
      ticker={selectedTicker} />` and `<AIInsightPanel
      ticker={selectedTicker} />` unconditionally, the same as `ChartPanel`
      already renders unconditionally for a `null` ticker (design.md
      Decision 13).
- [x] 14.2 In `frontend/src/App.css`, remove `.app-shell__empty` and
      `.app-shell__empty-message` (no longer rendered by any component).
- [x] 14.3 In `frontend/src/components/AIInsightPanel/AIInsightPanel.jsx`,
      remove the `if (!ticker) { return null }` early return. When
      `!ticker`, render the same three-item + disclaimer layout already
      built for the loading state (reuse the existing
      `.ai-insight-panel__value--placeholder` /
      `.ai-insight-panel__label--placeholder` classes), except this
      branch shows the **real** labels ("Confidence", "Technical Signal",
      "Advice" — not `—` labels) with `—` values, since there is no
      "is this still loading" ambiguity to protect against in the
      no-ticker case the way there is for the loading case (design.md
      Decision 13, confirmed with user: show Advice's dash and the
      disclaimer always, don't omit the Advice block). **Also guarded
      `isPopulated` with `Boolean(ticker)` so the no-ticker state is never
      treated as populated (avoids remembering a height keyed by `null`).**
- [x] 14.4 In `frontend/src/components/PredictionDisplay/PredictionDisplay.jsx`,
      remove the `if (!ticker) { return null }` early return. When
      `!ticker`, render the `<h2>Prediction</h2>` title plus a `—`
      placeholder in place of the percentage/as-of/horizon block, styled
      distinctly (muted) from a real value — add a
      `.prediction-display__percent--placeholder` (or equivalent) class
      in `prediction-display.css` following the same muted-color pattern
      `ai-insight-panel.css` already uses for its own placeholders.
- [x] 14.5 Verify live via Playwright screenshot that: on initial load
      (no ticker selected), both `PredictionDisplay` and `AIInsightPanel`
      render their full layout with `—` placeholders instead of the old
      shared "Select a ticker..." message; the AI insight panel's
      disclaimer is visible in this state; selecting a ticker replaces
      the placeholders with that ticker's real loading/populated state as
      before. **Verified live at 1280px: no-ticker state shows the full
      dashboard shape (Prediction, Confidence, Technical Signal, Advice,
      disclaimer) with muted dash placeholders; selecting TCB correctly
      swaps in real populated data for all four values with no layout
      jump.**
- [x] 14.6 Update `frontend/src/App.test.jsx` (and any other test)
      asserting on the old shared "Select a ticker to see its prediction
      and AI insight." message or the `.app-shell__empty` element — those
      assertions no longer apply and should be replaced with assertions
      that both panels render their placeholder layout instead. **Updated
      both affected tests to assert on the dash-placeholder layout
      instead.**
- [x] 14.7 Update `frontend/src/components/AIInsightPanel/AIInsightPanel.test.jsx`
      and `frontend/src/components/PredictionDisplay/PredictionDisplay.test.jsx`
      for the new `ticker={null}` behavior — replace any test asserting
      `renderPanel(null)` returns an empty container with one asserting
      the placeholder layout renders instead (labels visible, `—` values,
      disclaimer visible for `AIInsightPanel`). **Both updated.**
- [x] 14.8 Run `pytest backend/tests` (expected unaffected — no backend
      change in this section) and `cd frontend && npm run test`; confirm
      both suites pass before considering this section complete. **78
      backend tests passed (unaffected); 93 frontend tests passed.**

- [x] 14.9 **Correction (added after a live flicker report, same day):**
      task 14.3's real-label no-ticker branch was reversed. Selecting a
      ticker for the first time in a session moves `AIInsightPanel`
      through no-ticker → loading → populated in quick succession — the
      no-ticker branch's real "Confidence"/"Technical Signal"/"Advice"
      labels and the loading branch's bare `—` labels are different DOM
      shapes, so the label text visibly flickered ("Confidence" → "—" →
      "Confidence") on every ticker's first selection each session.
      `PredictionDisplay` has no equivalent flicker — its `<h2>Prediction
      </h2>` title is static across every state, only the value below it
      swaps. Fixed by merging the no-ticker branch into the existing
      loading branch (`if (!ticker || insightQuery.isLoading)`) so both
      render the identical placeholder markup — real label text now
      renders only in the populated branch, preserving the "real label =
      real data has loaded" signal other code/tests/assistive tech
      already depended on. Updated
      `AIInsightPanel.test.jsx`/`App.test.jsx` assertions that expected
      real labels in the no-ticker state. Re-verified live via Playwright
      (label-text mutation trace across a fresh ticker selection): exactly
      one transition (`—` → real label), not two. **78 backend tests
      passed (unaffected); 93 frontend tests passed.**

- [x] 14.10 **Second correction (added after a follow-up "still flashes,
      but Prediction doesn't" report, same day):** 14.9 fixed the label
      text swap, but a real geometry bug remained and was still visible.
      The loading/no-ticker placeholder's three `.ai-insight-panel__item`
      blocks were all nested inside one wrapping `<div aria-hidden="true">`
      — a plain block element, not a flex participant, so
      `.ai-insight-panel`'s `gap: var(--space-lg)` (24px) never applied
      *between* those three items the way it does for the populated
      branch's items (which are direct flex children). That shaved
      ~70-100px off the placeholder's rendered height versus the real
      populated height — measured live: `455.0px → 470.6px` after this
      fix, versus `406.2px → 509.4px` (a ~103px jump) before it. This is
      what still read as a "flash" once real data landed, and explains why
      `PredictionDisplay` never exhibited it: it has no such wrapper div at
      all. **Fixed** by removing the wrapping `<div>` and moving
      `aria-hidden="true"` onto each of the three item blocks individually,
      so they stay direct children of the flex container in every state.
      The disclaimer `<p>` — previously also nested inside that same
      wrapper, and therefore hidden from screen readers while loading even
      though its text is unconditional, never-changing content (Rule 6) —
      is deliberately left OFF `aria-hidden` in this fix too, correcting
      that pre-existing a11y gap alongside the layout fix (user-confirmed:
      keep the disclaimer announced in every state, not just populated).
      Re-verified live via Playwright (geometry trace across a fresh
      ticker selection): AI insight panel's height jump (~15.6px) is now
      smaller than Prediction's own (~54.4px). 78 backend tests passed
      (unaffected); 93 frontend tests passed.

- [x] 14.11 **Third correction (user-requested, same day): make
      "Confidence"/"Technical Signal"/"Advice" real, static labels in
      every state** — reversing part of 14.9. The user asked for these
      three headings to stop participating in the loading transition at
      all, since they're section titles, not data. Changed the
      `if (!ticker || insightQuery.isLoading)` branch to render the real
      label text immediately (matching `PredictionDisplay`'s `<h2>
      Prediction</h2>`, which never changes across states) — only each
      item's VALUE (and subtext/reasoning) is still a `—` placeholder,
      each individually `aria-hidden="true"` (the disclaimer remains not
      aria-hidden, per 14.10). This retires the "real label = real data
      has loaded" signal 14.9's own comment described — tests/other code
      must now wait on a real VALUE (e.g. `findByText('Bullish')`), not
      the label, to detect "data has loaded"; updated
      `AIInsightPanel.test.jsx`/`App.test.jsx` accordingly (several
      `findByText('Technical Signal')`-as-wait-signal calls were
      superseded by waiting on a value or note instead). Removed the
      now-dead `.ai-insight-panel__label--placeholder` CSS class (no JSX
      references it after this change).
      **Separately traced and fixed the value-swap flash itself** (a
      distinct user report, same day: "still see a millisecond flicker
      changing dash to number, Prediction doesn't have it"): measured
      live via Playwright mutation trace — the dash→value swap is a single
      correct transition with no leftover double-render bug, but
      Confidence/Technical Signal/Advice's three values all resolve in
      the same render (one query) with zero CSS transition, so three
      values snapping in at once reads as more noticeable than
      `PredictionDisplay`'s single-value swap (which has the same "no
      transition" property but only changes one thing). Since the
      loading→populated transition is a full JSX-branch swap (unmount +
      remount, not the same node's text updating), a plain `transition`
      can't fire — added a `@keyframes` fade-in animation
      (`ai-insight-panel-value-in`, `var(--dur-fast)`/`var(--ease-out)`,
      opacity 0→1) on `.ai-insight-panel__value` instead, which plays on
      mount regardless of prior state. Respects
      `prefers-reduced-motion: reduce` (animation disabled), matching this
      file's existing pattern for the spinner/backtest-button transitions.
      Verified live via Playwright (`getComputedStyle` on the freshly
      mounted populated value): animation applies as expected. 78 backend
      tests passed (unaffected); 93 frontend tests passed.
