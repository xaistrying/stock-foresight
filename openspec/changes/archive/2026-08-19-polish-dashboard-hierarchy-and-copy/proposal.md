## Why

An `/opsx:explore` session (2026-08-12) walked the shipped M5/M6 dashboard
live (Playwright) against the `ui-ux-pro-max` skill's dashboard guidance and
found the underlying design-token system (OKLCH, semantic-only color, 4pt
spacing) is sound, but two presentation problems survive on top of it: (1)
the ticker panel's header gives the app's own wordmark more visual weight
than the ticker chips and search box, which are what a returning user
actually scans for first, and (2) the AI insight panel's four stacked
disclosure sentences (Confidence basis, Sentiment basis, Advice reasoning,
disclaimer) read at near-identical weight, clumping into one gray paragraph
instead of four scannable footnotes. Two smaller redundancies — a duplicated
"select a ticker" empty state shown twice side-by-side, and three
over-long hardcoded copy strings — compound the density problem. None of
this requires touching computation, the API contract, or the DB — it is a
CSS/copy/composition pass over already-correct data.

A follow-up screenshot review after those four items shipped (2026-08-12,
same day) surfaced two more presentation gaps in the same panels: the
ticker panel header still reads as sparse at desktop widths and its search
box has low visual affordance, and the AI insight panel — now visibly
tighter after the rhythm fix above — leaves noticeable empty space beside
the taller, fixed-height chart panel. Both are folded into this change
(design.md Decisions 5/6) rather than filed separately, since they're the
same "dashboard polish" thread on the same components.

## What Changes

- **Ticker panel header hierarchy**: reduce `.ticker-panel__title`'s visual
  weight (currently `--text-xl` serif — the single largest text in the
  header row) so the search box and ticker chips read as the primary
  scan target, not the wordmark. Layout/markup structure is unchanged;
  this is a `ticker-panel.css` sizing/weight change only.
- **AI insight panel value/explanation rhythm**: tighten the gap between
  each stat's headline value and its own subtext (bind as one visual
  unit) while increasing the gap between separate stat blocks
  (`.ai-insight-panel__item`), so Confidence / Sentiment / Advice / the
  disclaimer read as four distinct footnotes instead of one paragraph.
  Spacing/rhythm only — **no text is hidden, collapsed, or made
  conditionally visible**. Rule 6 already rejected a disclaimer
  visibility toggle (see `docs/M5_DASHBOARD_EXPLORE_NOTES.md`); this
  change does not revisit that.
- **Copy tightening**, each checked against what its rule requires the
  string to state (not just against how it reads):
  - Confidence basis (`backend/app/api/insight.py`): shorten the
    hit-rate basis sentence. Rule 4 requires the basis be stated, not
    that it be a full sentence.
  - Sentiment subtext (`AIInsightPanel.jsx`): shorten "Based on {inputs}
    — not news or market sentiment." Rule 5 requires the indicators be
    named AND the non-sentiment disclaimer be present — both must
    survive tightening.
  - Advice reasoning line: tighten wording only if the
    reasoning-precedes-verdict structure Rule 3 depends on is preserved.
  - Disclaimer sentence: **left unchanged** — already tight, and is the
    literal text Rule 6 requires; not touched by this change.
  - Exact final wording for each is a design.md decision to confirm with
    the user, not silently locked in during implementation.
- **Unify duplicate empty states**: the two adjacent "Select a ticker to
  see its prediction." / "Select a ticker to see its AI insight."
  messages (shown side-by-side before any ticker is selected) become one
  shared empty-state message for that column. **Reversed later in this
  change (design.md Decision 13, user feedback)** — see the
  "no-ticker-selected dash placeholders" bullet below for the replacement
  design; this bullet is left as a record of what shipped first.
- **No-ticker-selected state shows dash placeholders, not an empty
  message** (added later the same day, user-requested — reverses the
  bullet above): the shared "Select a ticker..." message is removed.
  Both `PredictionDisplay` and `AIInsightPanel` instead always render
  their full populated layout — every ticker-dependent value (Prediction
  percentage/as-of, Confidence, Technical Signal, Advice) shows a dash
  (`—`) placeholder, visually distinct (muted) from a real value, so it
  can never be mistaken for actual computed data. The disclaimer renders
  unconditionally in this state too. See design.md Decision 13.
- Existing frontend tests that assert on today's exact copy strings
  (`AIInsightPanel.test.jsx`, `TickerPanel.test.jsx`) are updated to
  match the new copy as part of this change, not left failing.
- **Search input redesign** (added after a follow-up screenshot review of
  the shipped items above): `TickerSearch.jsx`'s visible "Search ticker"
  label is replaced with an `aria-label` (still accessible, no longer
  consuming a text-row of vertical space), a `MagnifyingGlass` icon
  (`@phosphor-icons/react`, new dependency) is added inside the input for
  affordance, and the input widens from `12rem` to `16rem` so the header
  row fills more of its available space at desktop widths. See design.md
  Decision 5.
- **AI insight panel vertical balance** (same follow-up review): the
  visible empty space below the insight panel's disclaimer — caused by
  the fixed-height chart panel beside it, not a stretching bug — is
  reduced by shrinking `.chart-panel`'s height from `22rem` to `18rem`
  (and its mobile height from `16rem` to `14rem`), rather than adding
  filler content to the insight panel. See design.md Decision 6.
- **Volume histogram pane** (added later the same day, user-requested):
  the chart panel gains a volume histogram in a second pane below the
  candlesticks (standard TradingView-style layout), using
  `lightweight-charts`' existing `HistogramSeries` and multi-pane API —
  no new dependency, no backend change, since `GET
  /tickers/{ticker}/history` already returns `volume` per row and it was
  simply unused until now. Bars are colored per-session to match that
  candle's up/down direction. `.chart-panel`'s height grows from `18rem`
  to `22rem` (mobile: `14rem` to `16rem`) to fit both panes — a value
  chosen after live-verifying it doesn't reopen the vertical-balance
  concern Decision 6 above addressed (an initial `24rem`/`18rem` attempt
  did reopen it; `22rem`/`16rem` was re-verified clean). See design.md
  Decision 7.
- **"Reset zoom" also resets the volume pane** (added later the same day,
  user-requested): the button previously only reset the candlestick
  price pane's price scale, leaving the volume pane's own independent
  y-axis unaffected by a manual drag/zoom on it. Now resets both panes'
  price scales together. See design.md Decision 8.
- **Chart panel height, corrected** (added later the same day,
  user-requested, then user caught a real error in this change's own
  reasoning): Decisions 6 and 7 above compared `.chart-panel`'s height
  against the AI insight panel card *alone*, but the column actually
  beside the chart (`.app-shell__side`) renders `PredictionDisplay` **and**
  `AIInsightPanel` together. Measured live at the `22rem` those decisions
  converged on: chart = 354px, real side column = 657px — the chart was
  the *shorter* element the whole time. `.chart-panel` grows from `22rem`
  to `26rem` (mobile: `16rem` to `18rem`) — meaningfully taller, but not a
  full match to 657px (≈41rem), which would be unusually tall for a
  single-series chart. Some gap below the chart remains and is accepted,
  not chased further. See design.md Decision 9.
- **"Reset zoom" also resets the pane split** (added later the same day,
  user-requested): the horizontal divider between the price pane and the
  volume pane is user-draggable, and dragging it changes each pane's
  `stretchFactor` away from the `3`/`1` (75/25) split set at chart
  creation. "Reset zoom" now re-applies that original split alongside its
  existing time-scale and price-scale resets. See design.md Decision 10.
- **Ticker panel title — uppercase wordmark treatment** (added later the
  same day, user-requested): `.ticker-panel__title` adds `text-transform:
  uppercase` and widens `letter-spacing` to `0.06em` (from `-0.01em`) so
  it reads as an intentional wordmark, not small body text — size, weight,
  and font-family from Decision 1 are unchanged, and the underlying DOM
  text stays "Stock Foresight" (uppercase is CSS-only, not a literal text
  change), so screen readers announce it normally. See design.md
  Decision 11.
- **Ticker panel title — Fraunces + accent rule, reversing the uppercase
  treatment** (added the next day, user feedback: "I still prefer Title
  Case Header"): Decision 11's uppercase is removed (Title Case restored,
  DOM text unaffected either way). `--font-display` (a `tokens.css`
  value, so it fans out to the Prediction percentage and each AI-insight
  stat's headline value too, not just the title) changes from `'Source
  Serif 4'` to `'Fraunces'` — both user-confirmed choices after reviewing
  alternatives. A short accent-colored (`var(--color-accent)`) rule
  renders beneath the title as the new "stand out" technique, replacing
  uppercase/letter-spacing for that role. Also fixes a pre-existing bug
  surfaced in the process: neither font value was ever actually loaded
  (no Google Fonts link/`@fontsource`/`@font-face` anywhere), so
  `--font-display` has silently fallen back to Georgia/`ui-serif` since
  it was introduced — fixed for Fraunces specifically (a Google Fonts
  `<link>` in `frontend/index.html`), not generally re-litigated. See
  design.md Decision 12.

**Explicitly out of scope** (found during the same explore session, real
gaps, deliberately deferred — not silently dropped):
- Ticker chip footer / freshness-dot legibility (e.g. a green "Fresh" dot
  next to "Loaded 5d ago") — entangled with the still-open
  `docs/DISCUSSION_calendar_staleness.md` decision. Fixing the visual
  symptom here would silently pre-empt that discussion; left for whenever
  it's formally resolved as its own change.
- Chart panel candlestick *colors*: already verified correct against
  standard trading convention (green/red matches `lightweight-charts`
  defaults) — no color change needed. (This does not rule out the chart
  panel entirely — Decision 7, added later in this change, adds a new
  volume series without touching candle colors.) The dashed prediction
  point lacking a self-contained legend is real but minor and separable.
- A volume moving-average overlay line — the volume histogram added by
  Decision 7 is bars only; an MA overlay is a distinct indicator not
  requested.
- Backend/API code-quality items (duplicated XGBoost inference logic
  between `/insight` and `/prediction`, a redundant `CREATE TABLE IF NOT
  EXISTS` run on every hit-rate query, the synchronous multi-fold
  single-ticker backtest with no timeout, and the disclaimer string being
  duplicated between `AIInsightPanel.jsx` and `docs/DISCLAIMER.md`) — all
  real findings from the same session, but a behavior/performance
  concern, not presentation. Belongs in a separate proposal.
- Model quality, volume-derived features, or "buying volume" ingestion —
  a distinct, larger thread (the pooled 47.8% backtest hit-rate in
  `docs/MODEL_CARD.md`, and vnstock's available-but-unused volume
  fields) explored separately; not part of this change.

## Domain rule interactions

- **Rule 3** (volatility-relative advice): unaffected computationally.
  Advice copy tightening (if any) must keep the reasoning-before-verdict
  structure this rule's UI contract depends on.
- **Rule 4** (Confidence = backtested hit-rate, not a prediction
  interval): unaffected. The confidence_basis string is shortened, not
  changed in what it asserts — still names "backtested hit-rate," not a
  different statistical claim.
- **Rule 5** (Sentiment is a technical proxy, not real sentiment):
  unaffected. The tightened subtext must still name the computing
  indicators and the non-sentiment disclaimer — both are non-negotiable
  content, only the wording shrinks.
- **Rule 6** (no investment-advice framing; disclaimer always visible,
  no hide control): unaffected and explicitly reinforced — the value/
  explanation spacing work is designed so the disclaimer becomes *more*
  legible as its own line, not less, and no toggle or collapse is
  introduced anywhere in this change.
- Rules 1 and 2 (prediction target, log-return-to-percentage conversion)
  are not touched by anything in this change.
- The search input redesign and chart-panel height reduction (design.md
  Decisions 5/6) touch none of the six rules either — no computation,
  data, or disclosure content changes; only a control's presentation and
  one panel's fixed height.
- The volume histogram pane (design.md Decision 7) touches none of the
  six rules either — `volume` is already-fetched OHLCV data, not a new
  model input or a new disclosure; this is a chart rendering addition
  only. Explicitly not the "volume-derived features" model-input thread
  this proposal already lists as out of scope.
- The reset-zoom fixes and the corrected chart height (design.md Decisions
  8/9/10) touch none of the six rules either — no computation, data, or
  disclosure content change; bug fixes and a height correction only.
- The title wordmark treatment (design.md Decision 11) touches none of
  the six rules either — a visual-only change to the app's own title, not
  a rule-governed disclosure (Confidence/Sentiment/Advice/disclaimer).
- Decision 12 (font swap + accent rule, reversing Decision 11's
  uppercase) touches none of the six rules either — even though
  `--font-display` fans out to the Prediction percentage and AI-insight
  stat values, this changes only their typeface, not their computed
  value, wording, or visibility.
- Decision 13 (dash placeholders, reversing Decision 4's shared empty
  message) interacts with rules 4/5/6 more directly than any other
  decision in this change, but strengthens rather than weakens them: a
  dash is explicit N/A, styled distinctly (muted) from a real value, so
  it can never be mistaken for actual Confidence/Sentiment/Advice/
  Prediction data. The disclaimer (rule 6) remains unconditional in this
  state too. No computed value, wording, or per-ticker disclosure content
  changes — only what renders when there is no ticker to disclose
  anything about yet.

All six rules are honored unchanged; none require sign-off to modify,
because none are being modified — only how their required disclosures are
styled and worded.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `dashboard-ui`: one narrow **ADDED** requirement — when no ticker is
  selected, the Prediction display and AI insight panel each render
  their full populated layout with a dash (`—`) placeholder in place of
  every ticker-dependent value, rather than either panel disappearing
  behind a message. This is genuinely new behavior (no existing
  requirement covers the no-ticker-selected state at all before this
  change), not a change to any existing requirement's text. **This
  requirement replaces an earlier version of itself** — this change
  initially added (and briefly shipped) a different ADDED requirement, a
  single shared "select a ticker" message replacing both panels; that
  version is reversed per design.md Decision 13's user feedback and does
  not appear in the final spec delta. Every other requirement in
  `dashboard-ui/spec.md` (AI insight panel rendering, Sentiment/Advice/
  disclaimer visibility, ticker panel search-and-chips behavior) is
  unaffected — this change only restyles and reflows *how* that
  already-required content is presented (spacing, weight, wording),
  which sits below those requirements' behavioral granularity. No
  existing scenario's pass/fail condition changes.
- `dashboard-ui`: one **MODIFIED** requirement — "Chart panel renders
  OHLCV plus the single predicted point, no indicator overlay" is
  clarified (not substantively changed) to state explicitly that volume
  (raw OHLCV data, already named in the requirement) is not itself a
  prohibited "derived indicator overlay" alongside Ichimoku/RSI/MACD/
  Bollinger/ATR/OBV. The requirement's actual constraint — no derived
  technical indicator may be drawn — is unchanged; only its wording and
  a new scenario make the volume case unambiguous rather than left to
  interpretation, since a volume histogram is close enough to that line
  to warrant a spec-recorded reading (design.md Decision 7).

## Impact

- **Frontend only, plus one backend string**:
  - `frontend/src/components/TickerPanel/TickerPanel.jsx`,
    `ticker-panel.css` — header hierarchy, then the title's uppercase
    wordmark treatment (design.md Decision 11), then reversed to Title
    Case + Fraunces + accent rule (design.md Decision 12).
  - `frontend/src/components/AIInsightPanel/AIInsightPanel.jsx`,
    `ai-insight-panel.css` — value/subtext rhythm, copy tightening, then
    dash placeholders for the no-ticker state (design.md Decision 13).
  - `frontend/src/components/PredictionDisplay/PredictionDisplay.jsx`,
    `prediction-display.css` — dash placeholders for the no-ticker state
    (design.md Decision 13).
  - `frontend/src/App.jsx`, `App.css` — the shared empty-state branch
    (Decision 4) is added, then removed again (design.md Decision 13):
    `PredictionDisplay` and `AIInsightPanel` render unconditionally, the
    same as `ChartPanel` already does for a `null` ticker.
  - `backend/app/api/insight.py` — `confidence_basis` string only; no
    endpoint behavior, status code, or response shape change.
  - `frontend/src/components/AIInsightPanel/AIInsightPanel.test.jsx`,
    `frontend/src/components/TickerPanel/TickerPanel.test.jsx` — updated
    to match new copy.
  - `frontend/src/components/TickerPanel/TickerSearch.jsx`,
    `ticker-panel.css` — search input icon, label, width (design.md
    Decision 5).
  - `frontend/src/components/ChartPanel/chart-panel.css` — height
    (design.md Decisions 6, 7, and 9 each revise it further).
  - `frontend/src/components/ChartPanel/ChartPanel.jsx` — adds the
    volume `HistogramSeries` in a second pane (design.md Decision 7),
    then extends `handleResetZoom` to also reset its price scale
    (design.md Decision 8) and the pane split's stretch factors
    (design.md Decision 10).
  - `frontend/src/components/ChartPanel/ChartPanel.test.jsx` — new test
    for the volume series.
  - `openspec/specs/dashboard-ui/spec.md`'s "no indicator overlay"
    requirement's wording (via this change's own spec delta) — see
    Capabilities above.
  - `frontend/package.json` / lockfile — adds `@phosphor-icons/react`.
  - `frontend/src/styles/tokens.css` — `--font-display` value changes
    to Fraunces (design.md Decision 12); fans out to
    `prediction-display.css` and `ai-insight-panel.css`, both of which
    reference `var(--font-display)` — no edits to those files themselves,
    only their rendered font changes.
  - `frontend/index.html` — adds a Google Fonts `<link>` for Fraunces
    (design.md Decision 12) — the first time either the old or new
    `--font-display` value is actually loaded, rather than silently
    falling back to Georgia/`ui-serif`.
- **No database, API contract, or model changes.** **One new frontend
  dependency**: `@phosphor-icons/react` (design.md Decision 5; the
  original scope of this change had none, this was added after a
  follow-up review — see design.md Context). `lightweight-charts` (used
  by Decision 7) is already an existing dependency — no new one added
  for the volume pane. No milestone status change (M5/M6 remain shipped;
  this is a hardening pass per `openspec/config.yaml`'s "Current focus"
  note, not new scope).
