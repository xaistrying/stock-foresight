import { useCallback, useEffect, useRef } from 'react'
import {
  CandlestickSeries,
  ColorType,
  LineSeries,
  LineStyle,
  createChart,
} from 'lightweight-charts'
import { useTickerHistory } from '../../hooks/useTickerHistory'
import { useTickerPrediction } from '../../hooks/useTickerPrediction'
import {
  approximateTargetDate,
  intermediateSessionDates,
  logReturnToPrice,
} from '../../lib/logReturn'
import { ApiError } from '../../api/client'
import { readChartTheme } from './chartTheme'
import './chart-panel.css'

// Default zoom (post-ship revision): opening a ticker used to fitContent()
// the entire 750-session history, squeezing the recent candles (and the
// predicted point) into a thin sliver at the right edge. This instead
// shows the most recent DEFAULT_VISIBLE_SESSIONS candles, with a few extra
// logical slots of right margin so the dashed prediction line/point isn't
// flush against the canvas edge. Same window "Reset zoom" restores.
const DEFAULT_VISIBLE_SESSIONS = 60
const RIGHT_MARGIN_SESSIONS = 5

/**
 * Chart panel (tasks.md section 8): OHLC candles from `GET
 * /tickers/{ticker}/history`, no indicator overlay (8.2), plus exactly
 * one predicted point at t+5 joined to the last close by a single
 * straight dashed line when the selected ticker's prediction has
 * `status: "ok"` (8.3, design.md Decision 8). Distinct states for no
 * selection / loading / never-loaded (404) / error (8.1, 8.4).
 *
 * The chart canvas container stays mounted across all states — the chart
 * instance is created once and never torn down just to show an overlay
 * message, so a loading -> loaded transition doesn't destroy and rebuild
 * the chart (and its zoom/pan) unnecessarily. States render as an overlay
 * on top of the (possibly empty) canvas instead of replacing it.
 */
export function ChartPanel({ ticker }) {
  const containerRef = useRef(null)
  const chartRef = useRef(null)
  const candleSeriesRef = useRef(null)
  const predictionSeriesRef = useRef(null)

  const historyQuery = useTickerHistory(ticker)
  const predictionQuery = useTickerPrediction(ticker)

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
        fontFamily: 'Inter, system-ui, sans-serif',
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
      // 76px comfortably fits this app's price range (2 decimals, up to
      // ~5-6 characters) plus the crosshair badge's padding, with headroom.
      rightPriceScale: { borderColor: theme.border, minimumWidth: 76 },
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

    const predictionSeries = chart.addSeries(LineSeries, {
      color: theme.accent,
      lineWidth: 2,
      lineStyle: LineStyle.Dashed,
      pointMarkersVisible: true,
      lastValueVisible: false,
      priceLineVisible: false,
      crosshairMarkerVisible: false,
    })

    chartRef.current = chart
    candleSeriesRef.current = candleSeries
    predictionSeriesRef.current = predictionSeries

    return () => {
      chart.remove()
      chartRef.current = null
      candleSeriesRef.current = null
      predictionSeriesRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Sets the time scale to the default "recent activity" window — the
  // most recent DEFAULT_VISIBLE_SESSIONS candles, plus a few logical slots
  // of right margin so the dashed prediction line/point (drawn a few
  // sessions past the last candle, see the effect below) isn't flush
  // against the canvas edge. Falls back to fitContent() for a short
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

  // Candle data (8.1, 8.2) — OHLCV only, no indicator series added anywhere
  // in this component. Opens on the recent-activity window (above) rather
  // than fitting the entire history, so a fresh ticker selection doesn't
  // squeeze months of candles (and the predicted point) into a sliver at
  // the right edge.
  useEffect(() => {
    const series = candleSeriesRef.current
    if (!series) return
    const rows = historyQuery.data?.rows ?? []
    series.setData(
      rows.map((row) => ({
        time: row.date,
        open: row.open,
        high: row.high,
        low: row.low,
        close: row.close,
      })),
    )
    setDefaultVisibleRange(rows.length)
  }, [historyQuery.data, setDefaultVisibleRange])

  // Reset-zoom (post-ship revision) — once a user manually adjusts either
  // axis (drag/scroll/pinch on the time scale, or drag on the price scale),
  // lightweight-charts leaves auto-fit mode permanently on that axis and
  // won't self-correct on new data; there was previously no way back
  // without reselecting the ticker. Restores the same default recent-
  // activity window the initial load opens on, plus resets the price
  // scale's auto-scale (candleSeriesRef, since the predicted-point line
  // series shares the same right-side price scale).
  function handleResetZoom() {
    setDefaultVisibleRange(historyQuery.data?.rows?.length ?? 0)
    candleSeriesRef.current?.priceScale().setAutoScale(true)
  }

  // Single predicted point (8.3, design.md Decision 8) — exactly two DATA
  // points with a value (last historical close, t+5 predicted price), so
  // the line series draws one straight segment with nothing interpolated
  // between them — the model produces one scalar, never a day-by-day
  // trajectory, and this must never imply otherwise.
  //
  // Separately, lightweight-charts' time scale only reserves x-axis width
  // for timestamps it has actually seen (real bars or explicit whitespace
  // points) — with only 2 data points, it collapsed the 4 intervening
  // trading sessions and drew the predicted point immediately adjacent to
  // the last bar, reading as "tomorrow" instead of "5 sessions out". Fixed
  // by also passing t+1..t+4 as whitespace-only points ({time}, no
  // `value`) — these reserve axis space but carry no plotted value and are
  // never connected by the line, so they don't add a fabricated
  // intermediate value/point in violation of Decision 8, only correct
  // where the real predicted point sits on the axis.
  //
  // Cleared entirely for near_gap / 404 / 5xx (dashboard-ui spec: "No
  // predicted point when prediction is unavailable").
  useEffect(() => {
    const series = predictionSeriesRef.current
    if (!series) return

    const rows = historyQuery.data?.rows ?? []
    const lastRow = rows[rows.length - 1]
    const prediction = predictionQuery.data

    if (!lastRow || !prediction || prediction.status !== 'ok') {
      series.setData([])
      return
    }

    const predictedPrice = logReturnToPrice(prediction.predicted_log_return, lastRow.close)
    const targetDate = approximateTargetDate(prediction.as_of)

    // lightweight-charts requires strictly ascending times; guard against
    // the (should-be-rare) case where the approximated target date lands
    // on or before the last historical bar rather than crashing setData.
    if (targetDate <= lastRow.date) {
      series.setData([])
      return
    }

    const intermediateDates = intermediateSessionDates(prediction.as_of).filter(
      (date) => date > lastRow.date && date < targetDate,
    )

    series.setData([
      { time: lastRow.date, value: lastRow.close },
      ...intermediateDates.map((time) => ({ time })),
      { time: targetDate, value: predictedPrice },
    ])
  }, [historyQuery.data, predictionQuery.data])

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
