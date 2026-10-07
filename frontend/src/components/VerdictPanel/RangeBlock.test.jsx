import { screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import * as tickersApi from '../../api/tickers'
import { ApiError } from '../../api/client'
import { INLINE_DISCLAIMER } from '../../lib/disclaimer'
import { renderWithQuery } from '../../test/railFixtures'
import { RangeBlock } from './RangeBlock'

const AVAILABLE = {
  ticker: 'TCB',
  as_of: '2026-10-06',
  status: 'ok',
  reasons: [],
  sigma_daily_pct: 1.37,
  range_5s_pct: 4.12,
  range_k: 1.1,
  range_coverage: 0.68,
  range_hit_rate: { rate: 0.68, n: 50 },
}

const renderBlock = (ticker, props = {}) => renderWithQuery(<RangeBlock ticker={ticker} {...props} />)
const mockRange = (body) => vi.spyOn(tickersApi, 'fetchTickerRange').mockResolvedValue({ ...AVAILABLE, ...body })

afterEach(() => {
  vi.restoreAllMocks()
})

describe('RangeBlock: no ticker selected', () => {
  it('keeps the block\'s shape: the label, an N/A as large as a figure, and dashes for the check and coverage', () => {
    const spy = vi.spyOn(tickersApi, 'fetchTickerRange')

    const { container } = renderBlock(null)

    expect(screen.getByText('Typical 5-session move')).toBeInTheDocument()
    expect(screen.getByText('N/A')).toHaveClass('range-block__figure', 'range-block__figure--placeholder')
    expect(container.querySelectorAll('.range-block__slot')).toHaveLength(2)
    for (const slot of container.querySelectorAll('.range-block__slot')) expect(slot).toHaveTextContent('—')
    expect(spy).not.toHaveBeenCalled()
  })

  it('has the same number of lines as a populated block, so selecting a ticker adds none', async () => {
    const { container, unmount } = renderBlock(null)
    const placeholderSlots = container.querySelectorAll('.range-block__slot').length
    unmount()
    mockRange({})
    const populated = renderBlock('TCB')
    await screen.findByText('±4.12%')

    expect(placeholderSlots).toBe(2)
    expect(populated.container.querySelectorAll('.range-block__slot')).toHaveLength(placeholderSlots)
  })

  it('shows the disclaimer when it is the only thing the block stands next to', () => {
    renderBlock(null, { disclaimer: true })

    expect(screen.getByText(INLINE_DISCLAIMER)).toBeInTheDocument()
  })

  it('shows no disclaimer of its own by default: the Verdict panel carries it', () => {
    renderBlock(null)

    expect(screen.queryByText(INLINE_DISCLAIMER)).not.toBeInTheDocument()
  })
})

describe('RangeBlock: loading', () => {
  it('shows a loading message and no figure while the request is in flight', () => {
    vi.spyOn(tickersApi, 'fetchTickerRange').mockReturnValue(new Promise(() => {}))

    renderBlock('TCB')

    expect(screen.getByText(/loading/i)).toBeInTheDocument()
    expect(screen.queryByText(/±/)).not.toBeInTheDocument()
  })
})

describe('RangeBlock: available', () => {
  it('writes the typical move unsigned with two decimals under its label', async () => {
    mockRange({})

    renderBlock('TCB')

    expect(await screen.findByText('±4.12%')).toHaveClass('range-block__figure')
    expect(screen.getByText('Typical 5-session move')).toBeInTheDocument()
  })

  it('shows two decimals even when the response rounds to fewer', async () => {
    mockRange({ range_5s_pct: 3.2 })

    renderBlock('TCB')

    expect(await screen.findByText('±3.20%')).toBeInTheDocument()
  })

  it('labels the range check "Range hit-rate" and words it "N of the last M five-session moves stayed inside it"', async () => {
    mockRange({})

    renderBlock('TCB')

    expect(await screen.findByText('Range hit-rate')).toBeInTheDocument()
    expect(screen.getByText('34 of the last 50 five-session moves stayed inside it')).toBeInTheDocument()
  })

  it('takes M from n and rounds N when rate x n is not whole', async () => {
    mockRange({ range_hit_rate: { rate: 0.7, n: 49 } }) // 34.3

    renderBlock('TCB')

    expect(await screen.findByText('34 of the last 49 five-session moves stayed inside it')).toBeInTheDocument()
  })

  it('states the nominal coverage as not a guaranteed interval', async () => {
    mockRange({})

    renderBlock('TCB')

    expect(await screen.findByText('Nominal coverage: about 2 in 3 — not a guaranteed interval.')).toBeInTheDocument()
  })

  it('derives the coverage words from the response, not from a constant', async () => {
    mockRange({ range_coverage: 0.8 })

    renderBlock('TCB')

    expect(await screen.findByText(/about 80%/)).toBeInTheDocument()
    expect(screen.queryByText(/about 2 in 3/)).not.toBeInTheDocument()
  })

  it.each([
    ['is missing', { range_hit_rate: null }],
    ['has n of 0', { range_hit_rate: { rate: null, n: 0 } }],
    ['has no rate', { range_hit_rate: { rate: null, n: 15 } }],
  ])('says "Not enough history to check the range", with no ratio, when the hit-rate %s', async (_name, override) => {
    mockRange(override)

    renderBlock('TCB')

    expect(await screen.findByText('Not enough history to check the range')).toBeInTheDocument()
    expect(screen.queryByText(/of the last/)).not.toBeInTheDocument()
    expect(screen.queryByText(/%/, { selector: '.range-block__check *' })).not.toBeInTheDocument()
  })

  it('for an uncalibrated ticker shows the band and "Not calibrated for this ticker", and no check, coverage or hit-rate', async () => {
    mockRange({ status: 'uncalibrated', range_coverage: null, range_hit_rate: { rate: 0.7, n: 50 } })

    renderBlock('TCB')

    expect(await screen.findByText('±4.12%')).toBeInTheDocument()
    expect(screen.getByText('Not calibrated for this ticker')).toBeInTheDocument()
    expect(screen.queryByText('Range hit-rate')).not.toBeInTheDocument()
    expect(screen.queryByText(/of the last/)).not.toBeInTheDocument()
    expect(screen.queryByText(/coverage/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/70%|0\.7/)).not.toBeInTheDocument()
  })

  it('drops the old As of and Horizon lines (the Stage header and the label carry them)', async () => {
    mockRange({})

    renderBlock('TCB')

    await screen.findByText('±4.12%')
    expect(screen.queryByText(/^As of/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Horizon/)).not.toBeInTheDocument()
  })

  it('never renders sigma_daily_pct', async () => {
    mockRange({ sigma_daily_pct: 1.37 })

    const { container } = renderBlock('TCB')

    await screen.findByText('±4.12%')
    expect(container.textContent).not.toContain('1.37')
    expect(container.innerHTML).not.toContain('1.37')
  })

  it('carries no sign, no direction attribute and no direction mark', async () => {
    mockRange({})

    const { container } = renderBlock('TCB')

    const figure = await screen.findByText('±4.12%')
    expect(figure.textContent).not.toMatch(/^[+-]/)
    expect(container.querySelector('[data-direction]')).toBeNull()
    expect(container).not.toHaveTextContent(/[↑↓▲▼]/)
  })

  it('decides by whether range_5s_pct is a number, so an unknown status still shows a served figure', async () => {
    mockRange({ status: 'some_future_status' })

    renderBlock('TCB')

    expect(await screen.findByText('±4.12%')).toBeInTheDocument()
  })

  it('renders the hit-rate wording once', async () => {
    mockRange({})

    renderBlock('TCB')

    await screen.findByText('±4.12%')
    expect(screen.getAllByText(/of the last 50 five-session moves/)).toHaveLength(1)
  })

  it('shows the disclaimer inside the block only when asked to', async () => {
    mockRange({})

    renderBlock('TCB', { disclaimer: true })

    await screen.findByText('±4.12%')
    expect(screen.getByText(INLINE_DISCLAIMER)).toBeInTheDocument()
  })
})

describe('RangeBlock: unavailable, not loaded and failed', () => {
  it('names the reason when range_5s_pct is null and reasons is non-empty', async () => {
    mockRange({ status: 'ineligible', reasons: ['stale'], range_5s_pct: null, sigma_daily_pct: null })

    renderBlock('TCB')

    expect(await screen.findByText(/prices are out of date|stale/i)).toBeInTheDocument()
    expect(screen.queryByText(/±/)).not.toBeInTheDocument()
  })

  it('shows a generic message when range_5s_pct is null and there are no reasons', async () => {
    mockRange({ status: 'model_unavailable', reasons: [], range_5s_pct: null, sigma_daily_pct: null })

    renderBlock('TCB')

    expect(await screen.findByText(/range unavailable for this ticker/i)).toBeInTheDocument()
  })

  it('treats a null range as unavailable even when the status says ok', async () => {
    mockRange({ status: 'ok', range_5s_pct: null })

    renderBlock('TCB')

    expect(await screen.findByText(/range unavailable for this ticker/i)).toBeInTheDocument()
  })

  it('says the ticker has not been loaded on a 404, without naming a panel that no longer exists', async () => {
    vi.spyOn(tickersApi, 'fetchTickerRange').mockRejectedValue(new ApiError('nope', { status: 404 }))

    renderBlock('TCB')

    expect(await screen.findByText(/hasn't been loaded yet/i)).toBeInTheDocument()
    expect(screen.queryByText(/ticker panel/i)).not.toBeInTheDocument()
  })

  it('shows a failure message, as an alert, on a 5xx', async () => {
    vi.spyOn(tickersApi, 'fetchTickerRange').mockRejectedValue(new ApiError('boom', { status: 503 }))

    renderBlock('TCB')

    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn't load the range/i)
    expect(screen.queryByText(/±/)).not.toBeInTheDocument()
  })

  it('tells unavailable, not loaded and failed apart', async () => {
    const kinds = []
    const scenarios = [
      () => mockRange({ range_5s_pct: null, reasons: [] }),
      () => vi.spyOn(tickersApi, 'fetchTickerRange').mockRejectedValue(new ApiError('x', { status: 404 })),
      () => vi.spyOn(tickersApi, 'fetchTickerRange').mockRejectedValue(new ApiError('x', { status: 500 })),
    ]
    for (const arrange of scenarios) {
      vi.restoreAllMocks()
      arrange()
      const { container, unmount } = renderBlock('TCB')
      await vi.waitFor(() => expect(container.querySelector('[data-kind]:not([data-kind="loading"])')).not.toBeNull())
      kinds.push(container.querySelector('[data-kind]').getAttribute('data-kind'))
      unmount()
    }

    expect(new Set(kinds).size).toBe(kinds.length)
  })
})
