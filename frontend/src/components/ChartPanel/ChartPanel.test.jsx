import { act } from 'react'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ChartPanel } from './ChartPanel'
import * as tickersApi from '../../api/tickers'
import { ApiError } from '../../api/client'
import { useTheme } from '../../hooks/useTheme'

// jsdom has no real CSS cascade, so readChartTheme()'s getComputedStyle(...).getPropertyValue()
// calls resolve to '' rather than a real token value — indistinguishable from each other for a
// per-bar colour assertion. Mocked with distinct fake values so the colour tests can assert on
// something meaningful, and held in a mutable object so a test can switch to a "dark" theme.
const theme = vi.hoisted(() => {
  const light = {
    surface: 'rgb(255, 255, 255)',
    line: 'rgb(200, 200, 200)',
    ink: 'rgb(20, 20, 20)',
    inkMuted: 'rgb(50, 50, 50)',
    candleUp: 'rgb(0, 128, 0)',
    candleDown: 'rgb(200, 0, 0)',
    accent: 'rgb(0, 0, 200)',
    bandFill: 'rgba(0, 0, 200, 0.15)',
  }
  const dark = {
    surface: 'rgb(23, 27, 34)',
    line: 'rgb(45, 53, 65)',
    ink: 'rgb(233, 236, 241)',
    inkMuted: 'rgb(166, 176, 190)',
    candleUp: 'rgb(47, 191, 128)',
    candleDown: 'rgb(240, 86, 107)',
    accent: 'rgb(126, 166, 255)',
    bandFill: 'rgba(126, 166, 255, 0.18)',
  }
  return { light, dark, current: light }
})
vi.mock('./chartTheme', () => ({ readChartTheme: () => ({ ...theme.current }) }))

// Captures every setData call made to the predicted-point line series, so
// tests can assert on the actual data points handed to lightweight-charts
// — jsdom can't render (or let us inspect) real canvas pixels, so this is
// the only way to verify the "exactly two points, ascending time" contract
// (design.md Decision 8) directly. vi.mock (not vi.spyOn on the module
// namespace) is required here — Vitest can't redefine an ESM named export
// directly, but a mock factory wrapping the real module works.
const lineSeriesDataCalls = []
// Primitives attached to the candle series (the range band)
// (their draw code cannot run in jsdom; the band geometry and state are what is asserted).
const attachedPrimitives = []
const detachedPrimitives = []
const volumeSeriesDataCalls = []
let fitContentCallCount = 0
const setAutoScaleCalls = []
const candleSetAutoScaleCalls = []
const volumeSetAutoScaleCalls = []
const visibleLogicalRangeCalls = []
const createChartCalls = []
const chartApplyOptionsCalls = []
const candleApplyOptionsCalls = []
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
      const originalChartApplyOptions = chart.applyOptions.bind(chart)
      chart.applyOptions = (options) => {
        chartApplyOptionsCalls.push(options)
        return originalChartApplyOptions(options)
      }
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
          const originalApplyOptions = series.applyOptions.bind(series)
          series.applyOptions = (options) => {
            candleApplyOptionsCalls.push(options)
            return originalApplyOptions(options)
          }
          const originalAttach = series.attachPrimitive.bind(series)
          series.attachPrimitive = (primitive) => {
            attachedPrimitives.push(primitive)
            return originalAttach(primitive)
          }
          const originalDetach = series.detachPrimitive.bind(series)
          series.detachPrimitive = (primitive) => {
            detachedPrimitives.push(primitive)
            return originalDetach(primitive)
          }
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

function rangeBody(overrides = {}) {
  return {
    ticker: 'TCB',
    as_of: '2026-08-10',
    status: 'ok',
    reasons: [],
    sigma_daily_pct: 1.4,
    range_5s_pct: 5,
    range_k: 1.1,
    range_coverage: 0.68,
    range_hit_rate: { rate: 0.7, n: 48 },
    ...overrides,
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
  attachedPrimitives.length = 0
  detachedPrimitives.length = 0
  volumeSeriesDataCalls.length = 0
  fitContentCallCount = 0
  setAutoScaleCalls.length = 0
  candleSetAutoScaleCalls.length = 0
  volumeSetAutoScaleCalls.length = 0
  stretchFactorCallsByPane[0].length = 0
  stretchFactorCallsByPane[1].length = 0
  visibleLogicalRangeCalls.length = 0
  createChartCalls.length = 0
  chartApplyOptionsCalls.length = 0
  candleApplyOptionsCalls.length = 0
  theme.current = theme.light
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
    vi.spyOn(tickersApi, 'fetchTickerRange').mockReturnValue(new Promise(() => {}))

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
    vi.spyOn(tickersApi, 'fetchTickerRange').mockRejectedValue(
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
    vi.spyOn(tickersApi, 'fetchTickerRange').mockRejectedValue(
      new ApiError('Feature computation failed', { status: 503 }),
    )

    const { unmount } = renderPanel('TCB')

    const message = await screen.findByText(/couldn't load the chart/i)
    expect(message).toBeInTheDocument()
    expect(screen.queryByText(/hasn't been loaded yet/i)).not.toBeInTheDocument()
    unmount()
  })

  it('renders no overlay once history and range load successfully', async () => {
    vi.spyOn(tickersApi, 'fetchTickerHistory').mockResolvedValue({
      ticker: 'TCB',
      rows: [
        { date: '2026-08-09', open: 10, high: 11, low: 9, close: 10.5, volume: 100 },
        { date: '2026-08-10', open: 10.5, high: 11.5, low: 10, close: 11, volume: 120 },
      ],
    })
    vi.spyOn(tickersApi, 'fetchTickerRange').mockResolvedValue(rangeBody())

    const { unmount } = renderPanel('TCB')

    await waitFor(() => {
      expect(screen.queryByText(/loading chart/i)).not.toBeInTheDocument()
    })
    expect(screen.queryByText(/couldn't load/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/hasn't been loaded/i)).not.toBeInTheDocument()
    unmount()
  })

  it('attaches one band primitive whose bounds are close x (1 +/- r/100) at the t+5 date', async () => {
    vi.spyOn(tickersApi, 'fetchTickerHistory').mockResolvedValue({
      ticker: 'TCB',
      rows: [
        { date: '2026-07-28', open: 10, high: 11, low: 9, close: 10.5, volume: 100 },
        // 2026-07-29 is a Wednesday.
        { date: '2026-07-29', open: 10.5, high: 11.5, low: 10, close: 11, volume: 120 },
      ],
    })
    vi.spyOn(tickersApi, 'fetchTickerRange').mockResolvedValue(rangeBody({ as_of: '2026-07-29', range_5s_pct: 5 }))

    const { unmount } = renderPanel('TCB')

    await waitFor(() => expect(attachedPrimitives[0]?.band).not.toBeNull())

    expect(attachedPrimitives).toHaveLength(1)
    const { time, upper, lower } = attachedPrimitives[0].band
    expect(time).toBe('2026-08-05')
    expect(upper).toBeCloseTo(11.55, 10)
    expect(lower).toBeCloseTo(10.45, 10)
    unmount()
  })

  it('draws the band bounds in the accent colour and its fill in the band-fill colour, never the candle colours', async () => {
    vi.spyOn(tickersApi, 'fetchTickerHistory').mockResolvedValue({
      ticker: 'TCB',
      rows: [{ date: '2026-07-29', open: 10.5, high: 11.5, low: 10, close: 11, volume: 120 }],
    })
    vi.spyOn(tickersApi, 'fetchTickerRange').mockResolvedValue(rangeBody({ as_of: '2026-07-29' }))

    const { unmount } = renderPanel('TCB')

    await waitFor(() => expect(attachedPrimitives[0]?.band).not.toBeNull())

    expect(attachedPrimitives[0].colors).toEqual({
      line: theme.light.accent,
      fill: theme.light.bandFill,
      text: theme.light.ink,
    })
    expect(Object.values(attachedPrimitives[0].colors)).not.toContain(theme.light.candleUp)
    expect(Object.values(attachedPrimitives[0].colors)).not.toContain(theme.light.candleDown)
    unmount()
  })

  it('labels the band with the same ±X.XX% text the Verdict panel shows', async () => {
    vi.spyOn(tickersApi, 'fetchTickerHistory').mockResolvedValue({
      ticker: 'TCB',
      rows: [{ date: '2026-07-29', open: 10.5, high: 11.5, low: 10, close: 11, volume: 120 }],
    })
    vi.spyOn(tickersApi, 'fetchTickerRange').mockResolvedValue(rangeBody({ as_of: '2026-07-29', range_5s_pct: 4.12 }))

    const { unmount } = renderPanel('TCB')

    await waitFor(() => expect(attachedPrimitives[0]?.band).not.toBeNull())

    expect(attachedPrimitives[0].band.label).toBe('±4.12%')
    unmount()
  })

  it('makes the price scale include both bounds through autoscaleInfo', async () => {
    vi.spyOn(tickersApi, 'fetchTickerHistory').mockResolvedValue({
      ticker: 'TCB',
      rows: [{ date: '2026-07-29', open: 10.5, high: 11.5, low: 10, close: 11, volume: 120 }],
    })
    vi.spyOn(tickersApi, 'fetchTickerRange').mockResolvedValue(rangeBody({ as_of: '2026-07-29', range_5s_pct: 20 }))

    const { unmount } = renderPanel('TCB')

    await waitFor(() => expect(attachedPrimitives[0]?.band).not.toBeNull())

    const info = attachedPrimitives[0].autoscaleInfo(0, 100)
    expect(info.priceRange.maxValue).toBeCloseTo(13.2, 10)
    expect(info.priceRange.minValue).toBeCloseTo(8.8, 10)
    unmount()
  })

  it('gives no valued point to any series between the last close and t+5; only whitespace reserves the axis slots', async () => {
    vi.spyOn(tickersApi, 'fetchTickerHistory').mockResolvedValue({
      ticker: 'TCB',
      rows: [
        { date: '2026-07-28', open: 10, high: 11, low: 9, close: 10.5, volume: 100 },
        { date: '2026-07-29', open: 10.5, high: 11.5, low: 10, close: 11, volume: 120 },
      ],
    })
    vi.spyOn(tickersApi, 'fetchTickerRange').mockResolvedValue(rangeBody({ as_of: '2026-07-29' }))

    const { unmount } = renderPanel('TCB')

    await waitFor(() => expect(lineSeriesDataCalls.some((call) => call.length > 0)).toBe(true))

    const finalData = lineSeriesDataCalls[lineSeriesDataCalls.length - 1]
    expect(finalData.map((point) => point.time)).toEqual([
      '2026-07-30',
      '2026-07-31',
      '2026-08-03',
      '2026-08-04',
      '2026-08-05',
    ])
    for (const call of lineSeriesDataCalls) {
      for (const point of call) expect(point).not.toHaveProperty('value')
    }
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
    vi.spyOn(tickersApi, 'fetchTickerRange').mockResolvedValue(rangeBody())

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

  it.each([
    ['a null range_5s_pct', () => vi.spyOn(tickersApi, 'fetchTickerRange').mockResolvedValue(rangeBody({ status: 'ineligible', range_5s_pct: null }))],
    ['a 404', () => vi.spyOn(tickersApi, 'fetchTickerRange').mockRejectedValue(new ApiError('nope', { status: 404 }))],
    ['a 5xx', () => vi.spyOn(tickersApi, 'fetchTickerRange').mockRejectedValue(new ApiError('boom', { status: 503 }))],
  ])('clears the band and reserves no future slots on %s', async (_name, arrange) => {
    vi.spyOn(tickersApi, 'fetchTickerHistory').mockResolvedValue({
      ticker: 'TCB',
      rows: [{ date: '2026-08-10', open: 10.5, high: 11.5, low: 10, close: 11, volume: 120 }],
    })
    arrange()

    const { unmount } = renderPanel('TCB')

    await waitFor(() => expect(candleSeriesInstance).not.toBeNull())
    await waitFor(() => expect(lineSeriesDataCalls.length).toBeGreaterThan(0))
    await waitForCountToStabilize(() => lineSeriesDataCalls.length)

    expect(attachedPrimitives[0].band).toBeNull()
    expect(attachedPrimitives[0].autoscaleInfo(0, 100)).toBeNull()
    for (const call of lineSeriesDataCalls) expect(call).toEqual([])
    unmount()
  })

  it('never lists a band bound in the OHLCV legend', async () => {
    vi.spyOn(tickersApi, 'fetchTickerHistory').mockResolvedValue({
      ticker: 'TCB',
      rows: [{ date: '2026-07-29', open: 10.5, high: 11.5, low: 10, close: 11, volume: 120 }],
    })
    vi.spyOn(tickersApi, 'fetchTickerRange').mockResolvedValue(rangeBody({ as_of: '2026-07-29', range_5s_pct: 5 }))

    const { container, unmount } = renderPanel('TCB')

    await waitFor(() => expect(attachedPrimitives[0]?.band).not.toBeNull())

    const legend = container.querySelector('.chart-panel__legend')
    expect(legend.textContent).not.toContain('11.55')
    expect(legend.textContent).not.toContain('10.45')
    unmount()
  })

  it('does not show the reset-zoom button in the empty/loading/error states', () => {
    const { unmount: unmountEmpty } = renderPanel(null)
    expect(screen.queryByRole('button', { name: /reset zoom/i })).not.toBeInTheDocument()
    unmountEmpty()

    vi.spyOn(tickersApi, 'fetchTickerHistory').mockReturnValue(new Promise(() => {}))
    vi.spyOn(tickersApi, 'fetchTickerRange').mockReturnValue(new Promise(() => {}))
    const { unmount: unmountLoading } = renderPanel('TCB')
    expect(screen.queryByRole('button', { name: /reset zoom/i })).not.toBeInTheDocument()
    unmountLoading()
  })

  it('shows a reset-zoom button once the chart has real data, and clicking it re-fits both the time scale and the price scale', async () => {
    vi.spyOn(tickersApi, 'fetchTickerHistory').mockResolvedValue({
      ticker: 'TCB',
      rows: [{ date: '2026-08-10', open: 10.5, high: 11.5, low: 10, close: 11, volume: 120 }],
    })
    vi.spyOn(tickersApi, 'fetchTickerRange').mockResolvedValue(rangeBody())

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
    vi.spyOn(tickersApi, 'fetchTickerRange').mockResolvedValue(rangeBody())

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
    vi.spyOn(tickersApi, 'fetchTickerRange').mockResolvedValue(rangeBody())

    const { unmount } = renderPanel('TCB')

    await waitFor(() => expect(fitContentCallCount).toBeGreaterThan(0))
    expect(visibleLogicalRangeCalls).toHaveLength(0)

    unmount()
  })

  it('reset-zoom restores the same default recent-activity window, not the full history', async () => {
    const rows = generateRows(750)
    vi.spyOn(tickersApi, 'fetchTickerHistory').mockResolvedValue({ ticker: 'TCB', rows })
    vi.spyOn(tickersApi, 'fetchTickerRange').mockResolvedValue(rangeBody())

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
    vi.spyOn(tickersApi, 'fetchTickerRange').mockResolvedValue(rangeBody())
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

  it('inks the legend values and marks the session direction with a swatch in the candle colour', async () => {
    mockHistoryAndPrediction()
    const { unmount } = renderPanel('TCB')

    // Default (latest row, index 1) is an up session (close >= open). `crosshairMoveHandler` is
    // registered at chart-creation time, before history data (and so the legend) exists — wait for
    // the legend's own text, not just the handler capture, before querying the element.
    await waitFor(() => expect(candleSeriesInstance).not.toBeNull())
    const priceFormatter = candleSeriesInstance.priceFormatter()
    await screen.findByText(priceFormatter.format(rows[rows.length - 1].close))
    const legend = document.querySelector('.chart-panel__legend')
    expect(legend.querySelector('.chart-panel__swatch')).toHaveAttribute('data-swatch', 'up')
    // The direction is the swatch's alone: the legend itself and its text carry no direction hue.
    expect(legend).not.toHaveAttribute('data-direction')
    for (const value of legend.querySelectorAll('.chart-panel__legend-value')) {
      expect(value).not.toHaveAttribute('style')
      expect(value).not.toHaveAttribute('data-direction')
    }

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
    expect(legend.querySelector('.chart-panel__swatch')).toHaveAttribute('data-swatch', 'down')

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

// A user pan or zoom, as the chart's inputs report it (a wheel turn on the chart).
const userZooms = () => fireEvent.wheel(document.querySelector('.chart-panel__canvas'))

// The chart history control (3M / 1Y / All): the visible window in sessions (rows), never calendar
// days, with no request when it changes.
describe('ChartPanel chart history control', () => {
  const group = () => screen.getByRole('group', { name: 'Chart history' })
  const button = (name) => within(group()).getByRole('button', { name })
  const lastRange = () => visibleLogicalRangeCalls[visibleLogicalRangeCalls.length - 1]

  async function open(count, ticker = 'TCB') {
    const rows = generateRows(count)
    const history = vi.spyOn(tickersApi, 'fetchTickerHistory').mockImplementation(async (t) => ({ ticker: t, rows }))
    const range = vi.spyOn(tickersApi, 'fetchTickerRange').mockResolvedValue(rangeBody())
    const view = renderPanel(ticker)
    await screen.findByRole('button', { name: /reset zoom/i })
    await waitForCountToStabilize(() => visibleLogicalRangeCalls.length + fitContentCallCount)
    return { rows, history, range, ...view }
  }

  it('is a group of three toggle buttons, with 3M pressed', async () => {
    const { unmount } = await open(750)

    expect(within(group()).getAllByRole('button').map((b) => b.textContent)).toEqual(['3M', '1Y', 'All'])
    expect(button('3M')).toHaveAttribute('aria-pressed', 'true')
    expect(button('1Y')).toHaveAttribute('aria-pressed', 'false')
    expect(button('All')).toHaveAttribute('aria-pressed', 'false')
    unmount()
  })

  it('opens on the last 60 sessions plus the band margin', async () => {
    const { unmount } = await open(750)

    expect(lastRange().from).toBe(750 - 60)
    expect(lastRange().to).toBeGreaterThan(750 - 1 + 5)
    unmount()
  })

  it('1Y shows the last 250 sessions and All shows every row served', async () => {
    const { unmount } = await open(750)

    await userEvent.click(button('1Y'))
    expect(lastRange().from).toBe(750 - 250)
    expect(button('1Y')).toHaveAttribute('aria-pressed', 'true')
    expect(button('3M')).toHaveAttribute('aria-pressed', 'false')

    await userEvent.click(button('All'))
    expect(lastRange().from).toBe(0)
    expect(lastRange().to).toBeGreaterThan(750 - 1 + 5)
    expect(button('All')).toHaveAttribute('aria-pressed', 'true')
    unmount()
  })

  it('counts sessions (rows), not calendar days: 3M is 60 rows however the dates fall', async () => {
    const rows = generateRows(400).filter((_, index) => index % 2 === 0) // 200 rows over 400 days
    vi.spyOn(tickersApi, 'fetchTickerHistory').mockResolvedValue({ ticker: 'TCB', rows })
    vi.spyOn(tickersApi, 'fetchTickerRange').mockResolvedValue(rangeBody())
    const { unmount } = renderPanel('TCB')
    await screen.findByRole('button', { name: /reset zoom/i })
    await waitFor(() => expect(visibleLogicalRangeCalls.length).toBeGreaterThan(0))

    expect(lastRange().from).toBe(200 - 60)
    unmount()
  })

  it('changing the window issues no request', async () => {
    const { history, range, unmount } = await open(750)

    await userEvent.click(button('1Y'))
    await userEvent.click(button('All'))
    await userEvent.click(button('3M'))

    expect(history).toHaveBeenCalledTimes(1)
    expect(range).toHaveBeenCalledTimes(1)
    unmount()
  })

  it.each([
    [200, { '3M': true, '1Y': false, All: false }],
    [249, { '3M': true, '1Y': false, All: false }],
    [250, { '3M': true, '1Y': true, All: false }],
    [251, { '3M': true, '1Y': true, All: true }],
    [600, { '3M': true, '1Y': true, All: true }],
    [60, { '3M': true, '1Y': false, All: false }],
  ])('with %i rows enables %j', async (count, enabled) => {
    const { unmount } = await open(count)

    for (const [name, isEnabled] of Object.entries(enabled)) {
      expect(button(name), name).toHaveProperty('disabled', !isEnabled)
    }
    unmount()
  })

  it('shows all of a short history and presses nothing when even 3M cannot be filled', async () => {
    const { unmount } = await open(30)

    for (const name of ['3M', '1Y', 'All']) {
      expect(button(name)).toBeDisabled()
      expect(button(name)).toHaveAttribute('aria-pressed', 'false')
    }
    expect(fitContentCallCount).toBeGreaterThan(0)
    expect(visibleLogicalRangeCalls).toHaveLength(0)
    unmount()
  })

  it('has every button disabled, and none pressed, with no ticker selected', () => {
    const { unmount } = renderPanel(null)

    for (const name of ['3M', '1Y', 'All']) expect(button(name)).toBeDisabled()
    unmount()
  })

  it('returns to 3M when another ticker is selected', async () => {
    const rows = generateRows(750)
    vi.spyOn(tickersApi, 'fetchTickerHistory').mockImplementation(async (t) => ({ ticker: t, rows }))
    vi.spyOn(tickersApi, 'fetchTickerRange').mockResolvedValue(rangeBody())
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const view = render(
      <QueryClientProvider client={queryClient}>
        <ChartPanel ticker="TCB" />
      </QueryClientProvider>,
    )
    await screen.findByRole('button', { name: /reset zoom/i })
    await userEvent.click(button('1Y'))
    expect(button('1Y')).toHaveAttribute('aria-pressed', 'true')

    view.rerender(
      <QueryClientProvider client={queryClient}>
        <ChartPanel ticker="VIB" />
      </QueryClientProvider>,
    )

    await waitFor(() => expect(button('3M')).toHaveAttribute('aria-pressed', 'true'))
    expect(button('1Y')).toHaveAttribute('aria-pressed', 'false')
    view.unmount()
  })

  it('Reset zoom restores the active window, not the opening one', async () => {
    const { unmount } = await open(750)
    await userEvent.click(button('1Y'))
    userZooms() // the user pans
    const before = visibleLogicalRangeCalls.length

    await userEvent.click(screen.getByRole('button', { name: /reset zoom/i }))

    expect(visibleLogicalRangeCalls.length).toBe(before + 1)
    expect(lastRange().from).toBe(750 - 250)
    expect(button('1Y')).toHaveAttribute('aria-pressed', 'true')
    unmount()
  })
})

describe('ChartPanel chart section', () => {
  it('gives the chart a text alternative stating the last close and the typical move', async () => {
    vi.spyOn(tickersApi, 'fetchTickerHistory').mockResolvedValue({
      ticker: 'TCB',
      rows: [{ date: '2026-07-29', open: 10.5, high: 11.5, low: 10, close: 11, volume: 120 }],
    })
    vi.spyOn(tickersApi, 'fetchTickerRange').mockResolvedValue(rangeBody({ as_of: '2026-07-29', range_5s_pct: 5 }))
    const { unmount } = renderPanel('TCB')

    const section = await screen.findByRole('region', { name: 'Price chart for TCB' })
    const alternative = await within(section).findByText('Last close 11.00; typical 5-session move ±5.00%')

    expect(alternative).toHaveClass('sr-only')
    unmount()
  })

  it('says the typical move is unavailable when /range serves no band', async () => {
    vi.spyOn(tickersApi, 'fetchTickerHistory').mockResolvedValue({
      ticker: 'TCB',
      rows: [{ date: '2026-07-29', open: 10.5, high: 11.5, low: 10, close: 11, volume: 120 }],
    })
    vi.spyOn(tickersApi, 'fetchTickerRange').mockResolvedValue(rangeBody({ status: 'ineligible', range_5s_pct: null }))
    const { unmount } = renderPanel('TCB')

    expect(await screen.findByText('Last close 11.00; typical 5-session move unavailable')).toBeInTheDocument()
    unmount()
  })

  it('has no text alternative before there is data', () => {
    const { unmount } = renderPanel(null)

    expect(screen.queryByText(/^Last close/)).not.toBeInTheDocument()
    unmount()
  })

  it('draws Reset zoom as the circular arrow, a 1.5px stroke path with an accessible name', async () => {
    vi.spyOn(tickersApi, 'fetchTickerHistory').mockResolvedValue({ ticker: 'TCB', rows: generateRows(10) })
    vi.spyOn(tickersApi, 'fetchTickerRange').mockResolvedValue(rangeBody())
    const { unmount } = renderPanel('TCB')

    const button = await screen.findByRole('button', { name: /reset zoom/i })
    const path = button.querySelector('path')

    expect(path.getAttribute('d')).toBe('M2 8a6 6 0 1 1 1.76 4.24M2 8V4m0 4h4')
    expect(path.getAttribute('stroke-width')).toBe('1.5')
    unmount()
  })
})

function ThemeToggle() {
  const { toggle } = useTheme()
  return (
    <button type="button" onClick={toggle}>
      toggle theme
    </button>
  )
}

describe('ChartPanel theme', () => {
  afterEach(() => {
    document.documentElement.removeAttribute('data-theme')
    localStorage.clear()
  })

  it('re-colours the chart, candles, volume and band on a theme change, keeping the visible window', async () => {
    const rows = generateRows(750)
    vi.spyOn(tickersApi, 'fetchTickerHistory').mockResolvedValue({ ticker: 'TCB', rows })
    vi.spyOn(tickersApi, 'fetchTickerRange').mockResolvedValue(rangeBody({ as_of: rows[rows.length - 1].date }))
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { unmount } = render(
      <QueryClientProvider client={queryClient}>
        <ThemeToggle />
        <ChartPanel ticker="TCB" />
      </QueryClientProvider>,
    )
    await waitFor(() => expect(attachedPrimitives[0]?.band).not.toBeNull())
    await waitForCountToStabilize(() => visibleLogicalRangeCalls.length + volumeSeriesDataCalls.length)
    const rangesBefore = visibleLogicalRangeCalls.length
    const volumeBefore = volumeSeriesDataCalls.length
    chartApplyOptionsCalls.length = 0
    candleApplyOptionsCalls.length = 0

    theme.current = theme.dark
    await userEvent.click(screen.getByRole('button', { name: 'toggle theme' }))

    await waitFor(() => expect(chartApplyOptionsCalls.length).toBeGreaterThan(0))
    const chartOptions = chartApplyOptionsCalls[chartApplyOptionsCalls.length - 1]
    expect(chartOptions.layout.background.color).toBe(theme.dark.surface)
    expect(chartOptions.layout.textColor).toBe(theme.dark.inkMuted)
    expect(chartOptions.grid.vertLines.color).toBe(theme.dark.line)
    expect(chartOptions.grid.horzLines.color).toBe(theme.dark.line)
    expect(chartOptions.rightPriceScale.borderColor).toBe(theme.dark.line)
    expect(chartOptions.timeScale.borderColor).toBe(theme.dark.line)
    expect(chartOptions.crosshair.vertLine.color).toBe(theme.dark.inkMuted)

    expect(candleApplyOptionsCalls[candleApplyOptionsCalls.length - 1]).toMatchObject({
      upColor: theme.dark.candleUp,
      downColor: theme.dark.candleDown,
      borderUpColor: theme.dark.candleUp,
      borderDownColor: theme.dark.candleDown,
      wickUpColor: theme.dark.candleUp,
      wickDownColor: theme.dark.candleDown,
    })

    // Volume colours are in the data, so the data is set again; every bar is one of the two colours.
    expect(volumeSeriesDataCalls.length).toBeGreaterThan(volumeBefore)
    const volume = volumeSeriesDataCalls[volumeSeriesDataCalls.length - 1]
    expect(volume.every((bar) => [theme.dark.candleUp, theme.dark.candleDown].includes(bar.color))).toBe(true)

    expect(attachedPrimitives[0].colors).toEqual({
      line: theme.dark.accent,
      fill: theme.dark.bandFill,
      text: theme.dark.ink,
    })

    // The visible window is not touched by a re-colour.
    expect(visibleLogicalRangeCalls).toHaveLength(rangesBefore)
    unmount()
  })
})

// The chart fills its card edge to edge (design.md Decision 15). jsdom has no layout, so the card
// width is stubbed (clientWidth) and the ResizeObserver replaced; what is asserted is the range the
// component asks the chart for.
describe('ChartPanel fills the card', () => {
  const PRICE_SCALE_PX = 82
  const LABEL_PX = '±5.00%'.length * 0.6 * 12 // the label is 12px monospace
  let cardWidth = 772
  let observers = []

  class FakeResizeObserver {
    constructor(callback) {
      this.callback = callback
      this.targets = []
      observers.push(this)
    }
    observe(target) {
      this.targets.push(target)
    }
    unobserve() {}
    disconnect() {
      this.targets = []
    }
  }

  const resizeCard = async (width) => {
    cardWidth = width
    const card = document.querySelector('.chart-panel')
    for (const observer of observers) if (observer.targets.includes(card)) observer.callback([{ target: card }])
    await new Promise((resolve) => setTimeout(resolve, 60)) // one animation frame
  }
  const lastRange = () => visibleLogicalRangeCalls[visibleLogicalRangeCalls.length - 1]

  const original = { resizeObserver: globalThis.ResizeObserver }

  beforeEach(() => {
    observers = []
    cardWidth = 772
    globalThis.ResizeObserver = FakeResizeObserver
    Object.defineProperty(HTMLElement.prototype, 'clientWidth', {
      configurable: true,
      get() {
        return this.classList?.contains('chart-panel') ? cardWidth : 0
      },
    })
  })

  afterEach(() => {
    globalThis.ResizeObserver = original.resizeObserver
    delete HTMLElement.prototype.clientWidth
  })

  async function open(width) {
    cardWidth = width
    const rows = generateRows(750)
    vi.spyOn(tickersApi, 'fetchTickerHistory').mockResolvedValue({ ticker: 'TCB', rows })
    vi.spyOn(tickersApi, 'fetchTickerRange').mockResolvedValue(rangeBody({ as_of: rows[rows.length - 1].date }))
    const view = renderPanel('TCB')
    await screen.findByRole('button', { name: /reset zoom/i })
    await waitForCountToStabilize(() => visibleLogicalRangeCalls.length)
    return view
  }

  it.each([772, 1252, 1892])('shows the same 60 sessions at a %ipx card, with room for the label inside the plot', async (width) => {
    const { unmount } = await open(width)

    const { from, to } = lastRange()
    expect(from).toBe(750 - 60)
    const plotPx = width - PRICE_SCALE_PX
    const slotPx = plotPx / (to - from + 1)
    const slotsRightOfBand = to - (750 - 1 + 5)
    expect(slotsRightOfBand).toBeGreaterThanOrEqual(1)
    expect(slotsRightOfBand * slotPx).toBeGreaterThanOrEqual(LABEL_PX)
    unmount()
  })

  it('leaves less margin on a wider card, since a slot is wider', async () => {
    const narrow = await open(772)
    const narrowExtra = lastRange().to - (750 - 1 + 5)
    narrow.unmount()
    visibleLogicalRangeCalls.length = 0
    const wide = await open(1892)

    expect(lastRange().to - (750 - 1 + 5)).toBeLessThan(narrowExtra)
    wide.unmount()
  })

  it('applies the window again when the card is resized', async () => {
    const { unmount } = await open(772)
    const before = visibleLogicalRangeCalls.length
    const widthBefore = lastRange().to

    await resizeCard(1252)

    expect(visibleLogicalRangeCalls.length).toBe(before + 1)
    expect(lastRange().from).toBe(750 - 60)
    expect(lastRange().to).not.toBe(widthBefore)
    unmount()
  })

  it('does not apply it again after the user zoomed or panned', async () => {
    const { unmount } = await open(772)
    userZooms()
    const before = visibleLogicalRangeCalls.length

    await resizeCard(1252)

    expect(visibleLogicalRangeCalls).toHaveLength(before)
    unmount()
  })

  it('counts a drag, the wheel and a touch on the chart as the user\'s, and a press on its buttons as not', async () => {
    const { unmount } = await open(772)
    const canvas = document.querySelector('.chart-panel__canvas')
    const before = visibleLogicalRangeCalls.length

    fireEvent.pointerDown(screen.getByRole('button', { name: /reset zoom/i }))
    await resizeCard(1252)
    expect(visibleLogicalRangeCalls.length).toBe(before + 1)

    for (const fire of [() => fireEvent.pointerDown(canvas), () => fireEvent.touchStart(canvas)]) {
      await userEvent.click(screen.getByRole('button', { name: /reset zoom/i })) // re-arm
      const armed = visibleLogicalRangeCalls.length
      fire()
      await resizeCard(772)
      expect(visibleLogicalRangeCalls.length).toBe(armed)
    }
    unmount()
  })

  it('Reset zoom and a tab change apply the window again, and re-arm the resize', async () => {
    const { unmount } = await open(772)
    userZooms()
    const afterZoom = visibleLogicalRangeCalls.length

    await userEvent.click(screen.getByRole('button', { name: /reset zoom/i }))
    expect(visibleLogicalRangeCalls.length).toBe(afterZoom + 1)
    await resizeCard(1252)
    expect(visibleLogicalRangeCalls.length).toBe(afterZoom + 2)

    userZooms()
    await userEvent.click(screen.getByRole('button', { name: '1Y' }))
    expect(lastRange().from).toBe(750 - 250)
    unmount()
  })

  it('stops observing the card when it unmounts', async () => {
    const { unmount } = await open(772)
    const card = document.querySelector('.chart-panel')
    expect(observers.some((observer) => observer.targets.includes(card))).toBe(true)

    unmount()

    expect(observers.every((observer) => !observer.targets.includes(card))).toBe(true)
  })
})
