## Context

The dashboard's design-token system (`frontend/src/styles/tokens.css`) uses
OKLCH color space, semantic-only color (positive/negative/warning/accent
reserved for real signal, never decoration), and a 4pt spacing scale.
`polish-dashboard-hierarchy-and-copy` tuned hierarchy, spacing, and copy on
top of this system without questioning the look itself — Fraunces (display)
+ Inter (body) + an unloaded system-mono stack, 6px/10px/999px radii,
green/red candlesticks matching `lightweight-charts`' pre-Decision-7
defaults.

A design-intelligence review (`ui-ux-pro-max` skill, against a screenshot of
the shipped dashboard) proposed three distinct directions; the user chose
**Swiss Data Minimalism** — a single sans family, tabular numerals, tighter
radii, a cooler slate/navy register — over an evolved-editorial-serif
direction and a bento-card layout direction. The user also flagged a real
gap surfaced during that review: the ticker panel's single horizontal
chip-wrap row has no plan for the searched-in ticker list growing large
(every distinct symbol searched and successfully loaded persists as a
selectable entry for the session; `GET /tickers` returns every row in the
`tickers` table, and the VN market has 1,600+ listed symbols).

Current state, read from `tokens.css` and the components that consume it:
- `--font-display: 'Fraunces', ui-serif, Georgia, serif` and `--font-body:
  'Inter', system-ui, ...` — both fan out to `ticker-panel.css`,
  `prediction-display.css`, `ai-insight-panel.css`.
- `--font-mono` exists but has never been an actually-loaded webfont — it
  falls back to the system mono stack. No component currently applies
  `font-variant-numeric: tabular-nums`.
- `--radius-sm: 6px`, `--radius-md: 10px`, `--radius-full: 999px` — used
  across cards, inputs, and the pill-shaped selected-ticker indicator.
- `--color-positive`/`--color-negative` are read both by `ChartPanel.jsx`'s
  `readChartTheme()` (candlestick + volume bar coloring) and by
  `PredictionDisplay`/`AIInsightPanel`'s up/down styling — one token pair,
  fanned out to both the chart and the text, per the existing "semantic
  color, single source" architecture. Changing the token values changes
  both simultaneously; that's a feature of the existing design, not a new
  risk this change introduces.
- `TickerPanel.jsx` renders `catalogTickers` (from `GET /tickers`) and
  `searchedTickers` (client-side session tracking) as one flat list of
  `TickerChip`s in a single `flex-wrap` row (`ticker-panel__chips`).

## Goals / Non-Goals

**Goals:**
- Replace the editorial-serif register (Fraunces/Inter) with a single-sans,
  tabular-numeral register (IBM Plex Sans/IBM Plex Mono) across every
  component that reads `--font-display`/`--font-body`/`--font-mono`.
- Retune the palette toward a cooler, higher-contrast slate/navy register,
  and align `--color-positive`/`--color-negative` with `lightweight-charts`'
  own canonical bullish/bearish hues.
- Tighten the radius scale to a near-flat register appropriate to a
  trading-terminal aesthetic.
- Give the ticker panel a plan for a searched-in list that can realistically
  grow into the dozens or low hundreds within a session, without breaking
  the existing "fixed Watchlist always visible" requirement.

**Non-Goals:**
- Not introducing list virtualization/windowing — deferred until real usage
  shows a plain scrollable, filtered list is actually too slow (see Risks).
- Not adding a user-facing theme toggle — theme stays
  `prefers-color-scheme`-only.
- Not touching computation, the API contract, the DB, or the model — this
  is presentation-only, identically scoped to the prior polish change.
- Not re-litigating the 4pt spacing *scale* itself (the `--space-*` step
  values) — only specific component paddings inside the new ticker-list
  treatment, where needed for the denser register.
- Not touching the AI insight panel's value/subtext rhythm, the chart's
  pane split, or any copy string — all settled by the prior change and out
  of scope here.

## Decisions

### Decision 1: Typography — IBM Plex Sans + IBM Plex Mono, single family

`--font-display` and `--font-body` both repoint to `'IBM Plex Sans',
system-ui, 'Segoe UI', Roboto, sans-serif` — the `ui-ux-pro-max` skill's
"Financial Trust" pairing (banks/finance/fintech, single family, avoids the
"heading font vs. body font" tension entirely). Visual distinction between
display and body contexts (app title, big numbers vs. labels/paragraph
text) is carried by weight and size, not by a second family — the same
mechanism `--font-display` at weight 600 already used with Fraunces.

`--font-mono` repoints to `'IBM Plex Mono', ui-monospace, 'SF Mono',
Consolas, monospace` and, unlike the prior change's Fraunces fix (scoped
only to that one family), is loaded correctly **from the start** via a
Google Fonts `<link>` in `frontend/index.html` alongside IBM Plex Sans —
no repeat of the "token value chosen, font never actually loaded" gap.
Genuinely numeric elements — Prediction %, Confidence %, chart price axis,
"Loaded Nd ago" — switch to `var(--font-mono)` with `font-variant-numeric:
tabular-nums`, so figures align in a column instead of using default
proportional numerals (`number-tabular` guidance).

Alternative considered: Lexend + Source Sans 3 ("Corporate Trust" pairing,
two families, built for accessibility/readability). Rejected — the
single-family "Financial Trust" pairing better matches the "Bloomberg-
terminal-adjacent" register the user picked, and avoids introducing a
second sans family's visual seams.

Domain rules: unaffected — a typeface and numeral-alignment change only;
no value, wording, or visibility of any Rule 1–6 governed content changes.

> **Correction (found via user report after this shipped):** the chart's
> right price-scale column (`rightPriceScale.minimumWidth: 76`, tuned
> under the prior Inter-based font) is shared by both panes — its width
> is driven by whichever pane's tick labels are widest, and that turned
> out to be the **volume** pane, not the price pane: `lightweight-charts`'
> `'volume'` price format shows a decimal point for lower-magnitude ticks
> ("1.5M") but not for round ones ("40M"). Verified live across all 9
> `TRAINING_TICKERS`: 8 rendered at exactly 76px, but SAB (max ~1.65M
> volume in the default visible window, versus 10–75M for the others)
> needed 80px — a real per-ticker difference, not a font-loading race
> (confirmed `document.fonts.check(...)` was already `true` before either
> render). Switching between a 76px-needing ticker and SAB, or clicking
> "Reset zoom" after such a switch, visibly resized the column and
> shrank/grew the candlestick+volume plot area with it — this is the bug
> report this correction addresses. **Fixed** by raising `minimumWidth`
> to `88` — comfortably above SAB's measured 80px need, confirmed live to
> render as one true constant (no longer just a floor that still grows
> for some tickers) across all 9 `TRAINING_TICKERS` plus a spot-checked
> lower-volume searched-in ticker (GAS, ~4.9M max volume). See
> `frontend/src/components/ChartPanel/ChartPanel.jsx`'s updated comment
> for the measured numbers. Domain rules: unaffected — a chart-sizing
> constant only, no computation, data, or disclosure content change.

### Decision 2: Palette — cooler slate/navy, canonical candle hues

Both `prefers-color-scheme` branches retune toward higher contrast and a
more deliberate navy accent (a directional decision; exact OKLCH values are
confirmed live during implementation per the Risks section, not locked in
here):
- `--color-ink` deepens (lower lightness, slightly higher chroma) for a
  crisper "navy-black" body-text color instead of the current soft gray.
- `--color-accent` deepens toward institutional navy rather than the
  current brighter selection-blue, while keeping its existing scope
  (selection/focus signal only, never decoration).
- `--color-positive`/`--color-negative` shift toward `lightweight-charts`'
  own default candle hues — teal-green (`#26A69A`-family) and coral-red
  (`#EF5350`-family) rather than the current pure green/red — translated to
  OKLCH. Because these tokens already fan out to both the chart and the
  Prediction/Advice text (Decision context above), this one token change
  covers both surfaces with no separate chart-specific override.
- `--color-paper`/`--color-border` stay close to today's values — the
  "cooler" register comes from ink/accent/positive/negative contrast, not
  from darkening the paper itself, which stays a calm near-white/near-black
  in light/dark respectively.

Alternative considered: a warmer navy+gold "Banking/Traditional Finance"
palette (`ui-ux-pro-max` result 3). Rejected — gold has no reserved
semantic slot in the existing "positive/negative/warning/accent only"
architecture, and introducing one without a real signal to attach it to
would violate that architecture's own stated constraint (`tokens.css`'s
comment: colors "never decorative").

Domain rules: unaffected — Rule 5's "Technical Signal" label and inline
basis text, and Rule 6's disclaimer, are restyled (new ink/paper contrast)
but not reworded or hidden. Rule 3's directional Advice wording
("Signal: up/down") keeps using the same positive/negative tokens, just
retuned.

### Decision 3: Radius scale — 6px/10px/999px → 2px/4px/999px

`--radius-sm` (6px → 2px) and `--radius-md` (10px → 4px) tighten to a
near-flat register; `--radius-full` (999px) is unchanged — it remains
reserved for the selected-ticker pill indicator, a real affordance signal,
not decoration, consistent with the existing token comment's intent.

Domain rules: unaffected — a shape-only change.

### Decision 4: Ticker panel — Watchlist / searched-in split, with a scoped filter

`TickerPanel.jsx` renders two distinct, separately-labeled groups instead
of one flat `role="group"` chip row:
- **Watchlist** (unchanged behavior): the 9 `TRAINING_TICKERS` from
  `catalogTickers`, rendered as today's chips, always visible regardless of
  filter state — this is the existing `dashboard-ui` spec requirement
  ("Ticker panel shows the fixed set... always visible"), untouched.
- **Searched tickers** (new): every entry in `searchedTickers` (plus any
  `catalogTickers` entry outside the fixed 9, if the backend ever returns
  one — see Open Questions), rendered as a vertically-scrollable list of
  compact rows, not chips — a list reads better than wrapping pills once
  the count moves from a handful to dozens, and matches the Swiss/dense
  register better than a chip wall would anyway.

A single-line substring filter input narrows the **Searched tickers** list
only, live as the user types (no network call — pure client-side
`.filter()` over the already-loaded `searchedTickers` array). It has no
effect on the Watchlist group, preserving the existing "always visible
regardless of search state" scenario verbatim. An `aria-live="polite"`
region announces the filtered count (e.g. "12 of 47 tickers") for screen
reader users, since the visible row count changing without an announcement
would otherwise be silent.

Alternative considered: reusing `TickerSearch`'s existing input as the
filter input, so typing both narrows the visible list live AND still
resolves-or-loads on submit. Adopted as the default (see Decision 5) rather
than adding a second, separate filter box — one input serving both purposes
keeps the header from gaining a second control that does something subtly
different from the first.

Domain rules: unaffected — no computation, prediction, or disclosure
content changes; this is a ticker-panel layout and interaction addition.

### Decision 5: One search input serves both filter and load

`TickerSearch.jsx`'s existing input drives both behaviors at once, not two
separate controls:
- **Live, as-you-type**: filters the **Searched tickers** list (Decision 4)
  to entries whose symbol contains the typed substring, case-insensitively.
- **On submit** (existing behavior, unchanged): resolves the typed symbol —
  selects it directly if already known, or triggers `POST
  /tickers/{ticker}/load` if not — exactly as today.

This means typing a substring that matches nothing in the already-loaded
list still lets the user press Enter/click Load to attempt loading it as a
new symbol — the filter narrows what's already there; it never blocks the
existing load path. The Watchlist is unaffected by typing, per Decision 4.

Domain rules: unaffected.

### Decision 6: Test updates

`TickerPanel.test.jsx` and `ChartPanel.test.jsx` (and any other test
asserting on Fraunces-era class names, the current pure green/red candle
color values, or the single flat chip-list DOM structure) are updated to
match the new two-group markup and retuned colors as part of this change,
not left failing — same discipline the prior change applied to its own
copy-string test updates.

### Decision 7: Adjacent fix — AI insight panel's first-selection flash (user-reported, not caused by this change)

Reported by the user while reviewing this change live: `AIInsightPanel`
visibly "flashed" the first time (per session) any given ticker was
selected — Confidence/Technical Signal/Advice's dash placeholders
unmounting and the real values mounting in — while `PredictionDisplay`'s
percent changed smoothly even on that same first click.

**Root-caused live via the network log, not guessed**: `TickerChip`
already fires `useTickerFreshness(ticker, ...)` for every Watchlist (and
searched-in) chip purely to compute its own freshness dot, and that hook
internally queries `prediction`/`history` — the exact same query keys
`PredictionDisplay`/`ChartPanel` read. So by the time any ticker is first
clicked, those two panels find already-warm cache data and paint
instantly, skipping their loading branch entirely. `AIInsightPanel`'s
`useTickerInsight` query has no equivalent prefetch anywhere — confirmed
live that selecting two different never-before-selected tickers each
triggered a fresh `/insight` request with no prior cache entry, while
`/prediction`/`/history` were already warm for both. A ticker's
first-ever selection therefore always started from a genuinely cold
`insight` cache, forcing the placeholder-to-populated unmount/remount
(and the `polish-dashboard-hierarchy-and-copy`-era fade-in animation that
softens but doesn't eliminate it) every time a *new* ticker was picked,
not just once per session.

**Fixed** by extending `useTickerInsight(ticker, options)` to accept an
`enabled` option, mirroring `useTickerFreshness`'s existing shape, and
having `TickerChip` call it the same way it already calls
`useTickerFreshness` — purely to warm `AIInsightPanel`'s own query cache
under the same key; the return value is unused at the call site.
Re-verified live: `/insight` now fires for all 9 `TRAINING_TICKERS`
immediately on page load (mirroring `/prediction`/`/history`'s existing
prefetch), and a previously-untouched ticker renders its populated AI
insight content on first click with no cold fetch.

This is presentation-adjacent (it fixes a visible flash) but is a real
data-fetching/caching behavior change — one extra request per Watchlist/
searched-in ticker on page load — not a font/color/layout one. Flagged as
its own decision for that reason, and because, unlike Decision 1's
price-scale correction, this bug predates this change entirely; it was
found and fixed in the same session only because the user was reviewing
this change's live result.

Domain rules: unaffected — no computed value, wording, or disclosure
visibility changes; Confidence/Sentiment/Advice/disclaimer render
identically once populated, only *when* that population completes changes.

### Decision 8: Ticker panel title — accent underline retired

User-reported after reviewing this change live: the accent-colored rule
beneath the "Stock Foresight" title (added by the prior
`polish-dashboard-hierarchy-and-copy` change's Decision 12) "looks
unmatched" now that the title renders in IBM Plex Sans against the
retuned navy/slate palette. That underline was tuned specifically to sit
under Fraunces' serif character, and Decision 12 itself already flagged
it as "a deliberate, narrow exception" to `--color-accent`'s
selection/focus-only scope — i.e. it was decoration riding on the accent
token, not signal.

Presented three options (via the `ui-ux-pro-max` skill's style-database
guidance for the Minimalism/Swiss Style category this change adopts,
which explicitly calls for "no unnecessary decorations" and an accent
"reserved" for real signal): remove the mark entirely; replace it with a
full-width neutral hairline divider between the header row and the
Watchlist; or replace it with a small accent square glyph beside the
title. **User chose removal.**

`.ticker-panel__title::after` (the underline) and its now-unneeded
`position: relative`/`padding-bottom` on the title are removed; the title
renders as plain weight-700 IBM Plex Sans at `--text-lg`, no applied
mark. This also restores `--color-accent`'s token comment ("used for
selection/focus, not decoration") to being literally true again — Decision
12's narrow exception is retired, not just visually replaced.

Domain rules: unaffected — a visual-only removal of the app's own
wordmark treatment; no data, computation, or disclosure content touched.

## Risks / Trade-offs

- **[Risk]** The retuned palette (Decision 2) could fail WCAG contrast in
  one of the two `prefers-color-scheme` branches, since exact OKLCH values
  are directional here, not locked. → **Mitigation**: verify contrast live
  (both light and dark) during implementation before considering Decision 2
  final — the same live-verification discipline the prior change used for
  every visual judgment call.
- **[Risk]** Dropping Fraunces removes an identity choice the prior change
  explicitly confirmed with the user (Decision 12) after considering
  alternatives — a full reversal within days of shipping. → **Mitigation**:
  this is a deliberate, user-chosen register change after reviewing three
  concrete alternatives (see proposal.md's Why), not an accidental
  re-litigation; framed here as superseding Decision 12, not contradicting
  it silently.
- **[Risk]** Splitting the ticker panel into two ARIA groups could break
  the existing single-`role="group"` assumption in tests or assistive-tech
  navigation patterns users have learned. → **Mitigation**: give each group
  its own labeled `role="group"` (e.g. "Watchlist", "Searched tickers"),
  update `TickerPanel.test.jsx` accordingly, and verify tab order/reading
  order live before finalizing.
- **[Risk]** A single input serving both "filter" and "load" (Decision 5)
  could confuse users if the two behaviors aren't clearly distinguished —
  e.g. typing a partial match might read as "searching," not "about to load
  a new ticker" if the user pauses instead of submitting. → **Mitigation**:
  the filtered list itself is the feedback loop (seeing 0 matches signals
  "this isn't loaded yet, submit to load it"); revisit with a separate
  input if live use shows this reads as ambiguous.
- **[Risk]** No virtualization for the searched-in list (a deliberate
  Non-Goal) could become a real performance problem if a session's list
  grows far beyond low hundreds. → **Mitigation**: explicitly flagged, not
  silently capped — if real usage produces a list large enough to lag, a
  follow-up change adds windowing (e.g. `@tanstack/react-virtual`) at that
  point, with actual evidence instead of speculative pre-optimization.

## Migration Plan

No data migration. No backend behavior, API contract, or DB change — this
ships entirely in `frontend/`. Sequencing within the frontend:
1. Token changes first (`tokens.css`: fonts, colors, radii) and the
   `index.html` font-link swap — every component consuming these tokens
   picks up the new look with no per-component edit needed for color/font/
   radius alone.
2. `ChartPanel.jsx`/`chart-panel.css` — no code change needed for candle
   colors specifically (they already read the retuned
   `--color-positive`/`--color-negative` tokens via `readChartTheme()`);
   verify live that the new hues render as expected on both a bullish and
   bearish session.
3. `TickerPanel.jsx`/`TickerChip.jsx`/`TickerSearch.jsx`/`ticker-panel.css`
   — the Watchlist/searched-list split and filter behavior, after step 1's
   tokens are in place (the new list rows should already inherit the new
   type/color register, not need their own overrides).
4. Test updates last, once the real rendered output (colors, class names,
   DOM structure) is stable.

Frontend and any future backend change (none anticipated here) have no
ordering dependency, since none exists in this change.

## Open Questions

- Exact OKLCH numeric values for the retuned ink/accent/positive/negative
  tokens (Decision 2) — directional here; confirmed via live contrast
  verification during implementation, not decided in this document.
- Whether `GET /tickers` can ever return a non-`TRAINING_TICKERS` entry
  (i.e. whether the backend's `tickers` table membership and the frontend's
  client-side `searchedTickers` tracking can diverge) — Decision 4 assumes
  "Searched tickers" is the right home for any such entry if it exists;
  worth a quick backend check during implementation rather than assumed.
