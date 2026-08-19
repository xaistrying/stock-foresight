## 1. Legend markup and positioning

- [x] 1.1 In `ChartPanel.jsx`, add a legend element (absolutely
      positioned, `top`/`left`, `z-index: 3` to clear `lightweight-charts`'
      own internal canvases — mirroring `.chart-panel__reset-zoom`'s
      existing technique) rendering five labeled values: `O`, `H`, `L`,
      `C`, `Vol`.
- [x] 1.2 Add `chart-panel.css` rules for the legend: neutral-colored
      labels, positioned to not overlap the existing top-right "Reset
      zoom" button, `aria-hidden="true"` (design.md Decision 5).
- [x] 1.3 Seed the legend's initial state from the latest row as soon as
      history data loads, so it's never blank before the first crosshair
      event fires.

## 2. Live crosshair updates

- [x] 2.1 Add `chart.subscribeCrosshairMove(handler)` in the same
      `useEffect` that creates the chart; unsubscribe (or rely on
      `chart.remove()`) on cleanup.
- [x] 2.2 In the handler: when `param.time` is set, look up
      `param.seriesData.get(candleSeriesRef.current)` and
      `param.seriesData.get(volumeSeriesRef.current)`; when either is
      missing (design.md Risk 1 — a gap/whitespace-only point), fall back
      to the latest-row default rather than rendering a partial legend.
- [x] 2.3 When `param.time` is `undefined` (crosshair not over the
      chart), fall back to the latest row.

## 3. Formatting and color

- [x] 3.1 Format O/H/L/C via
      `candleSeriesRef.current.priceFormatter().format(value)`.
- [x] 3.2 Format Volume via
      `volumeSeriesRef.current.priceFormatter().format(value)` — do not
      hand-roll a K/M/B abbreviation (design.md Decision 3).
- [x] 3.3 Color the five values using the same `close >= open` comparison
      `ChartPanel.jsx` already uses for volume-bar coloring, applied to
      the legend's current bar — do not introduce a second comparison.

## 4. Tests

- [x] 4.1 Add `ChartPanel.test.jsx` coverage: legend shows the latest
      row's values by default (no crosshair event fired yet).
- [x] 4.2 Add coverage: simulating a crosshair-move event updates the
      legend to the hovered bar's values.
- [x] 4.3 Add coverage: legend values are colored positive/negative
      matching the session's `close`/`open` comparison.
- [x] 4.4 Add coverage: a crosshair position with no candle data (e.g. a
      predicted-point whitespace date) falls back to the latest row
      rather than rendering blank/partial values.

## 5. Live verification

- [x] 5.1 Verify live (Playwright) on a real ticker (TCB): legend shows
      the latest session by default (confirmed against real backend
      data), and a genuine crosshair hover updated it to a different,
      earlier session — legend's Close matched the crosshair's own price
      badge exactly, colored green (up, close ≥ open) versus the
      default's red (down), confirming the hover-tracking path works
      end-to-end with real data, not just in the mocked unit tests.
- [x] 5.2 Verified in the same screenshots: the legend (top-left) and
      "Reset zoom" button (top-right) never overlap.
- [x] 5.3 Verified at 375px: the legend wraps to two lines (O/H/L/C, then
      Vol) via `flex-wrap` rather than overlapping the candles or
      clipping.
- [x] 5.4 Full frontend suite: 103/103 passing (99 pre-existing + 4 new
      legend tests), including the two-second full run after this
      section's live verification.
