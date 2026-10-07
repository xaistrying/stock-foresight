import { render, screen, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import * as tickersApi from '../../api/tickers'
import { ApiError } from '../../api/client'
import { INLINE_DISCLAIMER } from '../../lib/disclaimer'
import { RangeDisplay } from './RangeDisplay'

const AVAILABLE = {
  ticker: 'TCB',
  as_of: '2026-10-06',
  status: 'ok',
  reasons: [],
  sigma_daily_pct: 1.37,
  range_5s_pct: 3.2,
  range_k: 1.1,
  range_coverage: 0.68,
  range_hit_rate: { rate: 0.75, n: 48 },
}

function renderCard(ticker) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <RangeDisplay ticker={ticker} />
    </QueryClientProvider>,
  )
}

function mockRange(body) {
  return vi.spyOn(tickersApi, 'fetchTickerRange').mockResolvedValue({ ...AVAILABLE, ...body })
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('RangeDisplay: no ticker selected', () => {
  it('renders the full card shape with an N/A placeholder and fetches nothing', () => {
    const spy = vi.spyOn(tickersApi, 'fetchTickerRange')

    renderCard(null)

    expect(screen.getByRole('heading', { name: /range/i })).toBeInTheDocument()
    expect(screen.getByText('N/A')).toBeInTheDocument()
    expect(screen.getByText('As of —')).toBeInTheDocument()
    expect(screen.getByText(/5 trading sessions/i)).toBeInTheDocument()
    expect(spy).not.toHaveBeenCalled()
  })

  it('shows the disclaimer unconditionally', () => {
    renderCard(null)

    expect(screen.getByText(INLINE_DISCLAIMER)).toBeInTheDocument()
  })
})

describe('RangeDisplay: loading', () => {
  it('shows a loading message and no figure while the request is in flight', () => {
    vi.spyOn(tickersApi, 'fetchTickerRange').mockReturnValue(new Promise(() => {}))

    renderCard('TCB')

    expect(screen.getByText(/loading/i)).toBeInTheDocument()
    expect(screen.queryByText(/±/)).not.toBeInTheDocument()
  })
})

describe('RangeDisplay: available', () => {
  it('shows the unsigned half-width, its label, the as-of date and the nominal coverage in words', async () => {
    mockRange({})

    renderCard('TCB')

    expect(await screen.findByText('±3.2%')).toBeInTheDocument()
    expect(screen.getByText('Typical 5-session move')).toBeInTheDocument()
    expect(screen.getByText(/As of 2026-10-06/)).toBeInTheDocument()
    expect(screen.getByText(/about 2 in 3/)).toBeInTheDocument()
  })

  it('words the hit-rate as "N of the last M five-session moves" from rate and n', async () => {
    mockRange({ range_hit_rate: { rate: 0.75, n: 48 } })

    renderCard('TCB')

    expect(await screen.findByText('36 of the last 48 five-session moves')).toBeInTheDocument()
  })

  it('rounds N when rate x n is not a whole number', async () => {
    mockRange({ range_hit_rate: { rate: 0.7, n: 49 } }) // 34.3

    renderCard('TCB')

    expect(await screen.findByText('34 of the last 49 five-session moves')).toBeInTheDocument()
  })

  it('derives the coverage words from the response, not from a constant', async () => {
    mockRange({ range_coverage: 0.8 })

    renderCard('TCB')

    expect(await screen.findByText(/about 80%/)).toBeInTheDocument()
    expect(screen.queryByText(/about 2 in 3/)).not.toBeInTheDocument()
  })

  it('makes no coverage claim when range_coverage is null', async () => {
    mockRange({ status: 'uncalibrated', range_coverage: null })

    renderCard('TCB')

    expect(await screen.findByText('±3.2%')).toBeInTheDocument()
    expect(screen.queryByText(/coverage/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/2 in 3/)).not.toBeInTheDocument()
  })

  it.each([
    ['is missing', { range_hit_rate: null }],
    ['has n of 0', { range_hit_rate: { rate: null, n: 0 } }],
    ['has no rate', { range_hit_rate: { rate: null, n: 12 } }],
  ])('says "Not enough history to measure" when the hit-rate %s', async (_name, override) => {
    mockRange(override)

    renderCard('TCB')

    expect(await screen.findByText('Not enough history to measure')).toBeInTheDocument()
    expect(screen.queryByText(/of the last/)).not.toBeInTheDocument()
  })

  it('shows the disclaimer inside the same card as the coverage and hit-rate figures', async () => {
    mockRange({})

    renderCard('TCB')

    const card = (await screen.findByText('±3.2%')).closest('section')
    expect(within(card).getByText(INLINE_DISCLAIMER)).toBeInTheDocument()
    expect(within(card).getByText(/about 2 in 3/)).toBeInTheDocument()
    expect(within(card).getByText(/of the last 48/)).toBeInTheDocument()
  })

  it('never renders sigma_daily_pct', async () => {
    mockRange({ sigma_daily_pct: 1.37 })

    const { container } = renderCard('TCB')

    await screen.findByText('±3.2%')
    expect(container.textContent).not.toContain('1.37')
    expect(container.innerHTML).not.toContain('1.37')
  })

  it('carries no sign and no up/down attribute on the figure', async () => {
    mockRange({})

    renderCard('TCB')

    const figure = await screen.findByText('±3.2%')
    expect(figure.textContent).not.toMatch(/^[+-]/)
    expect(figure.closest('[data-direction]')).toBeNull()
  })

  it('decides by whether range_5s_pct is a number, so an unknown status still shows a served figure', async () => {
    mockRange({ status: 'some_future_status' })

    renderCard('TCB')

    expect(await screen.findByText('±3.2%')).toBeInTheDocument()
  })
})

describe('RangeDisplay: unavailable, not loaded and failed', () => {
  it('names the reason when range_5s_pct is null and reasons is non-empty', async () => {
    mockRange({ status: 'ineligible', reasons: ['stale'], range_5s_pct: null, sigma_daily_pct: null })

    renderCard('TCB')

    expect(await screen.findByText(/prices are out of date|stale/i)).toBeInTheDocument()
    expect(screen.queryByText(/±/)).not.toBeInTheDocument()
  })

  it('shows a generic message when range_5s_pct is null and there are no reasons', async () => {
    mockRange({ status: 'model_unavailable', reasons: [], range_5s_pct: null, sigma_daily_pct: null })

    renderCard('TCB')

    expect(await screen.findByText(/range unavailable for this ticker/i)).toBeInTheDocument()
    expect(screen.queryByText(/±/)).not.toBeInTheDocument()
  })

  it('treats a refusing status with a null range as unavailable even when the status says ok', async () => {
    mockRange({ status: 'ok', range_5s_pct: null })

    renderCard('TCB')

    expect(await screen.findByText(/range unavailable for this ticker/i)).toBeInTheDocument()
  })

  it('says the ticker has not been loaded on a 404', async () => {
    vi.spyOn(tickersApi, 'fetchTickerRange').mockRejectedValue(new ApiError('nope', { status: 404 }))

    renderCard('TCB')

    expect(await screen.findByText(/hasn't been loaded yet/i)).toBeInTheDocument()
    expect(screen.queryByText(/±/)).not.toBeInTheDocument()
  })

  it('shows a failure message on a 5xx', async () => {
    vi.spyOn(tickersApi, 'fetchTickerRange').mockRejectedValue(new ApiError('boom', { status: 503 }))

    renderCard('TCB')

    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn't load the range/i)
    expect(screen.queryByText(/±/)).not.toBeInTheDocument()
  })

  it('renders four distinct messages for unavailable, not loaded, failed and loading', async () => {
    const messages = []
    const scenarios = [
      () => mockRange({ range_5s_pct: null, reasons: [] }),
      () => vi.spyOn(tickersApi, 'fetchTickerRange').mockRejectedValue(new ApiError('x', { status: 404 })),
      () => vi.spyOn(tickersApi, 'fetchTickerRange').mockRejectedValue(new ApiError('x', { status: 500 })),
    ]
    for (const arrange of scenarios) {
      vi.restoreAllMocks()
      arrange()
      const { container, unmount } = renderCard('TCB')
      await vi.waitFor(() => expect(container.querySelector('[data-kind]:not([data-kind="loading"])')).not.toBeNull())
      messages.push(container.querySelector('[data-kind]').getAttribute('data-kind'))
      unmount()
    }

    expect(new Set(messages).size).toBe(messages.length)
  })

  it('keeps the disclaimer visible in every state', async () => {
    vi.spyOn(tickersApi, 'fetchTickerRange').mockRejectedValue(new ApiError('x', { status: 404 }))

    renderCard('TCB')

    await screen.findByText(/hasn't been loaded yet/i)
    expect(screen.getByText(INLINE_DISCLAIMER)).toBeInTheDocument()
  })
})
