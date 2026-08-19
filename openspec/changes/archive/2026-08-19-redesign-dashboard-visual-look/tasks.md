## 1. Design tokens — typography

- [x] 1.1 In `frontend/index.html`, remove the Fraunces Google Fonts
      `<link>` (added by `polish-dashboard-hierarchy-and-copy` Decision 12)
      and add links for IBM Plex Sans (weights 400/500/600/700) and IBM
      Plex Mono (weights 400/500), `display=swap`.
- [x] 1.2 In `frontend/src/styles/tokens.css`, repoint `--font-display`
      and `--font-body` to `'IBM Plex Sans', system-ui, 'Segoe UI', Roboto,
      sans-serif`.
- [x] 1.3 Repoint `--font-mono` to `'IBM Plex Mono', ui-monospace, 'SF
      Mono', Consolas, monospace`.
- [x] 1.4 Apply `var(--font-mono)` + `font-variant-numeric: tabular-nums`
      to genuinely numeric value elements: `PredictionDisplay`'s percent
      value, `AIInsightPanel`'s Confidence percent value, the chart
      panel's price/volume axis labels, and the ticker chip/row's "Loaded
      Nd ago" text. Do not apply to headings, labels, or non-numeric body
      text.

## 2. Design tokens — color and radius

- [x] 2.1 In `tokens.css`, retune `--color-ink`/`--color-ink-2`/
      `--color-ink-3` toward a crisper, slightly higher-chroma
      "navy-black" in the light branch; retune the dark
      `prefers-color-scheme` branch's equivalents to match.
- [x] 2.2 Retune `--color-accent`/`--color-accent-bg`/`--color-accent-border`/
      `--color-focus` toward a deeper institutional navy in both branches,
      keeping the token's existing scope (selection/focus signal only).
- [x] 2.3 Retune `--color-positive`/`--color-positive-bg` and
      `--color-negative`/`--color-negative-bg` in both branches toward
      `lightweight-charts`' own canonical bullish (`#26A69A`-family) and
      bearish (`#EF5350`-family) hues, translated to OKLCH.
- [x] 2.4 Change `--radius-sm` from `6px` to `2px` and `--radius-md` from
      `10px` to `4px`. Leave `--radius-full` unchanged.
- [x] 2.5 Verify live (Playwright, both light and dark) that every
      retuned foreground/background pair in 2.1–2.3 still meets WCAG AA
      contrast (4.5:1 body text, 3:1 large text) — adjust lightness/chroma
      values if any pair fails, before considering this section done.

## 3. Chart panel — candle colors

- [x] 3.1 Confirm `ChartPanel.jsx`'s `readChartTheme()` reads
      `--color-positive`/`--color-negative` directly (no hardcoded hex
      fallback that would bypass section 2's retuned values).
- [x] 3.2 Verify live on a ticker with both bullish and bearish sessions
      visible that candlestick and volume-bar colors render the retuned
      hues correctly in both themes.
- [x] 3.3 Update `ChartPanel.test.jsx`'s color assertions (if any) to the
      new values.

## 4. Ticker panel — Watchlist / searched-in split

- [x] 4.1 In `TickerPanel.jsx`, split rendering into two labeled groups:
      `role="group" aria-label="Watchlist"` for the 9 `TRAINING_TICKERS`
      (unchanged `TickerChip` markup/behavior), and a new
      `role="group" aria-label="Searched tickers"` for `searchedTickers`
      entries.
- [x] 4.2 Add a new compact list-row component (or a row-mode variant of
      `TickerChip`) for the "Searched tickers" group, styled as a
      vertically-scrollable list (`overflow-y: auto`, capped max-height)
      rather than a wrapping chip row.
- [x] 4.3 Add `ticker-panel.css` rules for the new list container and row
      styling, consistent with sections 1–2's retuned tokens (no new
      one-off colors or fonts).
- [x] 4.4 Confirm the Watchlist group's chips remain wholly unaffected by
      this restructuring — same markup, same freshness-dot legend, same
      selection behavior.

## 5. Ticker panel — filter behavior

- [x] 5.1 In `TickerSearch.jsx`, add a live `onChange` handler (distinct
      from the existing submit/load handler) that reports the current
      input value up to `TickerPanel.jsx` on every keystroke.
- [x] 5.2 In `TickerPanel.jsx`, filter `searchedTickers` to entries whose
      symbol contains the current input value (case-insensitive
      substring match) before rendering the "Searched tickers" group. The
      Watchlist group's rendering is untouched by this value.
- [x] 5.3 Add an `aria-live="polite"` region near the "Searched tickers"
      group announcing the visible/total count (e.g. "12 of 47 tickers")
      whenever the filtered count changes.
- [x] 5.4 Confirm the existing submit-to-load behavior (Enter key / Load
      button) still fires correctly when the typed value doesn't match any
      currently-loaded ticker — filtering must not intercept or block it.

## 6. Test updates

- [x] 6.1 Update `TickerPanel.test.jsx` for the two-group ARIA structure,
      the new list-row markup for searched-in tickers, and the live
      filter/announcement behavior (sections 4–5).
- [x] 6.2 Update any test asserting on Fraunces-era class names or the
      old chip-only flat structure.
- [x] 6.3 Run `cd frontend && npm run test` and fix any other test broken
      by the retuned tokens (e.g. snapshot or class-name assertions in
      `AIInsightPanel.test.jsx`, `PredictionDisplay.test.jsx`,
      `App.test.jsx`).

## 7. Live verification

- [x] 7.1 Screenshot the full dashboard (Playwright) in both light and
      dark `prefers-color-scheme` with a ticker selected, confirming the
      IBM Plex Sans/Mono typography, retuned palette, and tightened radii
      render as intended.
- [x] 7.2 Screenshot the ticker panel specifically after searching in
      15–20 test symbols, confirming the Watchlist stays fixed while the
      "Searched tickers" list scrolls and the filter narrows it correctly.
- [x] 7.3 Re-verify Rule 5 (Sentiment labeled as a technical proxy, basis
      visible inline) and Rule 6 (disclaimer unconditionally visible)
      still hold with the new typography/color — a restyle should not
      have altered their content or visibility.

## 8. Post-implementation fix — chart price-scale column fluctuates per ticker

- [x] 8.1 User-reported: switching to SAB (or switching away from it, or
      clicking "Reset zoom" afterward) visibly resized the chart's right
      price-scale column and the candlestick/volume plot area with it.
      Root-caused live (Playwright) to the volume pane's abbreviated tick
      labels needing a decimal point for SAB's lower-magnitude volume
      range ("1.5M") versus the other 8 `TRAINING_TICKERS`' round-number
      labels ("40M") — not a font-loading race (checked and ruled out).
      See design.md Decision 1's correction note.
- [x] 8.2 Raise `ChartPanel.jsx`'s `rightPriceScale.minimumWidth` from
      `76` to `88` so the column is a true constant (verified ≥ every
      measured case) rather than a floor that still grows for some
      tickers.
- [x] 8.3 Verify live across all 9 `TRAINING_TICKERS` plus a lower-volume
      searched-in ticker that the column renders at the same fixed width
      on initial selection, after switching tickers, and after "Reset
      zoom" — no fluctuation in any case.
- [x] 8.4 Re-run the full frontend test suite to confirm no regression.

## 9. Adjacent fix — AI insight panel flashes on a ticker's first selection

- [x] 9.1 User-reported: after a fresh reload, selecting a ticker for the
      first time visibly flashes the AI insight panel's Confidence/
      Technical Signal/Advice content, while Prediction's percent changes
      smoothly on that same first click. Root-caused live (network log):
      `TickerChip` already prefetches `prediction`/`history` for every
      Watchlist/searched-in ticker via `useTickerFreshness`; nothing
      prefetches `insight`, so a ticker's first-ever selection always
      starts from a cold `useTickerInsight` cache. See design.md
      Decision 7 (flagged as predating this change, found in the same
      session).
- [x] 9.2 Extend `useTickerInsight(ticker, options)` to accept an
      `enabled` option (mirroring `useTickerFreshness`'s existing shape).
- [x] 9.3 Have `TickerChip` call `useTickerInsight(ticker, { enabled:
      isLoaded && !featuresFailed })` alongside its existing
      `useTickerFreshness` call, purely to warm the cache — return value
      unused.
- [x] 9.4 Add test coverage: a Watchlist ticker's insight is prefetched on
      render (not just on selection), and an unloaded ticker's is not.
- [x] 9.5 Verify live: `/insight` fires for all 9 `TRAINING_TICKERS` on
      page load, and a previously-unselected ticker renders populated AI
      insight content on first click with no cold fetch.
- [x] 9.6 Re-run the full frontend test suite to confirm no regression.

## 10. Ticker panel title — retire the accent underline

- [x] 10.1 User-reported: the accent-colored rule beneath "Stock
      Foresight" (prior change's Decision 12, tuned for Fraunces) "looks
      unmatched" against the new IBM Plex Sans/navy register. Presented
      3 options via `ui-ux-pro-max`'s style guidance (remove; full-width
      neutral divider; small accent glyph) — user chose removal. See
      design.md Decision 8.
- [x] 10.2 Remove `.ticker-panel__title::after` and the now-unneeded
      `position: relative`/`padding-bottom` on `.ticker-panel__title`.
- [x] 10.3 Verify live: title renders as plain weight-700 text, no mark;
      full test suite still passes.
