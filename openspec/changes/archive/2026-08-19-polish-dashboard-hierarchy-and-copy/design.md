## Context

The dashboard's design-token system (`frontend/src/styles/tokens.css`) is
already sound — OKLCH color space, semantic-only color (positive/negative/
warning reserved for real signal, never decoration), a 4pt spacing scale,
`prefers-reduced-motion` handled. This change works entirely within that
existing system for Decisions 1–4; it introduces no new tokens and no new
visual language there. It only reallocates existing type-scale steps and
spacing steps, and shortens existing copy strings. Decisions 5 and 6, added
after a follow-up screenshot review of the shipped Decisions 1–4, extend
scope slightly further: Decision 5 adds this change's only new dependency
(`@phosphor-icons/react`), and Decision 6 adjusts one more existing
component's sizing (`chart-panel.css`) beyond the two panels named in the
original proposal.

Current state, verified live via Playwright against the running app
(`/opsx:explore`, 2026-08-12):
- `.ticker-panel__title` renders at `--text-xl` (1.75rem) weight 600 serif —
  larger than `.ticker-chip__symbol` (`--text-base`, 0.9375rem) and the
  search input/button (`--text-base`), making the app's own name the
  single largest text in the header row.
- `.ai-insight-panel__item` blocks use `padding-bottom: var(--space-md)`
  (1rem) between items, while a value and its own subtext inside one item
  are separated only by the item's `gap: var(--space-2xs)` (0.25rem) —
  these two gaps are close enough in scale (1rem vs. 0.25rem, a 4x ratio)
  that with four stacked items the eye doesn't cleanly segment "which
  subtext belongs to which value."
- `PredictionDisplay` and `AIInsightPanel` each render their own
  independent empty-state message ("Select a ticker to see its
  prediction." / "Select a ticker to see its AI insight.") when no ticker
  is selected, in two adjacent boxes.

Current state, verified live via Playwright after Decisions 1–4 shipped
(follow-up review, 2026-08-12):
- The ticker panel header still reads as sparse at desktop widths: the
  title demotion (Decision 1) freed vertical space that the search box
  doesn't fill, and `TickerSearch.jsx`'s visible "Search ticker" label
  above a plain `12rem`-wide bordered input reads as a low-affordance,
  under-designed control next to the now-prominent ticker chips.
- The AI insight panel sits in `.app-shell__main`'s CSS grid next to the
  chart panel (`align-items: start`, so the insight column is not
  stretched — it renders at its own intrinsic height). The chart panel has
  a fixed `height: 22rem` (`chart-panel.css`); the insight panel's three
  stat blocks + disclaimer render shorter than that, leaving visible empty
  space below the disclaimer that reads as unfinished, most noticeably for
  a `near_gap` ticker (no Advice block) or in general once Decision 2's
  tighter rhythm reduced the panel's total height further.

## Goals / Non-Goals

**Goals:**
- Rebalance visual weight in the ticker panel header so chips + search
  (the actual navigation) read as primary, the wordmark as secondary.
- Make the AI insight panel's four disclosure blocks (Confidence,
  Sentiment, Advice, disclaimer) read as visually distinct footnotes
  rather than one paragraph, via spacing/rhythm only.
- Shorten three specific copy strings without weakening what rules 3/4/5
  require them to state.
- Collapse two duplicate empty-state messages into one.
- Give the search input real affordance (icon, accessible-but-not-visible
  label) and let it and the header row fill their available space instead
  of reading as sparse (Decision 5).
- Reduce the visual height mismatch between the chart panel and the AI
  insight panel without inventing filler content (Decision 6).
- Add a volume histogram pane below the price chart, rendering data the
  API already returns but the chart doesn't display today (Decision 7).

**Non-Goals:**
- Not changing any token *color, spacing, or type-scale* value in
  `tokens.css` (Decisions 1–10 only reallocate which existing step each
  element uses; no new color/spacing/type-scale step is introduced
  anywhere in this change). **Decision 12 is the sole exception**: it
  changes `--font-display`'s value (a font-family swap, not a color/
  spacing/type-scale step) — see Decision 12 for why this is scoped as a
  deliberate, singular exception rather than a pattern this change
  otherwise establishes.
- Not touching the freshness dot / chip footer "Loaded Nd ago" legibility
  — deliberately deferred to `docs/DISCUSSION_calendar_staleness.md`'s own
  resolution, not pre-empted here.
- Not touching chart panel colors, legend, or the dashed prediction point
  — Decision 6 touches only `.chart-panel`'s height, nothing else about it.
  Decision 7 is additive (a new series), touching neither the candle
  colors nor the prediction line.
- Not adding a volume moving-average overlay or any other new indicator —
  Decision 7 is the raw volume bars only.
- Not feeding volume into the XGBoost model or any prediction/backtest
  computation — Decision 7 is a chart rendering addition of already-
  fetched data, unrelated to the "volume-derived features" thread flagged
  out of scope in this change's proposal.md.
- Not adding, removing, or making conditional any disclosure required by
  rules 4/5/6 — Confidence basis, Sentiment basis + indicator names, and
  the disclaimer all remain unconditionally visible; only their size,
  weight, spacing, and wording change.
- Not touching backend computation, response shape, or status codes
  anywhere — the one backend edit (`confidence_basis` string) is a string
  literal change only.
- Not adding decorative-only content to the AI insight panel to fill
  vertical space (Decision 6 explicitly rejects this).

## Decisions

### Decision 1: Ticker panel title — demote to `--text-base`, weight 600

`.ticker-panel__title` changes from `--text-xl` (1.75rem) to `--text-base`
(0.9375rem), keeping `font-family: var(--font-display)` and weight 600 so
it stays visually distinct from body text (still serif, still bold) while
no longer out-scaling the chips and search box beside it. This is a new
UI-hierarchy decision, not covered by any of the six domain rules — it
does not touch what data is shown or how it's computed, only how the
existing "Stock Foresight" label is sized.

Alternative considered: relocate the title out of the header row entirely
(e.g. into a slim top bar). Rejected — larger structural change than this
polish pass scopes to; a sizing change achieves the same hierarchy result
with a one-line CSS edit and no markup/layout restructuring.

### Decision 2: AI insight panel — bind value+subtext, separate items

Two paired spacing changes inside `ai-insight-panel.css`:
- Reduce the effective visual gap between `.ai-insight-panel__value` and
  its own `.ai-insight-panel__subtext`/`__reasoning` (tighten line-height
  and/or the item's internal `gap`) so they read as one unit.
- Increase `.ai-insight-panel__item`'s `padding-bottom` (currently
  `--space-md`, 1rem) to `--space-lg` (1.5rem) — an existing token step,
  not a new one — so the boundary between stat blocks reads more clearly
  once the internal value/subtext gap shrinks.

This is a rhythm/hierarchy decision, not a content decision — it does not
add, remove, or gate any of rules 4/5/6's required text. The disclaimer
(rule 6) keeps its own `border-top` separator and `padding-top: var(
--space-md)`, unchanged, since it's already visually set apart from the
three stat items above it.

### Decision 3: Copy tightening — exact strings

Each candidate is checked against the specific fact its governing rule
requires the string to state, not against how it reads:

| Location | Current | Proposed | Rule requirement preserved |
|---|---|---|---|
| `insight.py` `confidence_basis` (has-history branch) | "Hit-rate over the ticker's most recent 60 backtested predictions." | "60-prediction backtested hit-rate." | Rule 4: basis must name it as backtested hit-rate, not a statistical interval. Both do. |
| `insight.py` `confidence_basis` (no-history branch) | "No backtested predictions for this ticker yet — needs more price history to backtest." | unchanged — already states the actionable reason; no length problem here | Rule 4: N/A must not read as a fabricated number. |
| `AIInsightPanel.jsx` sentiment subtext | "Based on {inputs} — not news or market sentiment" | "{inputs} — not news or market sentiment" | Rule 5: indicators must be named inline (kept via `{inputs}`) AND the non-sentiment disclaimer must be present (kept verbatim). |
| `AIInsightPanel.jsx` `ADVICE_COPY` reasoning lines | "Move exceeds typical volatility to the upside" / "...downside" / "Move is within normal volatility range" | Left as a design checkpoint, not pre-decided here — see Open Questions. Rule 3 requires the reasoning-before-verdict structure be kept; any tightened wording must still state the volatility-relative reasoning, not just show the verdict alone. | Rule 3. |
| `AIInsightPanel.jsx` `INLINE_DISCLAIMER` | "Technical observation from a backtested model — not a forecast, not investment advice." | **Unchanged.** | Rule 6 — this is the literal required disclaimer text; not a candidate for tightening in this change. |

The Advice reasoning lines are intentionally left as an open checkpoint
(see below) rather than pre-committed, since shortening a
rule-3-load-bearing sentence without the user's explicit sign-off on
final wording risks silently weakening what the UI states.

### Decision 4: Unified empty state

> **Reversed by Decision 13** (added after this shipped and was
> reviewed live): the user preferred both panels to always render their
> full layout with dash placeholders rather than either panel
> disappearing behind a shared message. Decision 4's shared-message
> branch is removed; see Decision 13 for the replacement design. This
> section is left in place as a record of what was tried first and why.

`PredictionDisplay` and `AIInsightPanel` currently render independent
empty-state branches. This change adds one shared empty-state message
rendered once by their common parent when no ticker is selected, replacing
both components' individual "Select a ticker..." branches for that
specific (no ticker) case only — each component's other states (loading,
404, error, populated) are untouched and still rendered independently by
each component as today. Unlike Decisions 1–3, this is a genuinely new
piece of specified behavior (no existing requirement covers the
no-ticker-selected empty state), so it is captured as an ADDED requirement
in this change's `specs/dashboard-ui/spec.md` delta rather than left
spec-silent.

### Decision 5: Search input redesign — icon affordance, drop visible label, widen input

`TickerSearch.jsx`'s visible `<label>Search ticker</label>` above the input
is replaced with `aria-label="Search ticker"` on the `<input>` itself —
still an accessible name (WCAG `form-labels`/`input-labels` requires an
accessible name, not necessarily a *visible* one when the icon + placeholder
already communicate the control's purpose). This removes a full text-row of
vertical rhythm from the header that wasn't earning its place once Decision
1 already demoted the title beside it.

A `MagnifyingGlass` icon (`@phosphor-icons/react`, `size={16}
weight="regular"`) is added inside the `.ticker-search__input` wrapper,
absolutely positioned at the input's left inset with the input's
`padding-left` increased to clear it — the standard icon-affordance search
pattern, breaking up the plain bordered-rectangle look.

`.ticker-search__input`'s `width` increases from `12rem` to `16rem` — still
a fixed step (a fluid full-width input would look odd stacked above a
fixed-width "Load" button), but wide enough that the header row fills more
of its available space at desktop widths. `.ticker-panel__header`'s
existing `flex-wrap`/`justify-content: space-between` behavior and the
`@media (max-width: 480px)` stacking rule are both unchanged.

**New dependency**: `@phosphor-icons/react` (user-confirmed acceptable —
first icon usage in the codebase; no other component currently needs an
icon library, so this establishes it for future use per the
`ui-ux-pro-max` skill's default icon recommendation).

Domain rules: unaffected. Ticker search/resolution behavior, loading
states, and error messages (all covered by `dashboard-ui/spec.md`'s
existing search requirements) are unchanged — only the input's visual
presentation and its label's accessibility binding change.

### Decision 6: AI insight panel vertical balance — shrink the chart panel, no filler content

> **Correction (added alongside Decisions 8/9, same day):** this decision
> and Decision 7's height re-check both compared `.chart-panel` against
> the AI insight panel card *alone*. That comparison was wrong — per
> `App.jsx`, `.app-shell__side` (the column beside the chart) renders
> `PredictionDisplay` **and** `AIInsightPanel` stacked together, not the
> AI insight panel by itself. Measured live: at the `22rem` (354px) height
> this decision and Decision 7 converged on, the real side column
> (Prediction card + `--space-lg` gap + AI insight card) is 657px tall —
> the chart was actually the *shorter* element the whole time, not the
> taller one these decisions were shrinking it to match. See Decision 9
> for the corrected sizing. Decision 6's actual code change (verified
> live at the time) did visually tighten the gap versus the pre-existing
> `22rem`→`18rem` shrink — the mistake was in the comparison target, not
> in whether shrinking reduced *a* gap.

Verified via `chart-panel.css`: `.chart-panel` has a fixed `height: 22rem`,
and `.app-shell__main`'s `align-items: start` (`App.css`) means the AI
insight panel column is *not* being stretched to match it — it already
renders at its own intrinsic (shorter) height. The empty space seen live is
therefore not a stretching bug; it is a real content-density mismatch
between a 22rem chart and a shorter three-stat panel, one that also varies
by ticker state (a `near_gap` ticker has no Advice block at all).

**Rejected approach**: adding content to the insight panel to fill the gap
(e.g. restating the "As of" date already shown in the adjacent Prediction
card, or a compact ticker-meta summary). This would be decorative filler
with no informational value beyond what's already displayed elsewhere,
conflicting with this project's existing anti-filler bias (the M5 explore
notes' rejection of a disclaimer-visibility toggle for the same "don't add
UI just to look busier" reason).

**Chosen approach**: reduce `.chart-panel`'s fixed height from `22rem` to
`18rem` (and its `@media (max-width: 480px)` height from `16rem` to
`14rem`, scaled proportionally) — still comfortably legible for a ~3-month
candlestick view, and close enough to the insight panel's typical rendered
height that the remaining gap reads as normal breathing room rather than
"unfinished." Shrinking the taller sibling is a one-line height edit on a
single component, versus growing or restructuring three independent,
already-correctly-sized stat blocks (which would reopen Decision 2's
already-verified rhythm work).

This is a `chart-panel.css` height change only — it does not touch chart
colors, the legend, or the dashed prediction point (all already out of
scope per the original proposal's "Explicitly out of scope" list), and does
not touch any AI insight panel file at all.

### Decision 7: Volume histogram pane below the candlestick chart

`ChartPanel.jsx` adds a `HistogramSeries` (`lightweight-charts`, already a
dependency) in a second pane below the existing candlestick price pane, via
`chart.addSeries(HistogramSeries, options, 1)` — v5's `paneIndex` parameter
creates pane 1 automatically, no separate `addPane()` call needed. The
volume pane is sized as a fraction of total chart height via
`chart.panes()[1].setStretchFactor(...)`, not a fixed pixel height, so it
scales with `.chart-panel`'s own height (including its
`@media (max-width: 480px)` step) rather than needing its own breakpoint
logic.

Each bar's color matches that session's candle direction —
`theme.positive`/`theme.negative` (already read by `readChartTheme()` for
the candlestick series) applied per-point via the histogram series' `color`
data field, not a single flat series-level color. Volume data comes from
the same `GET /tickers/{ticker}/history` rows already fetched for the
candlestick series (`row.volume` — present in the API response and typed in
`frontend/src/api/tickers.js`, confirmed unused in the frontend today). No
volume moving-average overlay — out of scope per explicit user direction;
only the bars themselves.

**Height**: `.chart-panel`'s height grows from `18rem` to `22rem` (mobile:
`14rem` to `16rem`) to fit both panes without compressing the price pane.
`24rem`/`18rem` was tried first and user-confirmed as an initial value, but
live Playwright verification (tasks.md 9.5) showed it reopened the exact
gap Decision 6 had closed — the AI insight panel column ended visibly
short of the chart panel's bottom edge on both a populated ticker and the
N/A-confidence branch. `22rem`/`16rem` was chosen instead after that live
check: still enough room for both panes to read clearly, and close enough
to the insight panel's typical height (on both branches) that the
remaining gap reads as normal breathing room again, matching Decision 6's
original bar. This is the concrete outcome of the required re-verification
this decision called for, not a value chosen without checking.

> **Correction (added alongside Decisions 8/9, same day):** as with
> Decision 6 above, this re-check compared `.chart-panel` only against the
> AI insight panel card, not the true side column (`PredictionDisplay` +
> `AIInsightPanel` together, per `App.jsx`/`App.css`'s `.app-shell__side`).
> Measured live at `22rem`, the real side column is 657px vs. the chart's
> 354px — the chart was under-sized relative to the correct comparison,
> not over-corrected. See Decision 9.

Domain rules: unaffected. No computation, no data change — `volume` is
already fetched and returned by the existing `GET
/tickers/{ticker}/history` endpoint; this only renders a field already in
the response. Not the "volume-derived features"/"buying volume ingestion"
thread flagged out of scope in this proposal's original "Explicitly out of
scope" list — that thread is about feeding volume into the XGBoost model as
a training input; this is chart display of already-fetched data, entirely
separate.

### Decision 8: "Reset zoom" also resets the volume pane's price scale

`ChartPanel.jsx`'s `handleResetZoom` currently resets the shared time scale
(`setDefaultVisibleRange`, which affects both panes since they share one
x-axis) and the candlestick series' own price scale
(`candleSeriesRef.current?.priceScale().setAutoScale(true)`). It does not
reset the volume pane's own price scale — added in Decision 7, and it has
its own independent y-axis (pane 1's price scale, distinct from the
candlestick pane's). If a user drags/zooms specifically on the volume
pane's y-axis, "Reset zoom" today undoes that for the price pane but not
for the volume pane.

**Fix**: add `volumeSeriesRef.current?.priceScale().setAutoScale(true)`
alongside the existing candlestick reset in `handleResetZoom`, so both
panes' independent price scales return to auto-fit together, not just the
price pane's. The shared time-scale reset already covers both panes'
x-axis, so this only needs to add the missing y-axis call for pane 1.

Domain rules: unaffected — this is a bug-fix-shaped completion of Decision
7's own reset-zoom behavior, not new scope; no computation or data change.

### Decision 9: Chart panel height, corrected — `26rem`

Decisions 6 and 7's height re-checks both compared `.chart-panel` against
the AI insight panel card alone, not the true side column it actually sits
beside (`.app-shell__side` renders `PredictionDisplay` **and**
`AIInsightPanel` together, per `App.jsx`). Measured live at the `22rem`
those decisions settled on: chart = 354px, real side column (Prediction
card + `--space-lg` gap + AI insight card) = 657px — the chart was
actually the shorter element, the opposite of what Decisions 6/7 believed
they were correcting for.

Fully matching 657px would require roughly a `41rem` chart — unusually
tall for a single-series candlestick+volume view relative to typical
trading-dashboard conventions, and a much larger jump than intended.
**Chosen**: grow `.chart-panel` from `22rem` to `26rem` (mobile: `16rem` to
`18rem`) — meaningfully taller without stretching to an oversized chart
just to erase all remaining whitespace next to a much taller sidebar. Some
gap below the chart panel is expected and accepted at this height; per
Decision 6's original rejection of decorative filler, no content is added
to either side purely to close it further, and no further shrinking of the
chart is planned to chase full parity — that goal is retired as
unachievable at a reasonable chart height, replacing Decisions 6/7's
mistaken premise that the chart was ever the taller element.

Domain rules: unaffected — a height-only correction, no computation or
data change.

### Decision 10: "Reset zoom" also resets the pane split (stretch factors)

`lightweight-charts`' default pane divider — the horizontal line between
the price pane and the volume pane — is user-draggable, and dragging it
changes each pane's `stretchFactor` away from the `3`/`1` split set at
chart creation (`chart.panes()[0]?.setStretchFactor(3)` /
`chart.panes()[1]?.setStretchFactor(1)`, Decision 7). `handleResetZoom`
(already extended in Decision 8 to reset the volume pane's price scale)
does not reset a manually-dragged pane split back to that original ratio.

**Fix**: `handleResetZoom` re-applies the same `setStretchFactor(3)`/
`setStretchFactor(1)` calls used at chart creation, restoring the original
75/25 price/volume split alongside the existing time-scale and price-scale
resets. The literal `3`/`1` values should be defined once (e.g. named
constants near `DEFAULT_VISIBLE_SESSIONS`) and reused at both the
creation site and in `handleResetZoom`, not duplicated as magic numbers in
two places.

Domain rules: unaffected — a bug-fix-shaped completion of "Reset zoom"
resetting everything a user can manually adjust on this two-pane chart,
the same reasoning Decision 8 already established for the volume pane's
price scale.

### Decision 11: Ticker panel title — uppercase wordmark treatment

Decision 1 resized `.ticker-panel__title` from `--text-xl` to `--text-base`
and its Open Questions noted the demoted size was verified live as
sufficient without further treatment. A follow-up polish request asked for
the title to read more intentionally as a wordmark rather than as small
body text sitting at the same size as the chip symbols and search input
beside it.

`.ticker-panel__title` adds `text-transform: uppercase` and widens
`letter-spacing` from `-0.01em` to `0.06em` — size (`--text-base`), weight
(600), and font-family (`--font-display`, Source Serif 4) are all
unchanged from Decision 1. Uppercase is applied via CSS `text-transform`,
not by changing the underlying JSX text ("Stock Foresight" stays the DOM
text content) — screen readers announce the real text node, not the
visually-transformed uppercase rendering, avoiding the letter-by-letter/
acronym-style announcement some assistive tech applies to literal all-caps
characters in markup. No accessible-name change; no test relying on the
title's visible casing should need updating since the underlying text is
unchanged.

Domain rules: unaffected — a visual-only treatment of the app's own
wordmark; no data, computation, or disclosure content touched.

### Decision 12: Ticker panel title — Fraunces + accent rule, reversing the uppercase treatment

Decision 11's uppercase wordmark treatment is reversed after user feedback:
the title reverts to Title Case ("Stock Foresight" as originally rendered),
and stands out via a new display font and a small accent-colored rule
instead.

**Font swap**: `--font-display` changes from `'Source Serif 4', ui-serif,
Georgia, serif` to `'Fraunces', ui-serif, Georgia, serif`. This is a
`tokens.css` change, not scoped to just the title — `--font-display` is
also used by `.prediction-display__title`/`.prediction-display__percent`
(`prediction-display.css`) and `.ai-insight-panel__value`
(`ai-insight-panel.css`), so all three pick up Fraunces too. Checked live
(`grep` across every component stylesheet): no other component currently
overrides `font-family` away from `var(--font-display)`, so this is a
single-token, whole-app-consistent swap, not a title-only special case —
the Prediction percentage and each AI-insight stat's headline value will
also render in Fraunces after this change, not just the app title.

**A pre-existing bug surfaced during this decision, explicitly deferred**:
neither the old `'Source Serif 4'` nor the new `'Fraunces'` is actually
loaded anywhere in the app (no Google Fonts `<link>`, no `@fontsource`
package, no `@font-face` rule) — `--font-display` has been silently
falling back to `ui-serif`/Georgia in every browser since it was
introduced. This decision fixes that gap **for Fraunces specifically**
(task 13.1 adds the Google Fonts link), since shipping a named font
swap that still silently falls back to Georgia would defeat the purpose
of this decision — but does not retroactively add loading for any other
missing font family. The user explicitly declined a general fix "while
in here"; this is the minimum needed to make Decision 12 itself correct.

**Title Case restored**: `.ticker-panel__title` removes
`text-transform: uppercase` (added in Decision 11) — the DOM text was
never changed ("Stock Foresight" throughout), so no accessible-name or
test impact either direction.

**Accent rule**: a `::after` pseudo-element on `.ticker-panel__title`
renders a short horizontal rule in `var(--color-accent)` beneath the
title — the same accent token used for selection/focus elsewhere
(`tokens.css`'s existing "restrained blue, used for selection/focus, not
decoration" accent), not a new color. Per that token's own documented
constraint (reserved for interactive signal, not decoration), this is a
deliberate, narrow exception: the rule's purpose is to give the app's own
identity mark a fixed visual anchor, functionally analogous to how the
accent already marks the selected ticker chip — not arbitrary decoration.
Sized short (aligned to the width of the title's first word or a fixed
short measure, not full title width) to read as an underline accent, not
a full-width divider competing with the header row's other elements.

Domain rules: unaffected — a visual-only treatment of the app's own
wordmark and a design-token swap; no data, computation, or disclosure
content touched, and the accent token's existing semantic scope (signal,
not decoration) is preserved in intent even as this is a narrow exception
to its literal usage today.

### Decision 13: Unselected-ticker state, reversed — dash placeholders instead of a shared empty message

Decision 4's shared "Select a ticker to see its prediction and AI
insight." message (rendered once by `App.jsx` in place of both
`PredictionDisplay` and `AIInsightPanel` when no ticker is selected) is
reversed after user feedback: both panels should always render their
full layout, with a dash (`—`) placeholder standing in for every
ticker-dependent value instead of either panel disappearing.

**Why reversed, not just extended**: Decision 4 was framed as removing a
redundancy (two adjacent "select a ticker" messages). The user's
follow-up preference is a different, incompatible layout goal — keep the
dashboard's shape stable at all times (labels and structure always
visible) rather than collapsing to a message box. These two goals can't
both be satisfied by the same markup, so Decision 4's shared-message
branch is removed entirely rather than kept alongside this one.

**Scope**: both `PredictionDisplay` and `AIInsightPanel` (confirmed with
the user — not just the AI insight panel alone), so the two panels stay
visually consistent with each other, the same way Decision 4 originally
wanted them consistent by sharing one message. Concretely:
- `PredictionDisplay`'s `!ticker` early return is removed; it renders its
  `<h2>Prediction</h2>` title plus a dash placeholder for the percentage/
  as-of/horizon block.
- `AIInsightPanel`'s `!ticker` early return is removed; it renders all
  three stat blocks (Confidence, Technical Signal, Advice) each with a
  dash placeholder value, plus the disclaimer (unconditional, matching
  its already-unconditional visibility whenever a ticker *is* selected —
  rule 6 is not weakened by this state existing).
- `App.jsx`'s `selectedTicker ? (...) : (<section className="app-shell__empty">...)` branch is removed — both components render unconditionally, the same as the chart panel already does today (`ChartPanel` never disappears for a `null` ticker; it shows its own empty state internally). This makes the three ticker-scoped panels consistent with each other in how they handle "nothing selected" — none of them unmount, all render an internal placeholder state.

**Placeholder styling — reuses this project's own prior art**: an
unrelated bug fix in this same working session (AI insight panel loading-
state height fluctuation) already established the pattern this decision
needs — render the exact populated DOM shape with a dimmed, explicit `—`
in place of a value, never a shimmering skeleton or fabricated-looking
number. That fix added `.ai-insight-panel__value--placeholder` /
`.ai-insight-panel__label--placeholder` (muted color, real markup
position) specifically so a placeholder can never be mistaken for real
data. This decision reuses those same classes for the no-ticker case
(one more reason to show a dash, not a fabricated-looking placeholder
number) and adds the equivalent for `PredictionDisplay`
(`.prediction-display__percent--placeholder` or similar).

**Domain rule interaction**: rules 4/5/6 require Confidence/Sentiment/
Advice to reflect real computed data or an explicit N/A, never a
fabricated stand-in that could pass as real. A dash is explicit N/A by
construction (not a number, not a directional word) and is additionally
styled distinctly (muted) from a real value — stricter than what the
rules require, not a weakening of them. The disclaimer remains
unconditional in every state, including this one, reinforcing rule 6
rather than testing its edge.

Domain rules: unaffected by the reversal itself — this changes only
which markup renders when no ticker is selected, not any computed value,
wording, or disclosure content for a selected ticker.

> **Correction (added after a live flicker report, same day):** this
> decision's `AIInsightPanel` no-ticker branch originally rendered the
> *real* "Confidence"/"Technical Signal"/"Advice" labels with `—` values
> — reasoned at the time as safe, since there's no "is this still
> loading" ambiguity to protect against with nothing in flight. That
> reasoning was correct in isolation but missed the transition: selecting
> a ticker for the first time in a session moves `AIInsightPanel` through
> no-ticker → loading → populated in quick succession, and the no-ticker
> branch's real labels vs. the loading branch's bare `—` labels are
> different DOM shapes — the label text visibly flickered ("Confidence"
> → "—" → "Confidence") on every ticker's first selection each session.
> `PredictionDisplay` has no equivalent flicker (confirmed live) because
> its `<h2>Prediction</h2>` title is static across every one of its
> states; only the value below it swaps. **Fixed** by merging the
> no-ticker branch into the existing loading branch
> (`if (!ticker || insightQuery.isLoading)`), so both render the
> identical placeholder markup and only the populated branch ever shows
> real label text — preserving the "real label = real data has loaded"
> signal this file's loading-branch comment already established for
> other code/tests/assistive tech. Re-verified live via Playwright
> (mutation trace of the AI insight panel's `<h3>` label text across a
> fresh ticker selection): exactly one transition (`—` → real label), not
> two. See tasks.md 14.9.

> **Second correction (added after a follow-up "still flashes, but
> Prediction doesn't" report, same day):** the fix above solved the label
> text swap, but a real geometry bug remained. The loading/no-ticker
> placeholder's three `.ai-insight-panel__item` blocks were all nested
> inside one wrapping `<div aria-hidden="true">` — a plain block element,
> not a flex participant, so `.ai-insight-panel`'s `gap: var(--space-lg)`
> (24px) never applied *between* those three items the way it does for
> the populated branch's items (direct flex children there). That shaved
> ~70-100px off the placeholder's rendered height versus the real
> populated height — measured live: a ~103px jump (`406.2px → 509.4px`)
> before this fix, ~16px (`455.0px → 470.6px`) after. This larger jump is
> exactly why `PredictionDisplay` never showed an equivalent flash: it has
> no such wrapper div at all, so its own (smaller, ~54px) content-driven
> height change reads as smooth. **Fixed** by removing the wrapping
> `<div>` and moving `aria-hidden="true"` onto each of the three item
> blocks individually, so they stay direct flex children in every state.
> Also corrected a pre-existing a11y gap surfaced by the same wrapper: the
> disclaimer `<p>` was nested inside it too, hiding its unconditional Rule
> 6 text from screen readers while loading even though nothing about that
> text was actually still loading — the disclaimer is deliberately left
> off `aria-hidden` now, in every state. Re-verified live via Playwright
> (geometry trace across a fresh ticker selection): the AI insight panel's
> height jump is now smaller than Prediction's own. See tasks.md 14.10.

> **Third correction (user-requested, same day): labels stop
> participating in loading at all.** The user asked for "Confidence"/
> "Technical Signal"/"Advice" to render as static, unchanging titles —
> never part of what "loads" — reversing part of the first correction
> above. `PredictionDisplay`'s `<h2>Prediction</h2>` was always this way;
> `AIInsightPanel`'s three labels now match it. Only each item's VALUE
> (and subtext/reasoning) remains a `—` placeholder while loading, each
> individually `aria-hidden="true"`. This retires the "real label = real
> data has loaded" signal the first correction relied on — anything
> needing to detect "has this ticker's data loaded" must now wait on a
> real *value* instead (e.g. `findByText('Bullish')`), not the label;
> `AIInsightPanel.test.jsx`/`App.test.jsx` updated accordingly. The
> now-unused `.ai-insight-panel__label--placeholder` CSS class was
> removed.
>
> **Separately, the value-swap itself was still visibly "flashing"** — a
> distinct report from the same user, same day, after the above shipped:
> "still see a millisecond flicker changing dash to number, Prediction
> doesn't have it." Traced live via Playwright mutation observer: the
> dash→value swap is a single, correct transition — no leftover
> double-render bug survived the second correction. The actual
> difference is that Confidence/Technical Signal/Advice's three values
> all resolve in the same render (one query, one re-render) with zero CSS
> transition on the swap, so three values snapping in simultaneously
> reads as more noticeable than `PredictionDisplay`'s single-value swap
> (which has the identical "no transition" property, but only one thing
> changes). Because loading→populated is a full JSX-branch swap (the
> value `<p>` unmounts and a new one mounts — not the same node's text
> updating), a plain `transition` cannot fire on it; a `@keyframes`
> fade-in animation (`ai-insight-panel-value-in`, using the existing
> `--dur-fast`/`--ease-out` tokens, opacity 0→1) was added to
> `.ai-insight-panel__value` instead, since CSS animations play on mount
> regardless of prior state. Disabled under `prefers-reduced-motion:
> reduce`, matching this file's existing pattern for the spinner and
> backtest button. Re-verified live via Playwright
> (`getComputedStyle().animationName` on the freshly mounted populated
> value): animation applies as expected. See tasks.md 14.11.

## Risks / Trade-offs

- **[Risk]** Shortening `confidence_basis` or the sentiment subtext could
  read as understating what rules 4/5 require disclosed, if done
  carelessly. → **Mitigation**: Decision 3's table checks each string
  against the specific fact the rule requires, not just brevity; the
  Advice line is left as an explicit checkpoint rather than guessed.
- **[Risk]** Existing tests (`AIInsightPanel.test.jsx`,
  `TickerPanel.test.jsx`) assert on today's exact copy strings and will
  fail once copy changes land. → **Mitigation**: tasks.md includes
  updating those assertions as part of this change, not as a follow-up.
- **[Risk]** Reallocating the title's type-scale step could read as "too
  small" once seen live, since `--text-base` is also used by chip
  symbols and body text — the title may need a weight or letter-spacing
  nudge beyond a flat size change to still read as a heading. →
  **Mitigation**: verify live via Playwright screenshot during
  implementation before considering this decision final; this is a
  visual judgment call best confirmed by looking at the rendered result,
  not decided from CSS values alone.
- **[Risk]** Shrinking `.chart-panel` to `18rem` (Decision 6) could make a
  longer price history feel cramped, since this height is shared by every
  ticker regardless of how much OHLCV history it has. → **Mitigation**:
  `lightweight-charts` auto-fits the visible range to the container
  regardless of height, and 18rem is still well above common dashboard
  chart heights for a single-series candlestick view; verify live via
  Playwright on both TCB (full training history) and a shorter-history
  searched-in ticker before considering this decision final.
- **[Risk]** `@phosphor-icons/react` (Decision 5) is a new runtime
  dependency — first icon library added to the frontend. → **Mitigation**:
  it's tree-shakeable (only `MagnifyingGlass` is imported) and has no
  runtime dependencies of its own beyond React; confirm bundle impact is
  negligible via a local build check rather than assuming it.
- **[Risk]** Growing `.chart-panel` back up (Decision 7) risks reopening
  the exact vertical-balance gap Decision 6 just closed against the AI
  insight panel. → **Materialized, then mitigated**: the first value tried
  (`24rem`/`18rem`) did reopen a visible gap on live Playwright re-check
  (tasks.md 9.5) — confirming this risk was real, not hypothetical.
  Reduced to `22rem`/`16rem`, re-verified live on both a populated ticker
  and the N/A-confidence branch, gap now reads as normal breathing room
  again. Not shipped on the first (untested) guess.
- **[Risk]** Per-bar volume coloring needs a specific up/down convention
  (close vs. open, or close vs. prior close) — picking the wrong one would
  silently disagree with `CandlestickSeries`'s own up/down coloring for
  the same session. → **Mitigation**: tasks.md 9.2 requires matching
  whichever convention the candlestick series already uses and stating it
  explicitly in a code comment, not re-deriving it independently.
- **[Risk]** Decisions 6/7's height re-checks compared `.chart-panel`
  against the wrong element (the AI insight panel alone, not the true
  side column) — this went undetected through two live-verification
  passes because both passes only ever looked at the same wrong
  comparison. → **Materialized, then corrected**: caught when growing the
  chart further (Decision 9) prompted re-measuring the actual DOM
  (`getBoundingClientRect()` on `.app-shell__side` vs. `.chart-panel`)
  instead of re-using the earlier visual comparison. Decision 9 documents
  the corrected numbers; future height changes to either panel should
  measure the real `.app-shell__side` total, not the AI insight panel in
  isolation.
- **[Risk]** `tokens.css`'s `--color-accent` is documented as "used for
  selection/focus, not decoration" — Decision 12's title-underline rule
  is a narrow, deliberate exception to that stated scope, not a new
  general license to use the accent color decoratively elsewhere. →
  **Mitigation**: Decision 12 states explicitly this is scoped to marking
  the app's own identity (functionally similar to marking the selected
  ticker chip), not decoration for its own sake; a future change reaching
  for the accent color decoratively elsewhere should not point to this
  decision as precedent without its own justification.
- **[Risk]** Swapping `--font-display` also changes fonts on
  `prediction-display.css` and `ai-insight-panel.css`, not just the
  title — a broader visual footprint than "polish the title" might
  suggest at a glance. → **Mitigation**: confirmed explicitly with the
  user before writing this decision (see Open Questions) — this is the
  deliberately-chosen scope (whole-app via the token), not an
  overlooked side effect.

## Migration Plan

No data migration. No backend behavior/contract change — the
`confidence_basis` string edit ships in the same way as any other backend
code change (no version gate, no client compatibility concern, since
frontend already renders whatever string this field contains verbatim).
Frontend and backend can ship independently or together; there is no
ordering dependency between the two.

Decisions 5 and 6 add one new frontend dependency (`@phosphor-icons/react`,
installed via `npm install` in `frontend/`) and one more frontend file
(`chart-panel.css`) to this change's footprint; neither has a database,
API contract, or model impact, and neither introduces an ordering
dependency with Decisions 1–4 or with each other.

Decision 7 adds no new dependency (`lightweight-charts` is already
installed) and no backend change (`volume` is already returned by `GET
/tickers/{ticker}/history`) — purely a `ChartPanel.jsx`/`chart-panel.css`
addition. It does have one real ordering interaction: it changes
`.chart-panel`'s height set by Decision 6, so Decision 7 should be
implemented and verified after Decision 6's height is in place, not
independently — tasks.md section 9 assumes section 8 has already landed.

Decisions 8 and 9 both build on Decision 7's code (`volumeSeriesRef`,
`.chart-panel`'s height) and should land after section 9, not
independently. Neither adds a dependency or backend change.

Decision 10 builds on Decision 8's `handleResetZoom` changes (same
function) and Decision 7's `setStretchFactor` calls (same values it
restores) — should land after section 10, not independently. No
dependency or backend change.

Decision 11 is independent of Decisions 7–10 (`ticker-panel.css`, not
`ChartPanel.jsx`/`chart-panel.css`) — no ordering dependency with the
chart-pane work, though it does follow on from Decision 1
(`.ticker-panel__title`) in the same file. No dependency or backend
change.

Decision 12 directly reverses part of Decision 11 (must land after it,
in the same file) and changes `tokens.css`'s `--font-display` value,
which fans out to every component that references
`var(--font-display)` — `prediction-display.css` and
`ai-insight-panel.css`, not just `ticker-panel.css`. No new dependency
(the Google Fonts `<link>` for Fraunces is a markup addition to
`frontend/index.html`, not an npm package) and no backend change.

## Open Questions

- ~~**Final Advice reasoning wording** (Decision 3)~~ — **Resolved during
  implementation**: user chose to leave `ADVICE_COPY`'s reasoning lines
  unchanged.
- ~~Whether the ticker-panel title's demotion (Decision 1) needs an
  additional visual treatment~~ — **Resolved during implementation**:
  verified live via Playwright; the `--text-base` weight-600 serif title
  reads clearly as a heading next to the chips/search box with no further
  treatment needed.
- Decisions 5 and 6 were confirmed with the user before being written up
  here (search redesign direction, icon dependency, and the
  shrink-chart-panel approach for Decision 6) — no open checkpoints remain
  for either.
- Decision 7's layout (separate pane, standard TradingView-style volume
  histogram) and no-MA-overlay scope were confirmed with the user before
  being written up here. The height value went through one live-verified
  revision: `24rem`/`18rem` was tried first, task 9.5's required
  Playwright re-check showed it reopened Decision 6's gap, and `22rem`/
  `16rem` was chosen instead after that check passed — **later found to
  be based on a wrong comparison, see Decision 9.**
- Decision 8's reset-zoom fix and Decision 9's `26rem`/`18rem` height
  (explicitly not a full match to the 657px side column, and not chasing
  one further) were both confirmed with the user before being written up
  here. No open checkpoints remain.
- Decision 10's restored 75/25 split ratio was confirmed with the user
  before being written up here. No open checkpoints remain.
- Decision 11's uppercase-wordmark direction and the CSS-`text-transform`-
  not-literal-uppercase approach (for the screen-reader announcement
  reason explained in Decision 11 itself) were both confirmed with the
  user before being written up here. **Reversed by Decision 12 after
  user feedback ("I still prefer Title Case Header") — no open checkpoint,
  the reversal itself is the resolution.**
- Decision 12's font pick (Fraunces over Newsreader/Space Grotesk),
  the whole-app token-level scope (vs. title-only), and the accent-rule
  stand-out technique (vs. a size/weight bump) were all confirmed with
  the user before being written up here. No open checkpoints remain. The
  pre-existing font-loading gap (neither the old nor new `--font-display`
  value was ever actually loaded) is fixed only for Fraunces, per this
  decision's own scope — the user explicitly declined a general fix.
- Decision 13's scope (both `PredictionDisplay` and `AIInsightPanel`, not
  just the AI insight panel alone) and its dash-placeholder-with-Advice-
  shown-always approach (vs. omitting the Advice block for the no-ticker
  case, matching how it's already sometimes absent for a real `near_gap`
  ticker) were both confirmed with the user before being written up here.
  **Reverses Decision 4 after user feedback (keep the dashboard's shape
  stable at all times rather than collapsing to a message box) — no open
  checkpoint, the reversal itself is the resolution.**
