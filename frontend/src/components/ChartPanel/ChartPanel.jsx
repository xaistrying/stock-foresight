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
import { useTheme } from '../../hooks/useTheme'
import { intermediateSessionDates, rangeBand } from '../../lib/sessionDates'
import { formatBandPct } from '../../lib/formatBand'
import { ApiError } from '../../api/client'
import { readChartTheme } from './chartTheme'
import { MONO_FONT_STACK, RangeBandPrimitive, bandLabelRoomPx } from './rangeBandPrimitive'
import './chart-panel.css'

// The chart history control: windows are counted in SESSIONS (rows served by /history), never
// calendar days (Rule 1: the unit of the horizon is the trading session). 3M is the opening view.
const WINDOWS = [
  { key: '3M', sessions: 60 },
  { key: '1Y', sessions: 250 },
  { key: 'All', sessions: Infinity },
]
const DEFAULT_WINDOW = '3M'
const WIDEST_FIRST = ['All', '1Y', '3M']

// A window is offered when the ticker has enough rows to fill it. All is offered only when it would
// show more than 1Y does, so it is never a duplicate of 1Y and never hides stored history.
function availableWindows(rowCount) {
  return { '3M': rowCount >= 60, '1Y': rowCount >= 250, All: rowCount > 250 }
}

// The window actually applied: the chosen one while it is available, else the widest that is.
function effectiveWindow(chosen, rowCount) {
  const available = availableWindows(rowCount)
  if (available[chosen]) return chosen
  return WIDEST_FIRST.find((key) => available[key]) ?? null
}

// Logical slots between the last candle and the t+5 band, and the width of the price scale, which
// the plot does not include.
const RIGHT_MARGIN_SESSIONS = 5
const PRICE_SCALE_WIDTH_PX = 82
// Used only before the card has a measured width (first paint, tests).
const FALLBACK_CARD_WIDTH_PX = 772

// Slots to leave right of the band so its label stays inside the plot. With `n` visible slots a slot
// is plot/n px wide, and the label needs `room` px: extra * plot / (shown + 5 + extra) >= room, which
// solves directly, so no measuring and no second pass.
function labelMarginSlots(shownSessions, plotPx, room) {
  if (!room) return 1
  const share = Math.min(0.5, room / plotPx)
  return Math.max(1, Math.ceil((share * (shownSessions + RIGHT_MARGIN_SESSIONS)) / (1 - share)))
}

// Price/volume pane split (design.md Decision 7, then Decision 10) — the price pane gets 3x the
// volume pane's share of total chart height (a 75/25 split). The divider is user-draggable; these
// constants are shared between chart creation and "Reset zoom" so a dragged split can be restored.
const PRICE_PANE_STRETCH_FACTOR = 3
const VOLUME_PANE_STRETCH_FACTOR = 1

const bandColors = (theme) => ({ line: theme.accent, fill: theme.bandFill, text: theme.ink })

/**
 * Chart panel: OHLC candles and volume from `GET /tickers/{ticker}/history`, no indicator overlay,
 * plus exactly one range band at t+5 — dashed accent bounds with a light fill and its `±X.XX%` label,
 * symmetric about the last close — when `GET /tickers/{ticker}/range` serves a numeric
 * `range_5s_pct`. Above the card a "Chart history" group (3M, 1Y, All) sets the visible window in
 * sessions without a request. Distinct states for no selection / loading / never-loaded (404) / error.
 *
 * The chart canvas container stays mounted across all states — the chart instance is created once and
 * never torn down just to show an overlay message. The chart follows the active theme, and is laid out
 * to fill its card: the window is applied again when the card is resized, unless the user has zoomed
 * or panned since.
 */
export function ChartPanel({ ticker }) {
  const cardRef = useRef(null)
  const containerRef = useRef(null)
  const chartRef = useRef(null)
  const candleSeriesRef = useRef(null)
  const bandSeriesRef = useRef(null)
  const bandPrimitiveRef = useRef(null)
  const volumeSeriesRef = useRef(null)
  // Latest history rows, mirrored into a ref so handlers registered once (the crosshair move) read
  // current data.
  const rowsRef = useRef([])
  // Whether the user has panned or zoomed since the window was last applied.
  const userAdjustedRef = useRef(false)
  // What the resize handler needs, kept fresh by an effect below.
  const latestRef = useRef({ windowKey: null, rowCount: 0, bandLabel: null })
  const [legend, setLegend] = useState(null)
  const [chosen, setChosen] = useState({ ticker: null, key: DEFAULT_WINDOW })
  const { theme: themeName } = useTheme()

  const historyQuery = useTickerHistory(ticker)
  const rangeQuery = useTickerRange(ticker)

  const rows = historyQuery.data?.rows ?? []
  const lastRow = rows[rows.length - 1]
  const range = rangeQuery.data
  // A chosen window belongs to the ticker it was chosen for: another ticker opens on 3M again.
  const windowKey = effectiveWindow(chosen.ticker === ticker ? chosen.key : DEFAULT_WINDOW, rows.length)
  const bandLabel = lastRow && range && Number.isFinite(range.range_5s_pct) ? formatBandPct(range.range_5s_pct) : null

  // Builds the legend's displayed strings from one OHLCV row, using each series' own priceFormatter()
  // so price/volume formatting never drifts from what the axis itself shows. `positive` reuses the
  // close >= open comparison the volume bars are already coloured by.
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

  // Chart + series are created once per mount and updated in place — recreating them on every data
  // change would drop the user's zoom/pan and re-run layout for no reason.
  useEffect(() => {
    if (!containerRef.current) return
    const theme = readChartTheme()

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: theme.surface },
        textColor: theme.inkMuted,
        // lightweight-charts takes one fontFamily for all of its own text (axis labels, crosshair
        // labels); nearly all of it is numeric, so it is the design's monospace stack.
        fontFamily: MONO_FONT_STACK,
        // The divider between the price and volume panes is a hairline, like every other line.
        panes: { separatorColor: theme.line },
      },
      grid: {
        vertLines: { color: theme.line },
        horzLines: { color: theme.line },
      },
      // minimumWidth pins the price-scale column to a fixed width — by default lightweight-charts
      // sizes it to the labels CURRENTLY visible (including the crosshair's price pill), so hovering
      // or a visible-range change could visibly resize the column. This column is shared by both
      // panes, and it is the VOLUME pane's abbreviated labels that vary across tickers ("1.5M" vs
      // "40M"); 82px was the tightest value confirmed live to stay constant across the nine original
      // tickers with 2px of headroom. A low-volume ticker that needs more: re-measure, don't guess.
      // PRICE_SCALE_WIDTH_PX is the same number: the plot is the card minus this column.
      rightPriceScale: { borderColor: theme.line, minimumWidth: PRICE_SCALE_WIDTH_PX },
      timeScale: { borderColor: theme.line },
      crosshair: { vertLine: { color: theme.inkMuted }, horzLine: { color: theme.inkMuted } },
      autoSize: true,
    })

    // No last-price line: it would run horizontally from the last close across the t+5 gap, and the
    // band is one position, with no line from the last close (design Decision 6).
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: theme.candleUp,
      downColor: theme.candleDown,
      borderUpColor: theme.candleUp,
      borderDownColor: theme.candleDown,
      wickUpColor: theme.candleUp,
      wickDownColor: theme.candleDown,
      priceLineVisible: false,
    })

    // Whitespace-only: it only reserves the t+1..t+5 slots on the time axis. The band itself is a
    // primitive attached once to the CANDLE series and fed through setBand (see the effect below): a
    // series with no data cannot convert a price to a coordinate, so the primitive lives on the one
    // that has data and shares the price scale.
    const bandSeries = chart.addSeries(LineSeries, {
      lastValueVisible: false,
      priceLineVisible: false,
      crosshairMarkerVisible: false,
    })
    const bandPrimitive = new RangeBandPrimitive(bandColors(theme))
    candleSeries.attachPrimitive(bandPrimitive)

    // Volume histogram — its own pane (index 1) below the price pane, sized as a fraction of the
    // chart's height via setStretchFactor so it scales with the card.
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

    // OHLCV legend: fires on every crosshair position change. `param.time` is unset whenever the
    // crosshair isn't over the plot — that is the one condition meaning "show the default". The
    // series data can also be empty for a real `param.time` that only the whitespace-only band slots
    // cover — guarded by falling back the same way.
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
      const current = rowsRef.current
      setLegend(buildLegendFromRow(current[current.length - 1]))
    }
    chart.subscribeCrosshairMove(handleCrosshairMove)

    // The user's own pan or zoom (a drag, the wheel, a pinch) is what a resize must leave alone, until
    // Reset zoom, a window change or new data. It is read from those inputs on the chart, not from the
    // visible range: the chart itself changes the range when its size changes, and that is not the user.
    const element = containerRef.current
    const markUserAdjusted = () => {
      userAdjustedRef.current = true
    }
    const USER_INPUTS = ['wheel', 'pointerdown', 'touchstart']
    USER_INPUTS.forEach((type) => element.addEventListener(type, markUserAdjusted, { passive: true }))

    return () => {
      chart.unsubscribeCrosshairMove(handleCrosshairMove)
      USER_INPUTS.forEach((type) => element.removeEventListener(type, markUserAdjusted))
      chart.remove()
      chartRef.current = null
      candleSeriesRef.current = null
      bandSeriesRef.current = null
      bandPrimitiveRef.current = null
      volumeSeriesRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // The theme changed (the toggle, or the operating system): re-read the tokens and re-colour the
  // chart in place. The volume bars' colours are in their data, so the data is set again; the
  // visible window is not touched.
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    const theme = readChartTheme()
    chart.applyOptions({
      layout: {
        background: { type: ColorType.Solid, color: theme.surface },
        textColor: theme.inkMuted,
        panes: { separatorColor: theme.line },
      },
      grid: { vertLines: { color: theme.line }, horzLines: { color: theme.line } },
      rightPriceScale: { borderColor: theme.line },
      timeScale: { borderColor: theme.line },
      crosshair: { vertLine: { color: theme.inkMuted }, horzLine: { color: theme.inkMuted } },
    })
    candleSeriesRef.current?.applyOptions({
      upColor: theme.candleUp,
      downColor: theme.candleDown,
      borderUpColor: theme.candleUp,
      borderDownColor: theme.candleDown,
      wickUpColor: theme.candleUp,
      wickDownColor: theme.candleDown,
    })
    volumeSeriesRef.current?.setData(volumeData(rowsRef.current, theme))
    bandPrimitiveRef.current?.setColors(bandColors(theme))
  }, [themeName])

  // Sets the visible window: the last `sessions` candles (every row for All) plus the band's margin on
  // the right. Falls back to fitContent() for a history shorter than the window — nothing to crop.
  const applyWindow = useCallback(() => {
    const chart = chartRef.current
    const { windowKey: key, rowCount, bandLabel: label } = latestRef.current
    if (!chart || rowCount === 0) return
    userAdjustedRef.current = false
    const sessions = WINDOWS.find((entry) => entry.key === key)?.sessions
    if (!key || (key !== 'All' && rowCount <= sessions)) {
      chart.timeScale().fitContent()
      return
    }
    const from = key === 'All' ? 0 : rowCount - sessions
    const cardWidth = cardRef.current?.clientWidth || FALLBACK_CARD_WIDTH_PX
    const plotPx = Math.max(1, cardWidth - PRICE_SCALE_WIDTH_PX)
    const extra = labelMarginSlots(rowCount - from, plotPx, bandLabelRoomPx(label))
    const visible = { from, to: rowCount - 1 + RIGHT_MARGIN_SESSIONS + extra }
    chart.timeScale().setVisibleLogicalRange(visible)
  }, [])

  useEffect(() => {
    latestRef.current = { windowKey, rowCount: rows.length, bandLabel }
  })

  // Candle data — OHLCV only, no derived-indicator series anywhere in this component (volume is raw
  // OHLCV data, not a derived indicator). New data, or a different window, applies the window.
  useEffect(() => {
    const series = candleSeriesRef.current
    const volumeSeries = volumeSeriesRef.current
    if (!series) return
    const current = historyQuery.data?.rows ?? []
    series.setData(
      current.map((row) => ({ time: row.date, open: row.open, high: row.high, low: row.low, close: row.close })),
    )
    volumeSeries?.setData(volumeData(current, readChartTheme()))
    applyWindow()

    // Keep the ref fresh for the crosshair handler, and (re)seed the legend to this ticker's latest
    // row so switching tickers never leaves a stale reading, and a fresh load is never blank.
    rowsRef.current = current
    setLegend(buildLegendFromRow(current[current.length - 1]))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [historyQuery.data, windowKey, applyWindow, buildLegendFromRow])

  // The band label arriving or changing (the range loads after the history) changes how much room
  // the right edge needs; the window follows it unless the user has moved off it.
  useEffect(() => {
    if (!userAdjustedRef.current) applyWindow()
  }, [bandLabel, applyWindow])

  // Fill the card: when it is resized, apply the window again one animation frame later, unless the
  // user has zoomed or panned since the last range this component set.
  useEffect(() => {
    const card = cardRef.current
    if (!card || typeof ResizeObserver === 'undefined') return undefined
    let frame = 0
    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() => {
        if (!userAdjustedRef.current) applyWindow()
      })
    })
    observer.observe(card)
    return () => {
      cancelAnimationFrame(frame)
      observer.disconnect()
    }
  }, [applyWindow])

  // Reset-zoom: once a user manually adjusts either axis, lightweight-charts leaves auto-fit mode
  // permanently on that axis, so this restores the ACTIVE window, both panes' auto-scale and the
  // pane divider's original split.
  function handleResetZoom() {
    applyWindow()
    candleSeriesRef.current?.priceScale().setAutoScale(true)
    volumeSeriesRef.current?.priceScale().setAutoScale(true)
    chartRef.current?.panes()[0]?.setStretchFactor(PRICE_PANE_STRETCH_FACTOR)
    chartRef.current?.panes()[1]?.setStretchFactor(VOLUME_PANE_STRETCH_FACTOR)
  }

  // The range band: ONE position (t+5), never a path. The whitespace-only line series carries the
  // t+1..t+5 slots — the time scale only reserves x-axis width for timestamps it has seen, so without
  // them t+5 would be drawn right next to the last bar, reading as "tomorrow". A whitespace point is
  // `{time}` with no `value`: it reserves axis space and plots nothing, so no series receives a valued
  // point between the last close and t+5.
  //
  // Cleared entirely when `range_5s_pct` is not a number (any refusing status), on 404 and on 5xx. The
  // decision keys on the number, not on `status`, so a status added later cannot leave a stale band.
  useEffect(() => {
    const series = bandSeriesRef.current
    const primitive = bandPrimitiveRef.current
    if (!series || !primitive) return

    const clearBand = () => {
      series.setData([])
      primitive.setBand(null)
    }

    const current = historyQuery.data?.rows ?? []
    const last = current[current.length - 1]
    const served = rangeQuery.data

    if (!last || !served || !Number.isFinite(served.range_5s_pct)) {
      clearBand()
      return
    }

    const band = rangeBand(last.close, served.as_of, served.range_5s_pct)

    // lightweight-charts requires strictly ascending times; guard against the (should-be-rare) case
    // where the approximated t+5 date lands on or before the last historical bar.
    if (band.time <= last.date) {
      clearBand()
      return
    }

    const slots = [...intermediateSessionDates(served.as_of), band.time].filter((date) => date > last.date)
    series.setData(slots.map((time) => ({ time })))
    primitive.setBand({ ...band, label: formatBandPct(served.range_5s_pct) })
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
      message: `${ticker} hasn't been loaded yet. Load it with the search above to see its chart.`,
    }
  } else if (genericError) {
    overlay = { kind: 'error', message: `Couldn't load the chart for ${ticker} — please try again.` }
  }

  const hasChartData = !overlay
  const available = availableWindows(hasChartData ? rows.length : 0)

  return (
    <div className="chart-stage">
      <div className="chart-history" role="group" aria-label="Chart history">
        {WINDOWS.map(({ key }) => (
          <button
            key={key}
            type="button"
            className="chart-history__button"
            aria-pressed={hasChartData && windowKey === key}
            disabled={!available[key]}
            onClick={() => setChosen({ ticker, key })}
          >
            {key}
          </button>
        ))}
      </div>
      <section
        ref={cardRef}
        className="chart-panel"
        aria-label={ticker ? `Price chart for ${ticker}` : 'Price chart'}
      >
        <div className="chart-panel__canvas" ref={containerRef} />
        {hasChartData && lastRow ? (
          <p className="sr-only">
            {`Last close ${lastRow.close.toFixed(2)}; typical 5-session move ${bandLabel ?? 'unavailable'}`}
          </p>
        ) : null}
        {hasChartData && legend && (
          // Values are in the primary ink; the swatch alone carries the session's direction, in the
          // candle colour (a mark, never a text colour).
          <div className="chart-panel__legend" aria-hidden="true">
            <span className="chart-panel__swatch" data-swatch={legend.positive ? 'up' : 'down'} />
            {[
              ['O', legend.open],
              ['H', legend.high],
              ['L', legend.low],
              ['C', legend.close],
              ['Vol', legend.volume],
            ].map(([label, value]) => (
              <span key={label} className="chart-panel__legend-item">
                <span className="chart-panel__legend-label">{label}</span>
                <span className="chart-panel__legend-value">{value}</span>
              </span>
            ))}
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
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
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
    </div>
  )
}

// Per-bar volume colours match CandlestickSeries' own up/down convention for the same session
// (close >= open), never re-derived independently.
function volumeData(rows, theme) {
  return rows.map((row) => ({
    time: row.date,
    value: row.volume,
    color: row.close >= row.open ? theme.candleUp : theme.candleDown,
  }))
}
