## Why

The chart panel renders candlesticks and a volume histogram, but a user
has no way to read the exact Open/High/Low/Close/Volume for any given
session without eyeballing the axis — every real trading-terminal chart
(the user's own reference: a VNDIRECT-style screenshot) solves this with
a small always-visible OHLCV readout in the chart's top-left corner that
updates as the crosshair moves. This is a genuine data-legibility gap in
an already-data-dense dashboard, not a cosmetic addition.

## What Changes

- **OHLCV legend overlay**: a fixed-position text readout anchored to the
  chart panel's top-left corner, in the same "`O` `H` `L` `C` `Vol`"
  label + value format as the reference screenshot. Values reflect the
  candle currently under the crosshair; when the crosshair isn't over the
  chart, the legend shows the most recent (rightmost) session's values —
  the chart is never blank of a reading.
- **Directional coloring**: the four price values (O/H/L/C) and the
  volume value render in the same positive/negative color the candle
  itself uses for that session (close ≥ open → positive, else negative)
  — reusing the existing semantic color tokens and up/down convention
  already established for candles and the volume bars, not a new color
  decision.
- **Live updates via the crosshair, not a floating tooltip**: implemented
  with `lightweight-charts`' `subscribeCrosshairMove`, which fires on
  every crosshair position change and reports which bar (if any) is
  under it. The legend is a plain positioned HTML element overlaid on the
  chart container (the same technique the existing "Reset zoom" button
  already uses), not a cursor-following popup.
- Volume displays abbreviated (e.g. "41.9M"), matching the volume pane's
  own existing axis-label formatting — one formatting rule, not two.

**Explicitly out of scope:**
- No change to what's plotted on the chart itself (no new series, no
  indicator overlay) — this is a text readout of data already rendered as
  candles/bars, not a new visual element on the canvas.
- No change to the predicted point, its line, or its own value display —
  the legend reflects only real historical OHLCV rows from `GET
  /tickers/{ticker}/history`, never the predicted price.
- No hover tooltip that follows the cursor — the corrected design (per
  live user feedback during this proposal) is a fixed corner legend, not
  a floating box.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `dashboard-ui`: one new **ADDED** requirement — the chart panel SHALL
  display an OHLCV legend for the crosshair-hovered (or, absent a
  crosshair position, most recent) session, with values colored to match
  that session's up/down direction. No existing requirement's behavior
  changes; this is additive to the chart panel's existing candle/volume
  rendering.

## Domain rule interactions

- **Rules 1–6**: unaffected. This displays already-fetched historical
  OHLCV data (`GET /tickers/{ticker}/history`, the same rows already
  drawn as candles and volume bars) — no prediction, confidence,
  sentiment, or advice content is touched, and the predicted point's
  value is explicitly excluded from the legend (see Explicitly out of
  scope). Rule 2 (never show the raw log return) does not apply here —
  there is no log-return value anywhere in this feature, only real
  historical prices/volume already displayed elsewhere in the UI in
  numeric form (the candles/bars themselves).

## Impact

- `frontend/src/components/ChartPanel/ChartPanel.jsx` — subscribe to
  `subscribeCrosshairMove`, track the active/default bar's OHLCV, render
  the legend element.
- `frontend/src/components/ChartPanel/chart-panel.css` — legend
  positioning and typography (reuses existing tokens; no new ones
  anticipated).
- `openspec/specs/dashboard-ui/spec.md` — one new requirement (via this
  change's spec delta).
- `frontend/src/components/ChartPanel/ChartPanel.test.jsx` — new tests
  for the legend's default/hover/color behavior.
- **No backend, API, database, or model changes.** No new dependency —
  `lightweight-charts`' `subscribeCrosshairMove` is part of the library
  already in use.
