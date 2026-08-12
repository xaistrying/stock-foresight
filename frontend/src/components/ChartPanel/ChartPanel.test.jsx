import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ChartPanel } from './ChartPanel'
import * as tickersApi from '../../api/tickers'
import { ApiError } from '../../api/client'

// Captures every setData call made to the predicted-point line series, so
// tests can assert on the actual data points handed to lightweight-charts
// — jsdom can't render (or let us inspect) real canvas pixels, so this is
// the only way to verify the "exactly two points, ascending time" contract
// (design.md Decision 8) directly. vi.mock (not vi.spyOn on the module
// namespace) is required here — Vitest can't redefine an ESM named export
// directly, but a mock factory wrapping the real module works.
const lineSeriesDataCalls = []
let fitContentCallCount = 0
const setAutoScaleCalls = []
const visibleLogicalRangeCalls = []
const createChartCalls = []

vi.mock('lightweight-charts', async () => {
  const actual = await vi.importActual('lightweight-charts')
  return {
    ...actual,
    createChart: (...args) => {
      createChartCalls.push(args[1])
      const chart = actual.createChart(...args)
      const originalAddSeries = chart.addSeries.bind(chart)
      chart.addSeries = (definition, options) => {
        const series = originalAddSeries(definition, options)
        if (definition === actual.LineSeries) {
          const originalSetData = series.setData.bind(series)
          series.setData = (data) => {
            lineSeriesDataCalls.push(data)
            return originalSetData(data)
          }
        }
        if (definition === actual.CandlestickSeries) {
          const originalPriceScale = series.priceScale.bind(series)
          series.priceScale = () => {
            const priceScale = originalPriceScale()
            if (!priceScale.__setAutoScaleWrapped) {
              const originalSetAutoScale = priceScale.setAutoScale.bind(priceScale)
              priceScale.setAutoScale = (on) => {
                setAutoScaleCalls.push(on)
                return originalSetAutoScale(on)
              }
              priceScale.__setAutoScaleWrapped = true
            }
            return priceScale
          }
        }
        return series
      }
      const originalTimeScale = chart.timeScale.bind(chart)
      chart.timeScale = () => {
        const timeScale = originalTimeScale()
        // `timeScale()` returns the same underlying object on every call
        // (ChartPanel calls it from both the data-load effect and the
        // reset-zoom handler) — wrap fitContent exactly once per object,
        // guarded by a marker, so repeated calls to timeScale() don't
        // stack multiple counting wrappers on top of each other.
        if (!timeScale.__fitContentWrapped) {
          const originalFitContent = timeScale.fitContent.bind(timeScale)
          timeScale.fitContent = () => {
            fitContentCallCount += 1
            return originalFitContent()
          }
          const originalSetVisibleLogicalRange = timeScale.setVisibleLogicalRange.bind(timeScale)
          timeScale.setVisibleLogicalRange = (range) => {
            visibleLogicalRangeCalls.push(range)
            return originalSetVisibleLogicalRange(range)
          }
          timeScale.__fitContentWrapped = true
        }
        return timeScale
      }
      return chart
    },
  }
})

// Polls `readCount` until it reports the same value on two consecutive
// checks a tick apart — used where React Query may re-render (and thus
// re-run an effect) an unpredictable number of times while settling, so
// asserting an exact intermediate call count would be flaky.
async function waitForCountToStabilize(readCount) {
  let previous = readCount()
  await new Promise((resolve) => setTimeout(resolve, 0))
  while (readCount() !== previous) {
    previous = readCount()
    await new Promise((resolve) => setTimeout(resolve, 0))
  }
}

function renderPanel(ticker) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <ChartPanel ticker={ticker} />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.restoreAllMocks()
  lineSeriesDataCalls.length = 0
  fitContentCallCount = 0
  setAutoScaleCalls.length = 0
  visibleLogicalRangeCalls.length = 0
  createChartCalls.length = 0
})

// Generates `count` ascending daily OHLCV rows ending at `endDate` — used
// to exercise the >DEFAULT_VISIBLE_SESSIONS branch (setVisibleLogicalRange)
// distinctly from the short-history fitContent() fallback the other tests
// already cover.
function generateRows(count, endDate = '2026-08-10') {
  const end = new Date(`${endDate}T00:00:00Z`)
  return Array.from({ length: count }, (_, i) => {
    const date = new Date(end)
    date.setUTCDate(date.getUTCDate() - (count - 1 - i))
    return {
      date: date.toISOString().slice(0, 10),
      open: 10,
      high: 11,
      low: 9,
      close: 10.5,
      volume: 100,
    }
  })
}

describe('ChartPanel', () => {
  it('shows an empty-state prompt when no ticker is selected', () => {
    const { unmount } = renderPanel(null)
    expect(screen.getByText(/select a ticker to see its chart/i)).toBeInTheDocument()
    unmount()
  })

  it('shows a loading message while history is in flight', () => {
    vi.spyOn(tickersApi, 'fetchTickerHistory').mockReturnValue(new Promise(() => {}))
    vi.spyOn(tickersApi, 'fetchTickerPrediction').mockReturnValue(new Promise(() => {}))

    const { unmount } = renderPanel('TCB')

    expect(screen.getByText(/loading chart/i)).toBeInTheDocument()
    // Chart mounts even during loading (the canvas container is always
    // present, see ChartPanel's overlay pattern) — unmount to run
    // chart.remove() before the next test tears down jsdom's window.
    unmount()
  })

  it('shows a distinct not-loaded message for a 404 history response', async () => {
    vi.spyOn(tickersApi, 'fetchTickerHistory').mockRejectedValue(
      new ApiError('Ticker not found', { status: 404 }),
    )
    vi.spyOn(tickersApi, 'fetchTickerPrediction').mockRejectedValue(
      new ApiError('Ticker has not been loaded', { status: 404 }),
    )

    const { unmount } = renderPanel('VIB')

    expect(await screen.findByText(/hasn't been loaded yet/i)).toBeInTheDocument()
    unmount()
  })

  it('shows a generic error message for a non-404 history failure, distinct from not-loaded', async () => {
    vi.spyOn(tickersApi, 'fetchTickerHistory').mockRejectedValue(
      new ApiError('Internal error', { status: 500 }),
    )
    vi.spyOn(tickersApi, 'fetchTickerPrediction').mockRejectedValue(
      new ApiError('Feature computation failed', { status: 503 }),
    )

    const { unmount } = renderPanel('TCB')

    const message = await screen.findByText(/couldn't load the chart/i)
    expect(message).toBeInTheDocument()
    expect(screen.queryByText(/hasn't been loaded yet/i)).not.toBeInTheDocument()
    unmount()
  })

  it('renders no overlay once history and prediction load successfully', async () => {
    vi.spyOn(tickersApi, 'fetchTickerHistory').mockResolvedValue({
      ticker: 'TCB',
      rows: [
        { date: '2026-08-09', open: 10, high: 11, low: 9, close: 10.5, volume: 100 },
        { date: '2026-08-10', open: 10.5, high: 11.5, low: 10, close: 11, volume: 120 },
      ],
    })
    vi.spyOn(tickersApi, 'fetchTickerPrediction').mockResolvedValue({
      ticker: 'TCB',
      as_of: '2026-08-10',
      status: 'ok',
      predicted_log_return: 0.02,
    })

    const { unmount } = renderPanel('TCB')

    await waitFor(() => {
      expect(screen.queryByText(/loading chart/i)).not.toBeInTheDocument()
    })
    expect(screen.queryByText(/couldn't load/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/hasn't been loaded/i)).not.toBeInTheDocument()
    unmount()
  })

  it('draws exactly two VALUED points (last close, predicted price), plus whitespace-only points reserving the intermediate sessions', async () => {
    vi.spyOn(tickersApi, 'fetchTickerHistory').mockResolvedValue({
      ticker: 'TCB',
      rows: [
        { date: '2026-07-28', open: 10, high: 11, low: 9, close: 10.5, volume: 100 },
        // 2026-07-29 is a Wednesday.
        { date: '2026-07-29', open: 10.5, high: 11.5, low: 10, close: 11, volume: 120 },
      ],
    })
    vi.spyOn(tickersApi, 'fetchTickerPrediction').mockResolvedValue({
      ticker: 'TCB',
      as_of: '2026-07-29',
      status: 'ok',
      predicted_log_return: 0.02,
    })

    const { unmount } = renderPanel('TCB')

    await waitFor(() => {
      const lastCall = lineSeriesDataCalls[lineSeriesDataCalls.length - 1]
      expect(lastCall).toHaveLength(6) // last close + 4 whitespace + predicted point
    })

    const finalData = lineSeriesDataCalls[lineSeriesDataCalls.length - 1]
    // Point 1: the most recent historical close, unchanged.
    expect(finalData[0]).toEqual({ time: '2026-07-29', value: 11 })
    // Points 2-5: whitespace only (no `value` key) at the 4 intermediate
    // weekday sessions — reserve x-axis width, never plotted or connected
    // by the line (design.md Decision 8: no fabricated intermediate value).
    const intermediates = finalData.slice(1, 5)
    expect(intermediates.map((p) => p.time)).toEqual([
      '2026-07-30',
      '2026-07-31',
      '2026-08-03',
      '2026-08-04',
    ])
    for (const point of intermediates) {
      expect(point).not.toHaveProperty('value')
    }
    // Point 6: the predicted price, strictly ascending after all prior
    // points — never equal (would crash lightweight-charts).
    const predictedPoint = finalData[5]
    expect(predictedPoint.time).toBe('2026-08-05')
    expect(predictedPoint.time > intermediates[3].time).toBe(true)
    expect(predictedPoint.value).toBeCloseTo(11 * Math.exp(0.02), 5)

    unmount()
  })

  it('clears the predicted-point line entirely when the prediction is unavailable (near_gap)', async () => {
    vi.spyOn(tickersApi, 'fetchTickerHistory').mockResolvedValue({
      ticker: 'TCB',
      rows: [{ date: '2026-08-10', open: 10.5, high: 11.5, low: 10, close: 11, volume: 120 }],
    })
    vi.spyOn(tickersApi, 'fetchTickerPrediction').mockResolvedValue({
      ticker: 'TCB',
      as_of: '2026-08-10',
      status: 'near_gap',
    })

    const { unmount } = renderPanel('TCB')

    await waitFor(() => {
      expect(lineSeriesDataCalls.length).toBeGreaterThan(0)
    })
    // Every call (including the final one) must be empty — no predicted
    // point rendered for a near_gap prediction.
    for (const call of lineSeriesDataCalls) {
      expect(call).toEqual([])
    }

    unmount()
  })

  it('does not show the reset-zoom button in the empty/loading/error states', () => {
    const { unmount: unmountEmpty } = renderPanel(null)
    expect(screen.queryByRole('button', { name: /reset zoom/i })).not.toBeInTheDocument()
    unmountEmpty()

    vi.spyOn(tickersApi, 'fetchTickerHistory').mockReturnValue(new Promise(() => {}))
    vi.spyOn(tickersApi, 'fetchTickerPrediction').mockReturnValue(new Promise(() => {}))
    const { unmount: unmountLoading } = renderPanel('TCB')
    expect(screen.queryByRole('button', { name: /reset zoom/i })).not.toBeInTheDocument()
    unmountLoading()
  })

  it('shows a reset-zoom button once the chart has real data, and clicking it re-fits both the time scale and the price scale', async () => {
    vi.spyOn(tickersApi, 'fetchTickerHistory').mockResolvedValue({
      ticker: 'TCB',
      rows: [{ date: '2026-08-10', open: 10.5, high: 11.5, low: 10, close: 11, volume: 120 }],
    })
    vi.spyOn(tickersApi, 'fetchTickerPrediction').mockResolvedValue({
      ticker: 'TCB',
      as_of: '2026-08-10',
      status: 'near_gap',
    })

    const { unmount } = renderPanel('TCB')

    const button = await screen.findByRole('button', { name: /reset zoom/i })
    // The automatic fit-on-load can fire more than once while React Query
    // settles (each `historyQuery.data` reference change re-runs the
    // effect) — wait for the count to stop changing for a full tick before
    // treating it as a stable baseline, rather than assuming a fixed
    // number of automatic calls.
    await waitFor(() => expect(fitContentCallCount).toBeGreaterThan(0))
    await waitForCountToStabilize(() => fitContentCallCount)
    const callsBeforeClick = fitContentCallCount

    await userEvent.click(button)
    // x-axis: re-fits to the full data range.
    expect(fitContentCallCount).toBe(callsBeforeClick + 1)
    // y-axis: re-enables auto-scale, undoing a manual price-scale drag —
    // fitContent() alone only affects the time scale (design.md/tasks.md:
    // "if I manually adjust the x or y, it can not go back to auto mode").
    expect(setAutoScaleCalls).toContain(true)

    unmount()
  })

  it('opens on the most recent ~60 sessions (not the full history) when more than that is available', async () => {
    const rows = generateRows(750)
    vi.spyOn(tickersApi, 'fetchTickerHistory').mockResolvedValue({ ticker: 'TCB', rows })
    vi.spyOn(tickersApi, 'fetchTickerPrediction').mockResolvedValue({
      ticker: 'TCB',
      as_of: rows[rows.length - 1].date,
      status: 'near_gap',
    })

    const { unmount } = renderPanel('TCB')

    await waitFor(() => expect(visibleLogicalRangeCalls.length).toBeGreaterThan(0))
    const lastCall = visibleLogicalRangeCalls[visibleLogicalRangeCalls.length - 1]

    // Window covers the last 60 candles...
    expect(lastCall.to - lastCall.from).toBeGreaterThanOrEqual(60)
    expect(lastCall.from).toBe(rows.length - 60)
    // ...with a few extra logical slots of margin past the last candle so
    // the predicted point/dashed line isn't flush against the edge.
    expect(lastCall.to).toBeGreaterThan(rows.length - 1)
    // The full 750-session history is not what's initially visible.
    expect(fitContentCallCount).toBe(0)

    unmount()
  })

  it('falls back to fitContent() when there are fewer rows than the default window', async () => {
    const rows = generateRows(10)
    vi.spyOn(tickersApi, 'fetchTickerHistory').mockResolvedValue({ ticker: 'TCB', rows })
    vi.spyOn(tickersApi, 'fetchTickerPrediction').mockResolvedValue({
      ticker: 'TCB',
      as_of: rows[rows.length - 1].date,
      status: 'near_gap',
    })

    const { unmount } = renderPanel('TCB')

    await waitFor(() => expect(fitContentCallCount).toBeGreaterThan(0))
    expect(visibleLogicalRangeCalls).toHaveLength(0)

    unmount()
  })

  it('reset-zoom restores the same default recent-activity window, not the full history', async () => {
    const rows = generateRows(750)
    vi.spyOn(tickersApi, 'fetchTickerHistory').mockResolvedValue({ ticker: 'TCB', rows })
    vi.spyOn(tickersApi, 'fetchTickerPrediction').mockResolvedValue({
      ticker: 'TCB',
      as_of: rows[rows.length - 1].date,
      status: 'near_gap',
    })

    const { unmount } = renderPanel('TCB')

    const button = await screen.findByRole('button', { name: /reset zoom/i })
    await waitFor(() => expect(visibleLogicalRangeCalls.length).toBeGreaterThan(0))
    await waitForCountToStabilize(() => visibleLogicalRangeCalls.length)
    const callsBeforeClick = visibleLogicalRangeCalls.length

    await userEvent.click(button)

    expect(visibleLogicalRangeCalls.length).toBe(callsBeforeClick + 1)
    expect(fitContentCallCount).toBe(0)

    unmount()
  })

  it('pins the price scale to a fixed minimum width so it does not resize on interaction (e.g. Reset zoom, crosshair hover)', () => {
    // lightweight-charts auto-sizes the price-scale column to fit
    // whatever labels are currently visible (including the crosshair's
    // price badge) — minimumWidth stops that column from visibly
    // resizing whenever the visible price range or crosshair state
    // changes, e.g. after clicking Reset zoom.
    const { unmount } = renderPanel('TCB')

    expect(createChartCalls).toHaveLength(1)
    expect(createChartCalls[0].rightPriceScale.minimumWidth).toBeGreaterThan(0)

    unmount()
  })
})
