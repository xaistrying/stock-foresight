import { useCallback, useEffect, useRef, useState } from 'react'
import {
  CandlestickSeries,
  ColorType,
  HistogramSeries,
  LineSeries,
  createChart,
} from 'lightweight-charts'
import { useTickerHistory } from '../../hooks/useTickerHistory'
import { useTickerRange } from '../../hooks/useTickerRange'
import { intermediateSessionDates, rangeBand } from '../../lib/sessionDates'
import { ApiError } from '../../api/client'
import { readChartTheme } from './chartTheme'
import { RangeBandPrimitive } from './rangeBandPrimitive'
import './chart-panel.css'

// Default zoom (post-ship revision): opening a ticker used to fitContent()
// the entire 750-session history, squeezing the recent candles (and the
// range band) into a thin sliver at the right edge. This instead
// shows the most recent DEFAULT_VISIBLE_SESSIONS candles, with a few extra
// logical slots of right margin so the t+5 range band isn't flush against
// the canvas edge. Same window "Reset zoom" restores.
const DEFAULT_VISIBLE_SESSIONS = 60
const RIGHT_MARGIN_SESSIONS = 5

// Price/volume pane split (design.md Decision 7, then Decision 10) — the
// price pane gets 3x the volume pane's share of total chart height (a
// 75/25 split). The divider between the two panes is user-draggable
// (lightweight-charts default behavior); these constants are shared
// between chart-creation and "Reset zoom" so a manually-dragged split is
// restorable to the same original ratio, not a magic number duplicated
// in two places.
const PRICE_PANE_STRETCH_FACTOR = 3
const VOLUME_PANE_STRETCH_FACTOR = 1

/**
 * Chart panel: OHLC candles from `GET /tickers/{ticker}/history`, no
 * indicator overlay, plus exactly one range band at t+5 — dashed upper and
 * lower bounds with a light fill, symmetric about the last close, in a
 * neutral colour — when `GET /tickers/{ticker}/range` serves a numeric
 * `range_5s_pct`. Distinct states for no selection / loading / never-loaded
 * (404) / error.
 *
 * The chart canvas container stays mounted across all states — the chart
 * instance is created once and never torn down just to show an overlay
 * message, so a loading -> loaded transition doesn't destroy and rebuild
 * the chart (and its zoom/pan) unnecessarily. States render as an overlay
 * on top of the (possibly empty) canvas instead of replacing it.
 *
 * A fixed top-left OHLCV legend (add-chart-ohlcv-legend) tracks the
 * crosshair-hovered session via `subscribeCrosshairMove`, falling back to
 * the most recent session when the crosshair isn't over the chart — see
 * `buildLegendFromRow`/`handleCrosshairMove` below.
 */
export function ChartPanel({ ticker }) {
  const containerRef = useRef(null)
  const chartRef = useRef(null)
  const candleSeriesRef = useRef(null)
  const bandSeriesRef = useRef(null)
  const bandPrimitiveRef = useRef(null)
  const volumeSeriesRef = useRef(null)
  // Latest history rows, mirrored into a ref (add-chart-ohlcv-legend
  // Decision 2) so the crosshair-move handler registered once in the
  // chart-creation effect below can always read *current* data — that
  // effect's own closure is fixed at chart-creation time, but `.current`
  // is read fresh on every crosshair event.
  const rowsRef = useRef([])
  const [legend, setLegend] = useState(null)

  const historyQuery = useTickerHistory(ticker)
  const rangeQuery = useTickerRange(ticker)

  // Builds the legend's displayed strings from one OHLCV row, using each
  // series' own `priceFormatter()` (add-chart-ohlcv-legend Decision 3) so
  // price/volume formatting never drifts from what the axis itself shows
  // — no separate K/M/B abbreviation logic is written here. `positive`
  // reuses the exact `close >= open` comparison the volume bars are
  // already colored by (Decision 4), not a new comparison.
  const buildLegendFromRow = useCallback((row) => {
    const candleSeries = candleSeriesRef.current
    const volumeSeries = volumeSeriesRef.current
    if (!row || !candleSeries || !volumeSeries) return null
    const priceFormatter = candleSeries.priceFormatter()
    const volumeFormatter = volumeSeries.priceFormatter()
    return {
      open: priceFormatter.format(row.open),
      high: priceFormatter.format(row.high),
      low: priceFormatter.format(row.low),
      close: priceFormatter.format(row.close),
      volume: volumeFormatter.format(row.volume),
      positive: row.close >= row.open,
    }
  }, [])

  // Chart + series are created once per mount and updated in place —
  // recreating them on every data change would drop the user's zoom/pan
  // and re-run layout for no reason.
  useEffect(() => {
    if (!containerRef.current) return
    const theme = readChartTheme()

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: theme.paper },
        textColor: theme.ink2,
        // redesign-dashboard-visual-look Decision 1: lightweight-charts
        // takes one fontFamily for all of its own text (price/time/volume
        // axis labels, crosshair labels) — virtually all of it is numeric,
        // so this is set to the app's numeric register (--font-mono)
        // rather than the body font. Hardcoded (not a CSS var lookup) the
        // same way the prior 'Inter, system-ui, sans-serif' value was —
        // lightweight-charts' layout option isn't itself CSS.
        fontFamily: "'IBM Plex Mono', ui-monospace, 'SF Mono', Consolas, monospace",
      },
      grid: {
        vertLines: { color: theme.border },
        horzLines: { color: theme.border },
      },
      // minimumWidth pins the price-scale column to a fixed width — by
      // default lightweight-charts auto-sizes it to fit whatever price
      // labels are CURRENTLY visible, including the crosshair's price
      // label (a padded pill background, wider than a plain tick of the
      // same digit count) — so hovering the chart, or any visible-range
      // change (e.g. Reset zoom re-enabling autoScale) landing on a range
      // with different-precision labels, could visibly resize the column.
      // This column is shared by BOTH panes (price and volume), and it's
      // the VOLUME pane's abbreviated tick labels that actually vary in
      // width across tickers, not the price labels: lightweight-charts'
      // 'volume' price format shows a decimal point for lower-magnitude
      // ticks ("1.5M") but not for round ones ("40M") — a real ticker
      // comparison (SAB, max ~1.65M volume in the default window) needed
      // 80px against every other TRAINING_TICKER's 76px, confirmed live.
      // 82px is the tightest value confirmed live to render as one true
      // constant across all 9 TRAINING_TICKERS (no fluctuation) while
      // still leaving 2px of headroom above SAB's measured 80px need —
      // narrower than an earlier 88px, which left a visibly wider gap
      // between the candles and the axis than any real ticker needs
      // today (user-reported). If a future low-volume searched-in ticker
      // ever needs more than 82px, re-measure live rather than guessing
      // a new headroom value.
      rightPriceScale: { borderColor: theme.border, minimumWidth: 82 },
      timeScale: { borderColor: theme.border },
      crosshair: { vertLine: { color: theme.ink3 }, horzLine: { color: theme.ink3 } },
      autoSize: true,
    })

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: theme.positive,
      downColor: theme.negative,
      borderUpColor: theme.positive,
      borderDownColor: theme.negative,
      wickUpColor: theme.positive,
      wickDownColor: theme.negative,
    })

    // Whitespace-only: it only reserves the t+1..t+5 slots on the time axis. The band itself is
    // a primitive attached once to the CANDLE series and fed through setBand (see the effect
    // below): a series with no data cannot convert a price to a coordinate, so the primitive
    // lives on the one that has data and shares the price scale.
    const bandSeries = chart.addSeries(LineSeries, {
      lastValueVisible: false,
      priceLineVisible: false,
      crosshairMarkerVisible: false,
    })
    const bandPrimitive = new RangeBandPrimitive(theme.ink)
    candleSeries.attachPrimitive(bandPrimitive)

    // Volume histogram (design.md Decision 7) — its own pane (index 1)
    // below the price pane, not overlaid into the candlesticks' price
    // scale. Sized as a fraction of total chart height via
    // setStretchFactor (roughly a quarter of the chart, price pane gets
    // the rest) so it scales with .chart-panel's own height, including
    // its mobile breakpoint, without separate breakpoint logic here.
    const volumeSeries = chart.addSeries(
      HistogramSeries,
      { priceFormat: { type: 'volume' }, priceLineVisible: false, lastValueVisible: false },
      1,
    )
    chart.panes()[0]?.setStretchFactor(PRICE_PANE_STRETCH_FACTOR)
    chart.panes()[1]?.setStretchFactor(VOLUME_PANE_STRETCH_FACTOR)

    chartRef.current = chart
    candleSeriesRef.current = candleSeries
    bandSeriesRef.current = bandSeries
    bandPrimitiveRef.current = bandPrimitive
    volumeSeriesRef.current = volumeSeries

    // OHLCV legend (add-chart-ohlcv-legend Decision 2): fires on every
    // crosshair position change. `param.time` is unset whenever the
    // crosshair isn't over the plot (mouse hasn't entered, or has left)
    // — that's the one condition meaning "show the default," not a
    // separate mouseleave handler. `param.seriesData.get(series)` can
    // also come back empty for a real `param.time` that only the
    // whitespace-only band-slot points cover (design.md Risk 1) —
    // guarded below by falling back the same way.
    const handleCrosshairMove = (param) => {
      const candleData = param.time && param.seriesData.get(candleSeries)
      const volumeData = param.time && param.seriesData.get(volumeSeries)
      if (candleData && volumeData) {
        setLegend(
          buildLegendFromRow({
            open: candleData.open,
            high: candleData.high,
            low: candleData.low,
            close: candleData.close,
            volume: volumeData.value,
          }),
        )
        return
      }
      const rows = rowsRef.current
      setLegend(buildLegendFromRow(rows[rows.length - 1]))
    }
    chart.subscribeCrosshairMove(handleCrosshairMove)

    return () => {
      chart.unsubscribeCrosshairMove(handleCrosshairMove)
      chart.remove()
      chartRef.current = null
      candleSeriesRef.current = null
      bandSeriesRef.current = null
      bandPrimitiveRef.current = null
      volumeSeriesRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Sets the time scale to the default "recent activity" window — the
  // most recent DEFAULT_VISIBLE_SESSIONS candles, plus a few logical slots
  // of right margin so the range band (drawn a few sessions past the last
  // candle, see the effect below) isn't flush against the canvas edge. Falls back to fitContent() for a short
  // history (fewer candles than the default window) — nothing to crop.
  const setDefaultVisibleRange = useCallback((candleCount) => {
    const chart = chartRef.current
    if (!chart || candleCount === 0) return
    if (candleCount <= DEFAULT_VISIBLE_SESSIONS) {
      chart.timeScale().fitContent()
      return
    }
    chart.timeScale().setVisibleLogicalRange({
      from: candleCount - DEFAULT_VISIBLE_SESSIONS,
      to: candleCount - 1 + RIGHT_MARGIN_SESSIONS,
    })
  }, [])

  // Candle data (8.1, 8.2) — OHLCV only, no derived-indicator series added
  // anywhere in this component (volume below is raw OHLCV data, not a
  // derived indicator — dashboard-ui spec's "no derived-indicator overlay"
  // requirement, design.md Decision 7). Opens on the recent-activity
  // window (above) rather than fitting the entire history, so a fresh
  // ticker selection doesn't squeeze months of candles (and the range
  // band) into a sliver at the right edge.
  useEffect(() => {
    const series = candleSeriesRef.current
    const volumeSeries = volumeSeriesRef.current
    if (!series) return
    const rows = historyQuery.data?.rows ?? []
    const theme = readChartTheme()
    series.setData(
      rows.map((row) => ({
        time: row.date,
        open: row.open,
        high: row.high,
        low: row.low,
        close: row.close,
      })),
    )
    // Per-bar coloring matches CandlestickSeries' own up/down convention
    // for the same session (close >= open, same comparison the candle
    // itself renders with via upColor/downColor above) — never re-derived
    // independently (design.md Decision 7 risk mitigation).
    volumeSeries?.setData(
      rows.map((row) => ({
        time: row.date,
        value: row.volume,
        color: row.close >= row.open ? theme.positive : theme.negative,
      })),
    )
    setDefaultVisibleRange(rows.length)

    // OHLCV legend (add-chart-ohlcv-legend tasks.md 1.3): keep the ref
    // fresh for the crosshair handler above, and (re)seed the legend to
    // this ticker's latest row — resetting any prior ticker's
    // crosshair-driven state, so switching tickers never leaves a stale
    // reading on screen, and a fresh load is never blank before the
    // first crosshair event fires.
    rowsRef.current = rows
    setLegend(buildLegendFromRow(rows[rows.length - 1]))
  }, [historyQuery.data, setDefaultVisibleRange, buildLegendFromRow])

  // Reset-zoom (post-ship revision) — once a user manually adjusts either
  // axis (drag/scroll/pinch on the time scale, or drag on the price scale),
  // lightweight-charts leaves auto-fit mode permanently on that axis and
  // won't self-correct on new data; there was previously no way back
  // without reselecting the ticker. Restores the same default recent-
  // activity window the initial load opens on, plus resets the price
  // scale's auto-scale — both the candlestick pane's (candleSeriesRef,
  // since the band's whitespace series shares the same right-side
  // price scale) and the volume pane's own independent price scale
  // (design.md Decision 8) — a manual drag/zoom on the volume pane's
  // y-axis specifically wasn't undone by this button before. Also
  // restores the pane divider to its original stretch-factor split
  // (design.md Decision 10) — dragging the divider between the price and
  // volume panes is a separate manual adjustment from either axis above,
  // and wasn't undone by this button before either.
  function handleResetZoom() {
    setDefaultVisibleRange(historyQuery.data?.rows?.length ?? 0)
    candleSeriesRef.current?.priceScale().setAutoScale(true)
    volumeSeriesRef.current?.priceScale().setAutoScale(true)
    chartRef.current?.panes()[0]?.setStretchFactor(PRICE_PANE_STRETCH_FACTOR)
    chartRef.current?.panes()[1]?.setStretchFactor(VOLUME_PANE_STRETCH_FACTOR)
  }

  // The range band: ONE position (t+5), never a path. The whitespace-only line series carries
  // the t+1..t+5 slots — lightweight-charts' time scale only reserves x-axis width for
  // timestamps it has actually seen (real bars or explicit whitespace points), so without them
  // t+5 would be drawn right next to the last bar, reading as "tomorrow". A whitespace point is
  // `{time}` with no `value`: it reserves axis space and plots nothing, so no series receives a
  // valued point between the last close and t+5. The band's bounds go to the primitive, which
  // draws them and reports them to the price scale.
  //
  // Cleared entirely when `range_5s_pct` is not a number (any refusing status), on 404 and on
  // 5xx. The decision keys on the number, not on `status`, so a status added later cannot leave
  // a stale band on screen.
  useEffect(() => {
    const series = bandSeriesRef.current
    const primitive = bandPrimitiveRef.current
    if (!series || !primitive) return

    const clearBand = () => {
      series.setData([])
      primitive.setBand(null)
    }

    const rows = historyQuery.data?.rows ?? []
    const lastRow = rows[rows.length - 1]
    const range = rangeQuery.data

    if (!lastRow || !range || !Number.isFinite(range.range_5s_pct)) {
      clearBand()
      return
    }

    const band = rangeBand(lastRow.close, range.as_of, range.range_5s_pct)

    // lightweight-charts requires strictly ascending times; guard against the (should-be-rare)
    // case where the approximated t+5 date lands on or before the last historical bar rather
    // than crashing setData.
    if (band.time <= lastRow.date) {
      clearBand()
      return
    }

    const slots = [...intermediateSessionDates(range.as_of), band.time].filter((date) => date > lastRow.date)
    series.setData(slots.map((time) => ({ time })))
    primitive.setBand(band)
  }, [historyQuery.data, rangeQuery.data])

  const notLoaded = historyQuery.isError && historyQuery.error instanceof ApiError && historyQuery.error.status === 404
  const genericError = historyQuery.isError && !notLoaded

  let overlay = null
  if (!ticker) {
    overlay = { kind: 'empty', message: 'Select a ticker to see its chart.' }
  } else if (historyQuery.isLoading) {
    overlay = { kind: 'loading', message: 'Loading chart…' }
  } else if (notLoaded) {
    overlay = {
      kind: 'empty',
      message: `${ticker} hasn't been loaded yet. Load it from the ticker panel to see its chart.`,
    }
  } else if (genericError) {
    overlay = { kind: 'error', message: `Couldn't load the chart for ${ticker} — please try again.` }
  }

  const hasChartData = !overlay

  return (
    <section
      className="chart-panel"
      aria-label={ticker ? `Price chart for ${ticker}` : 'Price chart'}
    >
      <div className="chart-panel__canvas" ref={containerRef} />
      {hasChartData && legend && (
        <div
          className="chart-panel__legend"
          data-direction={legend.positive ? 'up' : 'down'}
          aria-hidden="true"
        >
          <span className="chart-panel__legend-item">
            <span className="chart-panel__legend-label">O</span>
            <span className="chart-panel__legend-value">{legend.open}</span>
          </span>
          <span className="chart-panel__legend-item">
            <span className="chart-panel__legend-label">H</span>
            <span className="chart-panel__legend-value">{legend.high}</span>
          </span>
          <span className="chart-panel__legend-item">
            <span className="chart-panel__legend-label">L</span>
            <span className="chart-panel__legend-value">{legend.low}</span>
          </span>
          <span className="chart-panel__legend-item">
            <span className="chart-panel__legend-label">C</span>
            <span className="chart-panel__legend-value">{legend.close}</span>
          </span>
          <span className="chart-panel__legend-item">
            <span className="chart-panel__legend-label">Vol</span>
            <span className="chart-panel__legend-value">{legend.volume}</span>
          </span>
        </div>
      )}
      {hasChartData && (
        <button
          type="button"
          className="chart-panel__reset-zoom"
          onClick={handleResetZoom}
          aria-label="Reset zoom"
          title="Reset zoom"
        >
          <svg
            width="16"
            height="16"
            viewBox="0 0 16 16"
            fill="none"
            aria-hidden="true"
          >
            <path
              d="M2 8a6 6 0 1 1 1.76 4.24M2 8V4m0 4h4"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>
      )}
      {overlay && (
        <div
          className="chart-panel__overlay"
          data-kind={overlay.kind}
          role={overlay.kind === 'error' ? 'alert' : undefined}
        >
          {overlay.kind === 'loading' && <div className="chart-panel__spinner" aria-hidden="true" />}
          <p className="chart-panel__message">{overlay.message}</p>
        </div>
      )}
    </section>
  )
}
