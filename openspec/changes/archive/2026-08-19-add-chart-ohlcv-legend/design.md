## Context

`ChartPanel.jsx` renders candles (`CandlestickSeries`) and a volume
histogram (`HistogramSeries`, `redesign-dashboard-visual-look` Decision
7's predecessor, `polish-dashboard-hierarchy-and-copy`) from `GET
/tickers/{ticker}/history` rows (`{date, open, high, low, close, volume}`).
Neither series currently exposes any per-bar value as text anywhere —
reading an exact number means eyeballing the price/volume axis. The
user's reference (a VNDIRECT-style screenshot) shows the standard
trading-terminal pattern: a small "`O` `H` `L` `C` `Vol`" readout fixed
to the chart's top-left corner, colored to match the session's up/down
direction, that updates as the crosshair moves and falls back to the
latest session when it isn't over the chart.

`lightweight-charts` v5 (already the project's dependency) exposes
`chart.subscribeCrosshairMove(handler)`, which fires on every crosshair
position change with a `param` object carrying `param.time` (undefined
when the crosshair isn't over the plot) and `param.seriesData` (a `Map`
keyed by series instance, valued by that series' bar data at the
crosshair's time). Each series' `ISeriesApi.priceFormatter()` returns an
`IPriceFormatter` with a `.format(value): string` method — the exact same
formatter the series' own price-scale/axis labels use (for
`HistogramSeries` with `priceFormat: {type: 'volume'}`, this is the
library's built-in "1.2K"/"12.67M"-style abbreviation).

## Goals / Non-Goals

**Goals:**
- A fixed top-left legend showing O/H/L/C/Volume for the crosshair-hovered
  session, falling back to the most recent session when the crosshair
  isn't over the chart — never blank.
- Reuse the exact formatting already used elsewhere (price precision,
  volume abbreviation) via each series' own `priceFormatter()`, rather
  than reimplementing number formatting a second time.
- Match the existing up/down color convention (candle/volume bar color)
  for the legend's values, not a new color decision.

**Non-Goals:**
- Not a cursor-following tooltip — corrected during proposal per live
  user feedback; the legend's position is fixed, only its content moves.
- Not adding a new plotted series, indicator, or any change to what's
  drawn on the canvas — text only.
- Not adding an accessible data-table alternative for the chart's OHLCV
  data generally — a real, separate gap (chart data has no non-visual
  fallback today), out of scope for this change, which only adds a
  sighted-user convenience layer on already-rendered data.
- Not touching the predicted point's own display — the legend's Volume
  field and OHLC fields come only from real historical rows.

## Decisions

### Decision 1: Fixed top-left legend, not a floating tooltip

A single absolutely-positioned element inside `.chart-panel__canvas`,
anchored `top`/`left` (mirroring `.chart-panel__reset-zoom`'s existing
`top`/`right` absolute-positioning technique, including its `z-index: 3`
to clear `lightweight-charts`' own internal canvases, which paint at
`z-index: 2`). Content updates in place; the element itself never moves,
unlike a cursor-following tooltip.

Domain rules: unaffected — a chart-overlay positioning decision only.

### Decision 2: Live updates via `subscribeCrosshairMove`, default to the latest bar

```js
chart.subscribeCrosshairMove((param) => {
  const candle = param.time
    ? param.seriesData.get(candleSeriesRef.current)
    : rows[rows.length - 1] // fallback: latest row, same shape
  const volume = param.time
    ? param.seriesData.get(volumeSeriesRef.current)?.value
    : rows[rows.length - 1]?.volume
  setLegend({ candle, volume })
})
```

`param.time` is `undefined` whenever the crosshair isn't over the plot
area (mouse hasn't entered, or has left) — this is the one condition
that means "show the default," not a separate "mouse leave" handler.
The initial legend state (before any crosshair event has ever fired,
right after data loads) is seeded from the same "latest row" fallback so
the legend is never blank momentarily on first render either.

Domain rules: unaffected — no new data source; `rows` is already fetched
history, and `param.seriesData` reads values already rendered on-canvas.

### Decision 3: Reuse each series' own `priceFormatter()` for text

`candleSeriesRef.current.priceFormatter().format(value)` formats O/H/L/C
identically to the price axis (2 decimals, per the existing
`CandlestickSeries` default). `volumeSeriesRef.current.priceFormatter().format(value)`
formats Volume identically to the volume axis's existing "1.2K"/"12.67M"
abbreviation (`priceFormat: {type: 'volume'}`, set when the series was
created — `redesign-dashboard-visual-look` design.md's Decision 1
correction already document this format's decimal-point behavior driving
the price-scale column width). No new formatting logic is written; this
change would otherwise risk a second, subtly different volume-abbreviation
implementation drifting out of sync with the axis's.

Alternative considered: reimplementing a `formatVolume()` helper (K/M/B
abbreviation) in JS, matching the library's documented behavior.
Rejected — `priceFormatter()` already returns the literal string the
library computes for that exact series; duplicating that logic risks
disagreeing with the axis itself over time (e.g. if a future
`lightweight-charts` upgrade changes its abbreviation thresholds).

Domain rules: unaffected — a formatting-reuse decision only.

### Decision 4: Directional color, matching the existing candle/volume convention

The legend's five values (not their `O`/`H`/`L`/`C`/`Vol` labels, which
stay a neutral ink color) render in `theme.positive` or `theme.negative`
based on `close >= open` for the legend's current bar — the exact same
comparison `ChartPanel.jsx` already uses to color that session's volume
bar to match its candle (comment: "Per-bar coloring matches
CandlestickSeries' own up/down convention for the same session... never
re-derived independently"). This change reuses that established
convention a third time rather than introducing a fourth up/down
comparison.

Domain rules: unaffected — reuses existing semantic color tokens
(`--color-positive`/`--color-negative`) already governed by the existing
"reserved for real signal" architecture; no new token or decorative use.

### Decision 5: `aria-hidden` on the legend

The legend is marked `aria-hidden="true"`. It duplicates information
already rendered on the canvas (which itself has no accessible
alternative today — a separate, real, pre-existing gap this change does
not attempt to close) and is driven by mouse-only crosshair movement a
screen-reader user cannot trigger. Marking it decorative avoids
implying a keyboard/screen-reader-accessible interaction exists where
none does, without making any existing accessibility gap worse.

Domain rules: unaffected.

## Risks / Trade-offs

- **[Risk]** `param.seriesData.get(series)` returns `undefined` for a
  series with no data point at the exact crosshair time (e.g. a gap, or
  the crosshair sitting on one of the predicted point's whitespace-only
  intermediate dates — `ChartPanel.jsx` already adds these for spacing,
  see its existing comment on `intermediateSessionDates`). → **Mitigation**:
  guard on the candle lookup being present before rendering hovered
  values; fall back to the latest-row default if a specific crosshair
  time has no candle data, rather than rendering a blank/partial legend.
- **[Risk]** Reusing `priceFormatter()` assumes both series' formatters
  are already configured the way the axis needs (2-decimal price,
  volume abbreviation) — if either series' options ever change, the
  legend's formatting silently follows, which is the intended behavior
  here but is worth re-confirming live after implementation, the same
  discipline this project applies to every other chart-visual decision.
- **[Risk]** Fixed top-left position could visually crowd the candles
  directly beneath it on a narrow/mobile viewport (`.chart-panel`'s
  existing `480px` breakpoint drops to an `18rem` height). → **Mitigation**:
  verify live on the mobile breakpoint; reduce legend font size or stack
  differently there if it visibly overlaps candle data, rather than
  assuming desktop sizing holds.
