## Why

`polish-dashboard-hierarchy-and-copy` tuned the dashboard's existing visual
language (OKLCH tokens, Fraunces/Inter pairing, chip-based ticker panel)
through 13 incremental hierarchy/spacing/copy decisions, but never
questioned the underlying look itself. A fresh look-and-feel review — using
the `ui-ux-pro-max` skill's design intelligence against a screenshot of the
shipped dashboard — surfaced a coherent alternative register, **Swiss Data
Minimalism**, that reads closer to a professional trading terminal than the
current editorial-serif treatment, plus a real scaling gap the review
uncovered: the ticker panel's single horizontal chip-wrap row has no plan
for what happens once the searched-in ticker list grows large. Every
distinct symbol a user searches and successfully loads persists as a
selectable entry for the rest of the session (`GET /tickers` returns every
row ever written to the `tickers` table); the VN market has 1,600+ listed
symbols across HOSE/HNX/UPCOM, so a session that explores broadly can
plausibly accumulate well past 100 entries with no current design for it.

## What Changes

- **Typography**: retire the serif display font (Fraunces, added by the
  prior change's Decision 12) in favor of a single sans family — **IBM
  Plex Sans** — for the app title, panel headings, and body text. **IBM
  Plex Mono** is added (a genuinely new load, not a token repoint) for
  numeric data specifically — Prediction %, Confidence %, prices, "Loaded
  Nd ago" — with `font-variant-numeric: tabular-nums` so figures align in
  a column instead of using default proportional numerals.
- **Palette**: shift `tokens.css`'s OKLCH values toward a cooler,
  higher-contrast slate/navy register in both the light and dark
  `prefers-color-scheme` branches — still OKLCH, still semantic-only color
  (positive/negative/warning/accent reserved for real signal, never
  decoration), still no user-facing theme toggle. Exact values and their
  WCAG contrast checks are a design.md decision, not decided here.
- **Radius**: tighten the corner-radius scale from today's 6px/10px/999px
  steps to a near-flat 2–4px scale for cards, panels, and inputs — pill
  shapes stay only where they mark a real affordance (the selected-ticker
  indicator), not as general decoration.
- **Candlestick colors**: adopt `lightweight-charts`' own canonical
  bullish/bearish hues (teal-green `#26A69A` / coral-red `#EF5350`,
  translated to OKLCH) in place of the current pure green/red — this is a
  return to the charting library's own defaults, not a new custom pairing,
  and stays within the prior change's already-settled "matches standard
  trading convention" bar.
- **Ticker panel scaling** (added after reviewing the direction with the
  user — a real gap, not originally scoped): split the panel into (a) a
  small, always-visible **Watchlist** row for the 9 `TRAINING_TICKERS`,
  unchanged in behavior and still the fixed set the existing spec
  requires, and (b) a separate, vertically-scrollable, filterable list for
  every other searched-in ticker. A lightweight substring filter narrows
  list (b) only as the user types; it never hides or affects the
  Watchlist row, preserving the existing "always visible regardless of
  search state" requirement for the fixed set.
- Existing frontend tests asserting on today's Fraunces-era class names,
  chip-only DOM structure, or candlestick color values are updated to
  match, not left failing.

**Explicitly out of scope / deferred:**
- List virtualization (windowing) for the searched-in ticker list — a
  plain scrollable, filtered list comfortably handles low hundreds of
  simple rows; virtualization is flagged as a concrete follow-up only if
  real usage produces a list large enough that scrolling/filtering itself
  measurably lags, not adopted pre-emptively without evidence.
- A user-facing light/dark theme toggle — still out of scope; theme stays
  OS-driven only (`prefers-color-scheme`), matching the existing
  architecture.
- Any change to computation, the API contract, the DB, or the model — this
  is a presentation-only change, like `polish-dashboard-hierarchy-and-copy`
  before it.
- The freshness-dot/chip-footer legibility question and the calendar-vs-
  internal-consistency staleness definition — both still tracked in
  `docs/DISCUSSION_calendar_staleness.md`, not pre-empted by this visual
  pass.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `dashboard-ui`: the "Ticker panel shows the fixed set plus search for
  any real ticker" requirement is generalized from "one selectable **chip**
  per ticker" to "one selectable **entry** per ticker" — a chip for the
  fixed Watchlist, a list row for searched-in tickers — with no change to
  what must be selectable or when. A **new** requirement/scenario is added:
  the searched-in ticker list SHALL offer a filter that narrows only that
  list's visible entries, and SHALL NOT affect the fixed Watchlist's
  visibility. Every other existing requirement (search-triggers-load,
  freshness states, prediction/insight rendering, disclaimer) is
  unaffected — this change only restyles presentation and adds the one
  filter behavior above.

## Domain rule interactions

- **Rule 1/2** (log-return target; percentage-only display): unaffected.
  Tabular numeral styling changes how the percentage is *rendered*
  visually, not its value or the conversion itself.
- **Rule 3** (volatility-relative Advice): unaffected — Advice wording and
  reasoning-before-verdict structure are untouched; only typography/color.
- **Rule 4** (Confidence = backtested hit-rate): unaffected — the value and
  its basis text are untouched.
- **Rule 5** (Sentiment is a technical proxy, must be labeled as such):
  unaffected and explicitly preserved — "Technical Signal" labeling and the
  inline RSI/MACD/Ichimoku basis text must survive the typography/color
  pass unchanged in content, restyled only.
- **Rule 6** (no investment-advice framing; disclaimer always visible, no
  hide control): unaffected and explicitly preserved — the disclaimer's
  unconditional rendering is not touched by any decision in this change;
  no toggle or collapse is introduced.

All six rules are honored unchanged; none require sign-off to modify,
because none are being modified — only how the dashboard looks, and how the
ticker panel scales.

## Impact

- `frontend/src/styles/tokens.css` — font-family, color, and radius token
  values change. `--font-display`/`--font-body` repoint to IBM Plex Sans;
  `--font-mono` repoints to IBM Plex Mono (first time it's an actual
  loaded webfont rather than a system-font fallback stack).
- `frontend/index.html` — Google Fonts `<link>` swaps: removes the
  Fraunces link (prior change's Decision 12), adds IBM Plex Sans + IBM
  Plex Mono.
- Every component stylesheet that already reads `var(--font-display)`,
  `var(--font-mono)`, or a semantic color token fans out automatically
  (`prediction-display.css`, `ai-insight-panel.css`, `ticker-panel.css`,
  `chart-panel.css`) — no per-file font/color literal changes needed
  beyond the token definitions themselves, except where a component sets
  its own radius or candle-color value directly.
- `frontend/src/components/ChartPanel/ChartPanel.jsx` /
  `chart-panel.css` — candlestick bullish/bearish color values.
- `frontend/src/components/TickerPanel/TickerPanel.jsx`,
  `TickerChip.jsx`, `ticker-panel.css` — Watchlist/searched-list split,
  new filter input and its state, updated ARIA structure for two distinct
  groups instead of one.
- `openspec/specs/dashboard-ui/spec.md` — the ticker-panel requirement's
  wording and one new filter scenario (via this change's spec delta).
- Various `*.test.jsx` files asserting on now-changed class names, colors,
  or DOM structure (`TickerPanel.test.jsx`, `ChartPanel.test.jsx`, and any
  snapshot/class assertions elsewhere).
- `frontend/src/hooks/useTickerInsight.js`, `TickerChip.jsx` — design.md
  Decision 7 (adjacent fix, user-reported, not caused by this change's own
  decisions): `useTickerInsight` gains an `enabled` option, and
  `TickerChip` calls it to prefetch AI insight for every Watchlist/
  searched-in ticker the same way it already prefetches prediction/
  history for its freshness dot — one extra `GET
  /tickers/{ticker}/insight` request per such ticker on page load.
- `frontend/src/components/TickerPanel/ticker-panel.css` — design.md
  Decision 8: the accent-colored underline beneath the "Stock Foresight"
  title (prior change's Decision 12, tuned for Fraunces) is removed —
  user-reported as visually unmatched against the new register, and out
  of step with the Swiss Data Minimalism style's own "no unnecessary
  decoration" guidance. Title now renders on weight/size alone.
- **No backend, API, database, or model changes.** No new npm dependency
  is anticipated (IBM Plex Sans/Mono load via Google Fonts `<link>`s, the
  same mechanism already used for Fraunces; the ticker-list filter is a
  plain client-side string match, no new package). No milestone status
  change — hardening/polish per `openspec/config.yaml`'s "Current focus,"
  not new scope.
