import { act } from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ChartPanel } from './ChartPanel'
import * as tickersApi from '../../api/tickers'
import { ApiError } from '../../api/client'

// jsdom has no real CSS cascade, so readChartTheme()'s
// getComputedStyle(...).getPropertyValue('--color-positive') calls resolve
// to '' rather than a real token value — indistinguishable from each other
// for a per-bar color-matching assertion. Mocked with distinct fake values
// so the volume-coloring test (design.md Decision 7) can assert on
// something meaningful.
vi.mock('./chartTheme', () => ({
  readChartTheme: () => ({
    paper: 'rgb(255, 255, 255)',
    border: 'rgb(200, 200, 200)',
    ink2: 'rgb(50, 50, 50)',
    ink3: 'rgb(100, 100, 100)',
    positive: 'rgb(0, 128, 0)',
    negative: 'rgb(200, 0, 0)',
    accent: 'rgb(0, 0, 200)',
  }),
}))

// Captures every setData call made to the predicted-point line series, so
// tests can assert on the actual data points handed to lightweight-charts
// — jsdom can't render (or let us inspect) real canvas pixels, so this is
// the only way to verify the "exactly two points, ascending time" contract
// (design.md Decision 8) directly. vi.mock (not vi.spyOn on the module
// namespace) is required here — Vitest can't redefine an ESM named export
// directly, but a mock factory wrapping the real module works.
const lineSeriesDataCalls = []
const volumeSeriesDataCalls = []
let fitContentCallCount = 0
const setAutoScaleCalls = []
const candleSetAutoScaleCalls = []
const volumeSetAutoScaleCalls = []
const visibleLogicalRangeCalls = []
const createChartCalls = []
// Captures the handler ChartPanel registers via subscribeCrosshairMove so
// tests can simulate a crosshair position directly (jsdom fires no real
// mouse-over-canvas events) — add-chart-ohlcv-legend tasks.md section 4.
let crosshairMoveHandler = null
// setStretchFactor calls per pane index (design.md Decision 10) — a test
// asserts Reset zoom restores both panes' original stretch factors, not
// just that *some* pane was resized.
const stretchFactorCallsByPane = { 0: [], 1: [] }
// Real series instances, captured so a test can build a `param.seriesData`
// Map keyed by the exact same objects ChartPanel's crosshair handler looks
// them up by (add-chart-ohlcv-legend tasks.md section 4).
let candleSeriesInstance = null
let volumeSeriesInstance = null

vi.mock('lightweight-charts', async () => {
  const actual = await vi.importActual('lightweight-charts')
  return {
    ...actual,
    createChart: (...args) => {
      createChartCalls.push(args[1])
      const chart = actual.createChart(...args)
      const originalAddSeries = chart.addSeries.bind(chart)
      chart.addSeries = (definition, options, paneIndex) => {
        const series = originalAddSeries(definition, options, paneIndex)
        if (definition === actual.LineSeries) {
          const originalSetData = series.setData.bind(series)
          series.setData = (data) => {
            lineSeriesDataCalls.push(data)
            return originalSetData(data)
          }
        }
        if (definition === actual.HistogramSeries) {
          volumeSeriesInstance = series
          const originalSetData = series.setData.bind(series)
          series.setData = (data) => {
            volumeSeriesDataCalls.push(data)
            return originalSetData(data)
          }
          // Volume pane's own independent price scale (design.md Decision
          // 8) — wrapped the same way as CandlestickSeries below, but into
          // its own array, so a test can assert Reset zoom resets BOTH
          // panes' price scales, not just tell they were both called on
          // *some* series.
          const originalPriceScale = series.priceScale.bind(series)
          series.priceScale = () => {
            const priceScale = originalPriceScale()
            if (!priceScale.__setAutoScaleWrapped) {
              const originalSetAutoScale = priceScale.setAutoScale.bind(priceScale)
              priceScale.setAutoScale = (on) => {
                setAutoScaleCalls.push(on)
                volumeSetAutoScaleCalls.push(on)
                return originalSetAutoScale(on)
              }
              priceScale.__setAutoScaleWrapped = true
            }
            return priceScale
          }
        }
        if (definition === actual.CandlestickSeries) {
          candleSeriesInstance = series
          const originalPriceScale = series.priceScale.bind(series)
          series.priceScale = () => {
            const priceScale = originalPriceScale()
            if (!priceScale.__setAutoScaleWrapped) {
              const originalSetAutoScale = priceScale.setAutoScale.bind(priceScale)
              priceScale.setAutoScale = (on) => {
                setAutoScaleCalls.push(on)
                candleSetAutoScaleCalls.push(on)
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
      // chart.panes() returns a fresh array each call — wrap each pane's
      // setStretchFactor by index (same __wrapped-marker convention as
      // timeScale above), so calls from both chart-creation and Reset
      // zoom (design.md Decision 10) are observable per pane.
      const originalPanes = chart.panes.bind(chart)
      chart.panes = () => {
        const panes = originalPanes()
        panes.forEach((pane, index) => {
          if (pane.__setStretchFactorWrapped) return
          const originalSetStretchFactor = pane.setStretchFactor.bind(pane)
          pane.setStretchFactor = (factor) => {
            ;(stretchFactorCallsByPane[index] ??= []).push(factor)
            return originalSetStretchFactor(factor)
          }
          pane.__setStretchFactorWrapped = true
        })
        return panes
      }
      const originalSubscribeCrosshairMove = chart.subscribeCrosshairMove.bind(chart)
      chart.subscribeCrosshairMove = (handler) => {
        crosshairMoveHandler = handler
        return originalSubscribeCrosshairMove(handler)
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
  volumeSeriesDataCalls.length = 0
  fitContentCallCount = 0
  setAutoScaleCalls.length = 0
  candleSetAutoScaleCalls.length = 0
  volumeSetAutoScaleCalls.length = 0
  stretchFactorCallsByPane[0].length = 0
  stretchFactorCallsByPane[1].length = 0
  visibleLogicalRangeCalls.length = 0
  createChartCalls.length = 0
  crosshairMoveHandler = null
  candleSeriesInstance = null
  volumeSeriesInstance = null
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

  it('renders volume bars colored to match each session\'s up/down direction, matching CandlestickSeries\' own convention (design.md Decision 7)', async () => {
    vi.spyOn(tickersApi, 'fetchTickerHistory').mockResolvedValue({
      ticker: 'TCB',
      rows: [
        // Up session: close >= open.
        { date: '2026-08-06', open: 10, high: 11, low: 9, close: 10.5, volume: 1000 },
        // Down session: close < open.
        { date: '2026-08-07', open: 10.5, high: 10.8, low: 9.8, close: 10, volume: 2000 },
        // Flat session (close === open) counts as "up" — same >= comparison
        // CandlestickSeries itself uses via upColor/downColor.
        { date: '2026-08-10', open: 10, high: 10.2, low: 9.9, close: 10, volume: 1500 },
      ],
    })
    vi.spyOn(tickersApi, 'fetchTickerPrediction').mockResolvedValue({
      ticker: 'TCB',
      as_of: '2026-08-10',
      status: 'near_gap',
    })

    const { unmount } = renderPanel('TCB')

    await waitFor(() => {
      const lastCall = volumeSeriesDataCalls[volumeSeriesDataCalls.length - 1]
      expect(lastCall).toHaveLength(3)
    })

    const lastCall = volumeSeriesDataCalls[volumeSeriesDataCalls.length - 1]
    expect(lastCall[0]).toMatchObject({ time: '2026-08-06', value: 1000 })
    expect(lastCall[1]).toMatchObject({ time: '2026-08-07', value: 2000 })
    expect(lastCall[2]).toMatchObject({ time: '2026-08-10', value: 1500 })

    // Up and flat sessions get theme.positive, the down session
    // theme.negative — the same tokens CandlestickSeries itself uses for
    // upColor/downColor (readChartTheme is mocked above with distinct
    // fake values so this assertion is meaningful in jsdom).
    expect(lastCall[0].color).toBe('rgb(0, 128, 0)')
    expect(lastCall[1].color).toBe('rgb(200, 0, 0)')
    expect(lastCall[2].color).toBe('rgb(0, 128, 0)')

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
    // Both panes' independent price scales reset together (design.md
    // Decision 8) — not just the candlestick pane's. Before this fix, a
    // manual drag/zoom on the volume pane's own y-axis specifically
    // wasn't undone by this button.
    expect(candleSetAutoScaleCalls).toContain(true)
    expect(volumeSetAutoScaleCalls).toContain(true)
    // The pane divider's stretch-factor split resets to the original
    // 3:1 (price:volume) ratio too (design.md Decision 10) — before this
    // fix, a manually-dragged divider wasn't restored by this button.
    expect(stretchFactorCallsByPane[0]).toContain(3)
    expect(stretchFactorCallsByPane[1]).toContain(1)

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

// OHLCV legend (add-chart-ohlcv-legend tasks.md section 4). jsdom fires no
// real mouse-over-canvas events, so hover is simulated by invoking the
// handler ChartPanel registered via subscribeCrosshairMove directly
// (captured above as `crosshairMoveHandler`), with a `param.seriesData`
// Map keyed by the real series instances (`candleSeriesInstance`/
// `volumeSeriesInstance`) the same way lightweight-charts itself would key
// it.
describe('ChartPanel OHLCV legend', () => {
  // Every O/H/L/C/Volume value across both rows is distinct, so a test
  // can look up any one of them with `findByText` without colliding with
  // another value rendered elsewhere in the legend.
  const rows = [
    // Down session (close < open) — hovered in the "updates on hover"
    // test; distinct from the default (latest) row below.
    { date: '2026-08-06', open: 10, high: 10.2, low: 8.7, close: 8.8, volume: 1000 },
    // Up session (close >= open) — the most recent row, so this is what
    // the legend shows by default.
    { date: '2026-08-07', open: 9.5, high: 12.3, low: 9.4, close: 11.6, volume: 2000000 },
  ]

  function mockHistoryAndPrediction() {
    vi.spyOn(tickersApi, 'fetchTickerHistory').mockResolvedValue({ ticker: 'TCB', rows })
    vi.spyOn(tickersApi, 'fetchTickerPrediction').mockResolvedValue({
      ticker: 'TCB',
      as_of: rows[rows.length - 1].date,
      status: 'near_gap',
    })
  }

  it('shows the most recent session\'s OHLCV by default, before any crosshair event', async () => {
    mockHistoryAndPrediction()
    const { unmount } = renderPanel('TCB')

    await waitFor(() => expect(candleSeriesInstance).not.toBeNull())
    const priceFormatter = candleSeriesInstance.priceFormatter()
    const volumeFormatter = volumeSeriesInstance.priceFormatter()
    const latest = rows[rows.length - 1]

    expect(await screen.findByText(priceFormatter.format(latest.open))).toBeInTheDocument()
    expect(screen.getByText(priceFormatter.format(latest.high))).toBeInTheDocument()
    expect(screen.getByText(priceFormatter.format(latest.low))).toBeInTheDocument()
    expect(screen.getByText(priceFormatter.format(latest.close))).toBeInTheDocument()
    expect(screen.getByText(volumeFormatter.format(latest.volume))).toBeInTheDocument()

    unmount()
  })

  it('updates to the hovered session\'s OHLCV when the crosshair moves', async () => {
    mockHistoryAndPrediction()
    const { unmount } = renderPanel('TCB')

    // The legend only renders once `hasChartData` is true (the same
    // gate "Reset zoom" uses) — wait for the default row's close to
    // appear before simulating a hover, not just for the handler to be
    // registered (which happens at chart-creation time, before history
    // data resolves).
    await waitFor(() => expect(candleSeriesInstance).not.toBeNull())
    const defaultPriceFormatter = candleSeriesInstance.priceFormatter()
    await screen.findByText(defaultPriceFormatter.format(rows[rows.length - 1].close))
    const hovered = rows[0] // the down session, not the default latest one
    await act(async () => {
      crosshairMoveHandler({
        time: hovered.date,
        seriesData: new Map([
          [candleSeriesInstance, { open: hovered.open, high: hovered.high, low: hovered.low, close: hovered.close }],
          [volumeSeriesInstance, { value: hovered.volume }],
        ]),
      })
    })

    const priceFormatter = candleSeriesInstance.priceFormatter()
    expect(await screen.findByText(priceFormatter.format(hovered.close))).toBeInTheDocument()
    // The previously-default (latest) row's close is no longer shown.
    const latest = rows[rows.length - 1]
    expect(screen.queryByText(priceFormatter.format(latest.close))).not.toBeInTheDocument()

    unmount()
  })

  it('colors the legend to match the hovered session\'s up/down direction', async () => {
    mockHistoryAndPrediction()
    const { unmount } = renderPanel('TCB')

    // Default (latest row, index 1) is an up session (close >= open).
    // `crosshairMoveHandler` is registered at chart-creation time, before
    // history data (and so the legend element itself) exists — wait for
    // the legend's own text, not just the handler capture, before
    // querying the element.
    await waitFor(() => expect(candleSeriesInstance).not.toBeNull())
    const priceFormatter = candleSeriesInstance.priceFormatter()
    await screen.findByText(priceFormatter.format(rows[rows.length - 1].close))
    const legend = document.querySelector('.chart-panel__legend')
    expect(legend).toHaveAttribute('data-direction', 'up')

    // Hover the down session (index 0).
    const down = rows[0]
    await act(async () => {
      crosshairMoveHandler({
        time: down.date,
        seriesData: new Map([
          [candleSeriesInstance, { open: down.open, high: down.high, low: down.low, close: down.close }],
          [volumeSeriesInstance, { value: down.volume }],
        ]),
      })
    })
    expect(legend).toHaveAttribute('data-direction', 'down')

    unmount()
  })

  it('falls back to the most recent session when the crosshair has no candle data at that time', async () => {
    mockHistoryAndPrediction()
    const { unmount } = renderPanel('TCB')

    await waitFor(() => expect(crosshairMoveHandler).not.toBeNull())
    const priceFormatter = candleSeriesInstance.priceFormatter()
    const latest = rows[rows.length - 1]
    await screen.findByText(priceFormatter.format(latest.close))

    // Simulates the crosshair sitting on a whitespace-only point (e.g. one
    // of the predicted-point line's intermediate dates) — a real `time`,
    // but neither the candle nor volume series has data there.
    await act(async () => {
      crosshairMoveHandler({ time: '2099-01-01', seriesData: new Map() })
    })

    // Still shows the latest row's close — not blank, not a crash.
    expect(await screen.findByText(priceFormatter.format(latest.close))).toBeInTheDocument()

    unmount()
  })
})
